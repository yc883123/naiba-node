"""
Naiba Qwen 提示词工作台 - 本地 GGUF 推理运行时
基于 llama-cpp-python(JamePeng fork,需 >=0.3.48 提供 Qwen35ChatHandler)。
负责:模型加载与单槽缓存、显存协调、消息组装、流式补全(响应 ComfyUI 中断)、
结果解析与透明背景后处理。
"""

from __future__ import annotations

import base64
import gc
import inspect
import io
import json
import os
import re
import threading
import time

import numpy as np
import torch
from PIL import Image

try:
    import comfy.model_management as model_management
except ImportError:
    model_management = None

try:
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Qwen35ChatHandler
except ImportError as exc:
    Llama = None
    Qwen35ChatHandler = None
    _LLAMA_ERROR = exc

# Qwen-Image RGBA 工作流的固定触发句(功能约定,输出透明背景提示词时首尾包裹)
TRANSPARENT_HEAD = "This is an RGBA image with transparency."
TRANSPARENT_TAIL = "The image has alpha channel and the background is transparent."

MAX_OUTPUT_TOKENS = 2048
TEMPERATURE = 0.3
TOP_P = 0.9
TOP_K = 30
MIN_P = 0.05

# 卸载策略
UNLOAD_AUTO = "自动"
UNLOAD_KEEP = "保持加载"
UNLOAD_AFTER = "运行后自动卸载"
UNLOAD_BEFORE_AFTER = "运行前后自动卸载"


# ---------------------------------------------------------------- 语言与消息

def _has_cjk(text: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", text or "") is not None


def select_language(choice: str, user_prompt: str, reverse_mode: bool = False) -> str:
    """把节点上的输出语言选项折算成 Chinese/English。

    自动档:反推固定中文;否则提示词含中文(或为空,准备反推)时用中文。
    """
    if choice == "中文":
        return "Chinese"
    if choice == "English":
        return "English"
    if reverse_mode:
        return "Chinese"
    text = (user_prompt or "").strip()
    return "Chinese" if (not text or _has_cjk(text)) else "English"


def _language_lock(language: str) -> str:
    if language == "Chinese":
        return (
            "OUTPUT LANGUAGE LOCK: the descriptive prose of rewritten_prompt is written in "
            "Chinese. Only text that must visibly appear inside the image keeps its original "
            "script. 描述性文字必须全部使用中文，画面内文字除外。"
        )
    return (
        "OUTPUT LANGUAGE LOCK: the descriptive prose of rewritten_prompt is written in "
        "English. Only text that must visibly appear inside the image keeps its original "
        "script. 描述性文字必须全部使用英文，画面内文字除外。"
    )


def _transparency_lock() -> str:
    return (
        "TRANSPARENT BACKGROUND OVERRIDE: the result is a native RGBA image on a fully "
        "transparent canvas. Remove every background description - backdrops, walls, floors, "
        "rooms, tables, sky, clouds, landscapes, gradients, background colors - even when the "
        "user or a reference image asks for them. The subject stands alone on transparency."
    )


def build_system_prompt(base: str, language: str, transparent: bool, reverse_mode: bool = False) -> str:
    """官方模板 + 运行时锁定段(语言 / 透明背景)。不改动模板原文,只向后追加。"""
    lock = _language_lock(language)
    if transparent:
        lock += "\n\n" + _transparency_lock()
    if reverse_mode:
        lock += "\n\nOutput only the two-field JSON (rewritten_prompt, wh_ratio); never add ratio_follow in this mode."
    return base + "\n\n" + lock


def build_user_turn(user_prompt: str, images: list, language: str, transparent: bool, reverse_mode: bool) -> str:
    """组装本轮用户消息:语言要求 + 图像编号 + 任务正文。"""
    count = len(images)
    head = f"OUTPUT LANGUAGE: write the descriptive prose of rewritten_prompt in {language}."
    if transparent:
        head += " The result must use a fully transparent background; ignore any contradictory background request."
    if count and not reverse_mode:
        labels = ", ".join(f"<image{i}>" for i in range(1, count + 1))
        head += (
            f" Exactly {count} image(s) are attached in order: {labels}. Refer only to "
            "images actually attached, never invent or renumber labels."
        )
    if reverse_mode:
        task = (
            "No user instruction was given. Inspect the input image and write the final "
            "text-to-image prompt exactly as the reverse-prompting rules above require."
        )
    else:
        task = "USER REQUEST (follow its meaning, not its language):\n" + (user_prompt or "").strip()
    return head + "\n\n" + task


# ---------------------------------------------------------------- 结果解析

def extract_json(text: str) -> dict:
    """从模型回复中提取 JSON 对象(容忍思考标签与代码围栏)。"""
    clean = re.sub(r"<think>.*?(?:</think>|$)", "", text or "", flags=re.DOTALL).strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        found = re.search(r"\{.*\}", clean, flags=re.DOTALL)
        if not found:
            raise ValueError(f"模型没有返回有效 JSON：{clean[:300]}")
        data = json.loads(found.group(0))
    if not isinstance(data, dict):
        raise ValueError("模型 JSON 返回值不是对象。")
    return data


def validate_result(data: dict, edit_mode: bool) -> dict:
    fields = {
        "rewritten_prompt": str(data.get("rewritten_prompt", "")).strip(),
        "wh_ratio": str(data.get("wh_ratio", "") or "").strip(),
    }
    if edit_mode:
        fields["ratio_follow"] = str(data.get("ratio_follow", "") or "").strip()
    if not fields["rewritten_prompt"]:
        raise ValueError("模型返回的 rewritten_prompt 为空。")
    return fields


def _json_schema(edit_mode: bool) -> dict:
    properties = {
        "rewritten_prompt": {"type": "string"},
        "wh_ratio": {"type": "string"},
    }
    required = ["rewritten_prompt", "wh_ratio"]
    if edit_mode:
        properties["ratio_follow"] = {"type": "string"}
        required.append("ratio_follow")
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _answer_text(result: dict) -> str:
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"模型返回结构异常：{result}") from exc


# ---------------------------------------------------------------- 输入图像

def collect_images(inputs: dict) -> list:
    """按编号收集 图像_NN / image_NN 端口上的批量张量,超过 10 张报错。"""
    picked = []
    for name, value in inputs.items():
        match = re.search(r"(\d+)$", str(name))
        if not match:
            continue
        key = str(name).casefold().replace("_", "")
        if not (key.startswith("图像") or key.startswith("image")):
            continue
        if torch.is_tensor(value) and value.ndim == 4 and value.shape[0] > 0 and value.shape[-1] >= 3:
            picked.append((int(match.group(1)), value))
    picked.sort(key=lambda item: item[0])
    images = [frame for _, batch in picked for frame in batch]
    if len(images) > 10:
        raise ValueError("Naiba Qwen 提示词工作台：图像总数超过 10 张。")
    return images


def _image_data_url(frame: torch.Tensor, max_side: int) -> str:
    array = frame.detach().cpu().float().clamp(0, 1).numpy()[..., :3]
    pil = Image.fromarray((array * 255.0 + 0.5).astype(np.uint8), mode="RGB")
    if 0 < max_side < max(pil.size):
        pil.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    pil.save(buffer, format="JPEG", quality=95)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _context_plan(image_count: int, reverse_mode: bool) -> tuple[int, int]:
    """按图像数量决定上下文长度与单图最长边。"""
    if image_count <= 0:
        return 8192, 0
    if image_count == 1:
        return (16384, 1536) if reverse_mode else (8192, 768)
    if image_count <= 4:
        return 16384, 512
    return 32768, 256


# ---------------------------------------------------------------- 透明背景清洗

_BACKGROUND_ZH = "黑|白|灰|红|橙|黄|绿|青|蓝|紫|粉|棕|米|金|银|彩色"
_BACKGROUND_EN = (
    "black|white|gray|grey|red|orange|yellow|green|cyan|blue|purple|pink|brown|"
    "beige|gold|silver|colored|colourful|colorful"
)
_RESIDUE_ZH = "天空|云层|云朵|云彩|地平线|风景|景色|墙面|墙壁|地面|地板|桌面|房间|室内|背景板|背景布|渐变背景|背景渐变"
_RESIDUE_EN = (
    r"sky|clouds?|horizon|landscape|scenery|wall|floor|tabletop|table|room|"
    r"interior|outdoor|backdrop|gradient background|background gradient"
)

_ZH_COLOR_BACKGROUND = re.compile(rf"(?:{_BACKGROUND_ZH})色?\s*背景")
_ZH_BACKGROUND_IS = re.compile(
    rf"背景(?:颜色)?\s*(?:是|为|呈|：|:)\s*[^，。；\n]*?(?:{_BACKGROUND_ZH})色?"
)
_EN_ON_BACKGROUND = re.compile(
    rf"\bon (?:a |an |the )?(?:[\w-]+ ){{0,3}}(?:{_BACKGROUND_EN})\s+(?:colored\s+)?(?:background|backdrop)\b",
    re.IGNORECASE,
)
_EN_COLOR_BACKGROUND = re.compile(
    rf"\b(?:{_BACKGROUND_EN})(?:\s+[\w-]+){{0,3}}\s+(?:background|backdrop)\b",
    re.IGNORECASE,
)
_EN_BACKGROUND_IS = re.compile(
    rf"\bbackground(?:\s+color)?\s+(?:is|was|becomes|changed\s+to|replaced\s+with|set\s+to)\s+"
    rf"[^,.!?;\n]*?\b(?:{_BACKGROUND_EN})\b",
    re.IGNORECASE,
)
_RESIDUE_ZH_CLAUSE = re.compile(rf"(?:^|(?<=[，。；、]))[^，。；\n]*?(?:{_RESIDUE_ZH})[^，。；\n]*(?=[，。；\n]|$)")
_RESIDUE_EN_CLAUSE = re.compile(
    rf"(?:^|(?<=[,.!?;]))[^,.!?;\n]*?\b(?:{_RESIDUE_EN})\b[^,.!?;\n]*(?=[,.!?;\n]|$)",
    re.IGNORECASE,
)


def _clean_background_text(text: str) -> str:
    """把常见实色背景描述改写为透明背景;双引号内的画面渲染文字保持原样。"""
    stash: dict[str, str] = {}

    def _protect(match: re.Match) -> str:
        token = f"\x00{len(stash)}\x00"
        stash[token] = match.group(0)
        return token

    value = re.sub(r'"[^"]*"', _protect, text)
    value = _ZH_COLOR_BACKGROUND.sub("透明背景", value)
    value = _ZH_BACKGROUND_IS.sub("背景为透明", value)
    value = _EN_ON_BACKGROUND.sub("on a transparent background", value)
    value = _EN_COLOR_BACKGROUND.sub("transparent background", value)
    value = _EN_BACKGROUND_IS.sub("the background is transparent", value)
    value = re.sub(r"背景为透明背景", "背景为透明", value)
    value = _RESIDUE_ZH_CLAUSE.sub("", value)
    value = _RESIDUE_EN_CLAUSE.sub("", value)
    value = re.sub(r"\s{2,}", " ", value)
    value = re.sub(r"([，。；、,.!?;])[，。；、,.!?;]+", r"\1", value)
    for token, original in stash.items():
        value = value.replace(token, original)
    return value.strip(" ，。；、,.!?;")


def append_transparency(prompt: str, enabled: bool) -> str:
    """透明背景开启时,清洗背景描述并包裹 RGBA 触发句。"""
    if not enabled:
        return prompt
    text = _clean_background_text(str(prompt or "").strip())
    while text.startswith(TRANSPARENT_HEAD):
        text = text[len(TRANSPARENT_HEAD):].lstrip()
    while text.endswith(TRANSPARENT_TAIL):
        text = text[: -len(TRANSPARENT_TAIL)].rstrip()
    if text and text[-1] not in ".。!?！？;；":
        text += "."
    return f"{TRANSPARENT_HEAD} {text} {TRANSPARENT_TAIL}"


# ---------------------------------------------------------------- 显存协调

def _clear_python_cache() -> None:
    gc.collect()
    if model_management is not None:
        try:
            model_management.soft_empty_cache()
        except Exception:
            pass


def _release_cuda_cache() -> None:
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if callable(getattr(torch.cuda, "ipc_collect", None)):
                torch.cuda.ipc_collect()
    except Exception:
        pass


def _vram_snapshot() -> tuple[int, int]:
    if model_management is None:
        return 0, 0
    try:
        device = model_management.get_torch_device()
        return int(model_management.get_free_memory(device)), int(model_management.get_total_memory(device))
    except Exception:
        return 0, 0


def _free_other_comfy_models() -> None:
    if model_management is None:
        return
    if not getattr(model_management, "current_loaded_models", []):
        return
    try:
        devices = model_management.get_all_torch_devices()
    except Exception:
        try:
            devices = [model_management.get_torch_device()]
        except Exception:
            return
    for device in devices:
        try:
            model_management.free_memory(1e30, device)
        except Exception:
            continue


def _file_bytes(paths) -> int:
    total = 0
    for path in paths:
        try:
            total += os.path.getsize(path)
        except OSError:
            continue
    return total


def _mmproj_on_gpu(model_path: str, mmproj_path: str | None) -> bool:
    """整套模型能安全放进空闲显存时,视觉编码器才走 GPU。"""
    if not mmproj_path:
        return False
    try:
        if not torch.cuda.is_available():
            return False
        free, _total = torch.cuda.mem_get_info()
    except Exception:
        return False
    required = _file_bytes([model_path, mmproj_path])
    return required > 0 and free > required * 1.25


# ---------------------------------------------------------------- 模型单槽

class _ModelSlot:
    """同一时间只持有一个 Llama 实例;签名(模型/上下文/视觉)变化即重载。"""

    def __init__(self):
        self.lock = threading.RLock()
        self.llm = None
        self.handler = None
        self.signature: tuple | None = None

    def get(self, model_path: str, mmproj_path: str | None, n_ctx: int, vision: bool):
        if Llama is None:
            raise RuntimeError(
                f"llama-cpp-python 不可用：{_LLAMA_ERROR}。请在节点横幅一键安装（>=0.3.48）后完全重启 ComfyUI。"
            )
        if Qwen35ChatHandler is None:
            raise RuntimeError("当前 llama-cpp-python 缺少 Qwen35ChatHandler，请安装 0.3.48 以上版本。")
        signature = (
            os.path.abspath(model_path),
            os.path.abspath(mmproj_path) if mmproj_path else "",
            int(n_ctx),
            bool(vision),
        )
        with self.lock:
            if self.llm is not None and self.signature == signature:
                return self.llm
            self.close()
            handler = Qwen35ChatHandler(
                mmproj_path=mmproj_path or None,
                use_gpu=_mmproj_on_gpu(model_path, mmproj_path),
                add_vision_id=vision,
                enable_thinking=False,
                verbose=False,
            )
            self.handler = handler
            try:
                self.llm = Llama(
                    model_path=model_path,
                    chat_handler=handler,
                    n_gpu_layers=-1,
                    n_ctx=int(n_ctx),
                    n_batch=2048,
                    n_ubatch=512,
                    verbose=False,
                )
            except Exception:
                self.close()
                raise
            self.signature = signature
            return self.llm

    def close(self) -> None:
        with self.lock:
            llm, self.llm, self.handler, self.signature = self.llm, None, None, None
            if llm is not None:
                try:
                    llm.close()
                except Exception:
                    pass
            _clear_python_cache()


_slot = _ModelSlot()


def close_model() -> None:
    """主动释放本地 llama.cpp 模型(供 ComfyUI 卸载钩子与测试调用)。"""
    _slot.close()


def _prepare_memory(policy: str, model_path: str, mmproj_path: str | None) -> None:
    _release_cuda_cache()
    wanted = (
        os.path.abspath(model_path),
        os.path.abspath(mmproj_path) if mmproj_path else "",
    )
    if _slot.llm is not None and _slot.signature is not None and _slot.signature[:2] == wanted:
        return
    free, _total = _vram_snapshot()
    required = int(_file_bytes([model_path, mmproj_path]) * 1.25)
    # 即使选择"保持加载",装不下时也要请出其它 ComfyUI 模型,否则层会落到 CPU
    if policy == UNLOAD_BEFORE_AFTER or (required > 0 and 0 < free < required):
        _free_other_comfy_models()
        _release_cuda_cache()


def _settle_after_run(policy: str) -> None:
    if policy in (UNLOAD_AFTER, UNLOAD_BEFORE_AFTER):
        _slot.close()
    elif policy == UNLOAD_AUTO:
        free, total = _vram_snapshot()
        if total and free * 2 < total:
            _slot.close()


def _reset_context(llm) -> None:
    """两次补全之间清掉 KV,避免上一轮提示词串味。"""
    try:
        llm.n_tokens = 0
    except Exception:
        pass
    ctx = getattr(llm, "_ctx", None)
    for name, args in (("kv_cache_clear", ()), ("memory_clear", (True,))):
        fn = getattr(ctx, name, None) if ctx is not None else None
        if callable(fn):
            try:
                fn(*args)
                break
            except Exception:
                continue


# ---------------------------------------------------------------- 补全

def _interrupted() -> bool:
    if model_management is None:
        return False
    try:
        return bool(model_management.processing_interrupted())
    except Exception:
        return False


def _check_interrupt() -> None:
    if not _interrupted():
        return
    throw = getattr(model_management, "throw_exception_if_processing_interrupted", None)
    if callable(throw):
        throw()
    raise InterruptedError("ComfyUI 任务已被中断。")


def _delta_of(chunk) -> dict:
    if not isinstance(chunk, dict) and hasattr(chunk, "model_dump"):
        chunk = chunk.model_dump()
    try:
        delta = chunk["choices"][0].get("delta", {})
    except (KeyError, IndexError, TypeError, AttributeError):
        return {}
    return delta if isinstance(delta, dict) else {}


def _chat(llm, messages: list, seed: int, response_format: dict | None = None) -> dict:
    """流式补全,逐 chunk 响应 ComfyUI 中断;不能流式时退回一次性调用。"""
    kwargs: dict = {
        "messages": messages,
        "seed": int(seed),
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "top_k": TOP_K,
        "min_p": MIN_P,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    try:
        supported = inspect.signature(llm.create_chat_completion).parameters
    except (TypeError, ValueError):
        supported = {}
    # reasoning_budget 是 JamePeng fork 的参数,官方包没有
    if "reasoning_budget" in supported:
        kwargs["reasoning_budget"] = 0
    _check_interrupt()
    if "stream" not in supported:
        return llm.create_chat_completion(**kwargs)
    pieces: list[str] = []
    try:
        for chunk in llm.create_chat_completion(**kwargs, stream=True):
            _check_interrupt()
            piece = _delta_of(chunk).get("content")
            if piece:
                pieces.append(piece)
    except (TypeError, NotImplementedError, ValueError):
        return llm.create_chat_completion(**kwargs)
    return {"choices": [{"message": {"role": "assistant", "content": "".join(pieces)}}], "usage": {}}


def complete(
    *,
    model_path: str,
    mmproj_path: str | None,
    system_prompt: str,
    user_prompt: str,
    images: list,
    edit_mode: bool,
    seed: int,
    unload_policy: str,
) -> dict:
    """执行一次改写,返回 {rewritten_prompt, wh_ratio[, ratio_follow]}。"""
    n_ctx, image_max_side = _context_plan(len(images), reverse_mode=bool(images) and not edit_mode)
    vision = bool(images)
    with _slot.lock:
        started = time.perf_counter()
        _prepare_memory(unload_policy, model_path, mmproj_path)
        llm = _slot.get(model_path, mmproj_path, n_ctx, vision)
        loaded_at = time.perf_counter()

        content: list = [{"type": "text", "text": user_prompt}]
        for frame in images:
            content.append({"type": "image_url", "image_url": {"url": _image_data_url(frame, image_max_side)}})
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content if vision else user_prompt},
        ]
        encoded_at = time.perf_counter()
        try:
            answer = _chat(llm, messages, seed)
            _check_interrupt()
            try:
                fields = validate_result(extract_json(_answer_text(answer)), edit_mode)
            except ValueError:
                # 模型没按 JSON 输出:清 KV 后用 schema 约束重试一次
                _reset_context(llm)
                answer = _chat(llm, messages, seed, response_format=_json_schema(edit_mode))
                _check_interrupt()
                fields = validate_result(extract_json(_answer_text(answer)), edit_mode)
        finally:
            _reset_context(llm)
            _settle_after_run(unload_policy)
        finished = time.perf_counter()
        print(
            f"[Naiba Qwen] load={loaded_at - started:.2f}s encode={encoded_at - loaded_at:.2f}s "
            f"infer={finished - encoded_at:.2f}s total={finished - started:.2f}s images={len(images)}"
        )
        return fields


def _install_unload_hook() -> None:
    """ComfyUI 卸载全部模型时,同步释放本地 llama.cpp 模型。"""
    if model_management is None or getattr(model_management, "_naiba_qwen_hook_installed", False):
        return
    original = getattr(model_management, "unload_all_models", None)
    if original is None:
        return

    def _hook(*args, **kwargs):
        close_model()
        return original(*args, **kwargs)

    model_management.unload_all_models = _hook
    model_management._naiba_qwen_hook_installed = True


_install_unload_hook()
