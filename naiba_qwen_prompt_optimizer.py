"""
Naiba Qwen 提示词工作台
用 models/LLM 下的 GGUF 语言模型(搭配 mmproj 视觉模型)把口语化需求改写成
Qwen Image 2.1 可直接使用的长提示词。三种模式自动判定:
- 无图像输入            -> 文生图(官方 T2I 模板,输出 rewritten_prompt/wh_ratio)
- 有图像 + 有提示词     -> 图片编辑(官方 EDIT 模板,额外输出 ratio_follow)
- 有图像 + 无提示词     -> 反推(T2I 模板 + 反推补充规则)
前端 UI 见 js/naiba_qwen_prompt_optimizer.js。运行依赖 llama-cpp-python>=0.3.48
(JamePeng fork,提供 Qwen35ChatHandler),未就绪时节点横幅可一键安装。
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
import json
import platform
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import folder_paths
from aiohttp import web
from server import PromptServer

from .naiba_qwen_prompt_runtime import (
    append_transparency,
    build_system_prompt,
    build_user_turn,
    close_model,
    collect_images,
    complete,
    select_language,
)
from .naiba_qwen_prompt_templates import edit_prompt, reverse_prompt, t2i_prompt


def _register_llm_folder() -> None:
    """确保 models/LLM(含小写变体)成为 .gguf 模型目录。"""
    if "LLM" in folder_paths.folder_names_and_paths:
        return
    models_dir = Path(folder_paths.models_dir)
    roots = [str(models_dir / "LLM"), str(models_dir / "llm")]
    folder_paths.folder_names_and_paths["LLM"] = (roots, {".gguf"})


_register_llm_folder()


# ---------------------------------------------------------------- 依赖管理

_LLAMA_MIN = (0, 3, 48)
_LLAMA_RELEASES = "https://github.com/JamePeng/llama-cpp-python/releases"
_LLAMA_RELEASES_API = "https://api.github.com/repos/JamePeng/llama-cpp-python/releases?per_page=100"
_INSTALL_LOCK = asyncio.Lock()


def _version_tuple(text: str) -> tuple[int, int, int]:
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


def _wheel_spec() -> dict | None:
    """按当前 系统/Python/CUDA 组合推算官方 wheel 的筛选条件。"""
    system, machine = platform.system(), platform.machine().casefold()
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    if system == "Darwin" and machine in ("arm64", "aarch64"):
        return {"marker": "-metal-macos-", "suffix": f"-{py_tag}-{py_tag}-macosx_11_0_arm64.whl", "backend": "metal"}
    if system == "Windows" and machine in ("amd64", "x86_64"):
        marker, platform_tag = "-win-", "win_amd64"
    elif system == "Linux" and machine in ("amd64", "x86_64"):
        marker, platform_tag = "-linux-", "linux_x86_64"
    else:
        return None
    try:
        import torch
        cuda = str(torch.version.cuda or "")
    except Exception:
        return None
    cuda_match = re.match(r"(\d+)\.(\d+)", cuda)
    if not cuda_match:
        return None
    backend = f"cu{cuda_match.group(1)}{cuda_match.group(2)}"
    return {
        "marker": f"-{backend}{marker}",
        "suffix": f"-{py_tag}-{py_tag}-{platform_tag}.whl",
        "backend": backend,
    }


def llama_dependency_status() -> dict:
    try:
        version = importlib.metadata.version("llama-cpp-python")
    except importlib.metadata.PackageNotFoundError:
        version = ""
    problems: list[str] = []
    if not version:
        problems.append("未安装 llama-cpp-python")
    elif _version_tuple(version) < _LLAMA_MIN:
        problems.append(f"llama-cpp-python 版本过旧：{version}")
    if importlib.util.find_spec("diskcache") is None:
        problems.append("缺少 diskcache")
    status: dict = {
        "installed_version": version or None,
        "needs_install": bool(problems),
        "reason": "；".join(problems) or "依赖可用",
        "minimum_version": "0.3.48",
        "release_url": _LLAMA_RELEASES,
    }
    spec = _wheel_spec()
    status["supported"] = spec is not None
    if spec is not None:
        status["backend"] = spec["backend"]
    return status


def _pick_wheel(spec: dict) -> tuple[str, str]:
    request = urllib.request.Request(
        _LLAMA_RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "naiba-test"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        releases = json.load(response)
    marker = spec["marker"].casefold()
    suffix = spec["suffix"].casefold()
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        if marker not in str(release.get("tag_name", "")).casefold():
            continue
        for asset in release.get("assets", []):
            name = str(asset.get("name", ""))
            url = str(asset.get("browser_download_url", ""))
            if name.casefold().endswith(suffix) and url.startswith("https://github.com/JamePeng/llama-cpp-python/releases/download/"):
                return url, name
    raise RuntimeError("发布页没有匹配当前系统/Python/CUDA 的 wheel。")


def install_llama() -> dict:
    spec = _wheel_spec()
    if spec is None:
        raise RuntimeError("当前系统/Python/CUDA 组合没有可自动安装的 wheel，请按发布页说明手动安装。")
    wheel_url, wheel_name = _pick_wheel(spec)
    done = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
         "--upgrade", "diskcache", wheel_url],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    if done.returncode != 0:
        tail = "\n".join(part for part in (done.stdout, done.stderr) if part.strip())[-2000:]
        raise RuntimeError(f"pip 安装失败（退出码 {done.returncode}）：\n{tail}")
    close_model()  # 旧实例可能还驻留显存,装新包后必须重载
    return {"success": True, "wheel": wheel_name, "message": "llama-cpp-python 安装完成，请完全重启 ComfyUI 后使用。"}


@PromptServer.instance.routes.get("/naiba/qwen_prompt_optimizer/llama_status")
async def _llama_status_route(_request):
    return web.json_response(llama_dependency_status())


@PromptServer.instance.routes.post("/naiba/qwen_prompt_optimizer/install_llama")
async def _llama_install_route(request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if payload.get("confirm") is not True:
        return web.json_response({"success": False, "message": "安装请求缺少用户确认。"}, status=400)
    if _INSTALL_LOCK.locked():
        return web.json_response({"success": False, "message": "安装任务正在进行。"}, status=409)
    async with _INSTALL_LOCK:
        try:
            return web.json_response(await asyncio.to_thread(install_llama))
        except Exception as error:
            return web.json_response(
                {"success": False, "message": str(error), "release_url": _LLAMA_RELEASES},
                status=500,
            )


# ---------------------------------------------------------------- 模型选择

def _model_choices() -> tuple[list[str], list[str]]:
    names = folder_paths.get_filename_list("LLM")
    main = [n for n in names if "mmproj" not in n.casefold()]
    vision = [n for n in names if "mmproj" in n.casefold()]
    return (main or ["未找到 GGUF 模型"], vision or ["未找到 mmproj GGUF 模型"])


def _prefer(names: list[str], keyword: str) -> str:
    return next((n for n in names if keyword.casefold() in n.casefold()), names[0])


def _model_path(display: str, expect_mmproj: bool) -> str:
    path = folder_paths.get_full_path("LLM", display)
    if path is None:
        raise ValueError(f"找不到所选模型：{display}")
    if ("mmproj" in Path(display).name.casefold()) != bool(expect_mmproj):
        raise ValueError(f"模型类型不符：{display}")
    return path


# ---------------------------------------------------------------- 节点

class NaibaQwenPromptOptimizer:
    @classmethod
    def INPUT_TYPES(cls):
        main, vision = _model_choices()
        return {
            "required": {
                "用户提示词": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": False}),
                "文生图模型": (main, {"default": _prefer(main, "PE-T2I")}),
                "图生图模型": (main, {"default": _prefer(main, "PE-I2I")}),
                "视觉模型": (vision, {"default": _prefer(vision, "PE-I2I")}),
                "输出语言": (["自动", "中文", "English"], {"default": "自动"}),
                "透明背景": ("BOOLEAN", {"default": False}),
                "种子值": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
                "种子模式": (["固定", "随机"], {"default": "固定"}),
                "卸载模型": (["自动", "保持加载", "运行后自动卸载", "运行前后自动卸载"], {"default": "自动"}),
            },
            "optional": {f"图像_{index:02d}": ("IMAGE",) for index in range(1, 11)},
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING", "STRING", "BOOLEAN")
    RETURN_NAMES = ("prompt", "json", "是否反推")
    FUNCTION = "optimize"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "Qwen 提示词工作台 - 用本地 GGUF 模型把口语化需求改写成 Qwen Image 2.1 长提示词。\n"
        "无图=文生图;有图+有提示词=图片编辑;有图+无提示词=反推。\n"
        "需要 models/LLM 目录下的 GGUF 主模型与 mmproj 视觉模型,"
        "以及 llama-cpp-python>=0.3.48(节点横幅可一键安装)。"
    )
    SEARCH_ALIASES = ["naiba", "qwen", "prompt", "optimizer", "提示词", "优化", "反推", "工作台"]

    @classmethod
    def IS_CHANGED(cls, 种子值=0, **kwargs):
        return max(0, min(0xFFFFFFFF, int(种子值)))

    def optimize(
        self,
        用户提示词,
        文生图模型,
        图生图模型,
        视觉模型,
        输出语言,
        透明背景,
        种子值,
        种子模式="固定",
        卸载模型="自动",
        unique_id=None,
        **kwargs,
    ):
        if isinstance(卸载模型, bool):
            卸载模型 = "运行后自动卸载" if 卸载模型 else "保持加载"
        images = collect_images(kwargs)
        has_images = bool(images)
        text = str(用户提示词 or "").strip()
        reverse_mode = has_images and not text
        edit_mode = has_images and not reverse_mode

        if reverse_mode:
            base_prompt = reverse_prompt()
        elif has_images:
            base_prompt = edit_prompt()
        else:
            base_prompt = t2i_prompt()

        language = select_language(输出语言, text, reverse_mode)
        system_prompt = build_system_prompt(base_prompt, language, bool(透明背景), reverse_mode)
        user_prompt = build_user_turn(text, images, language, bool(透明背景), reverse_mode)

        seed = max(0, min(0xFFFFFFFF, int(种子值)))
        fields = complete(
            model_path=_model_path(图生图模型 if edit_mode else 文生图模型, expect_mmproj=False),
            mmproj_path=_model_path(视觉模型, expect_mmproj=True),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=images,
            edit_mode=edit_mode,
            seed=seed,
            unload_policy=卸载模型,
        )
        prompt_text = append_transparency(fields["rewritten_prompt"], bool(透明背景))
        payload = dict(fields)
        payload["rewritten_prompt"] = prompt_text
        return {
            "ui": {"seed": [seed]},
            "result": (prompt_text, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), reverse_mode),
        }


NODE_CLASS_MAPPINGS = {
    "NaibaQwenPromptOptimizer": NaibaQwenPromptOptimizer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaQwenPromptOptimizer": "Naiba Qwen 提示词工作台",
}
