"""
Visual LoRA Loader 节点 - 带 lora_testing 风格弹窗的可视化LoRA加载器
支持全屏模态弹窗选择LoRA，含图片预览、搜索、文件夹浏览、网格/列表视图切换
前端UI由 js/visual_lora_loader.js 提供
"""

import json
import os
import folder_paths
import comfy.utils
import comfy.sd

from .lora_load_utils import (
    ensure_lora_has_compatible_patches,
    parse_lora_list,
    resolve_lora_name,
)


def _load_lora_cached_sha256(lora_name: str) -> str | None:
    """
    读取 LoRA 的 SHA256 哈希值。
    优先从全局离线缓存(naiba_sha256_cache.json)读取，其次回退到
    模型同目录的 .civitai.info.json 文件。

    Args:
        lora_name: LoRA 文件名（可能带前导斜杠/反斜杠）

    Returns:
        str | None: SHA256 哈希值，如果都查不到则返回 None
    """
    if not lora_name:
        return None

    # 1) 优先：全局离线缓存（离线缓存SHA256/批量同步写入）
    try:
        from . import sha256_cache
        sha = sha256_cache.get(lora_name)
        if not sha:
            norm = lora_name.replace("\\", "/").lstrip("/")
            if norm != lora_name:
                sha = sha256_cache.get(norm)
        if sha:
            return sha
    except Exception:
        pass

    # 2) 回退：模型同目录的 .civitai.info.json
    try:
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            return None

        metadata_path = os.path.splitext(lora_path)[0] + ".civitai.info.json"
        if not os.path.exists(metadata_path):
            return None

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        if isinstance(metadata, dict):
            return metadata.get("hash")
    except Exception:
        return None

    return None


def _load_lora_download_url(lora_name: str) -> str | None:
    """
    读取 LoRA 的 Civitai 下载链接。
    从模型同目录的 .civitai.info.json 中取 version_id，
    按 Civitai 官方下载地址格式构造链接（与 civitai_utils.build_civitai_version_info 的回退逻辑一致）。

    Args:
        lora_name: LoRA 文件名（可能带前导斜杠/反斜杠）

    Returns:
        str | None: 下载链接，未同步或读取失败时返回 None
    """
    if not lora_name:
        return None
    try:
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            return None
        metadata_path = os.path.splitext(lora_path)[0] + ".civitai.info.json"
        if not os.path.exists(metadata_path):
            return None
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        if isinstance(metadata, dict):
            version_id = metadata.get("version_id")
            if version_id:
                return f"https://civitai.com/api/download/models/{version_id}"
    except (OSError, ValueError, TypeError) as e:
        print(f"[VisualLoRALoader] 读取 LoRA 下载链接失败 {lora_name}: {e}")
    return None


def _build_lora_info_text(lora_configs: list) -> str:
    """
    把 LoRA 配置列表渲染成人类可读的多行文本。

    每行格式: 序号. [开关状态] 名称 | M:模型权重 C:CLIP权重 | 下载链接 | sha256: 哈希
    """
    if not lora_configs:
        return "（未选择任何 LoRA）"
    lines = []
    for index, config in enumerate(lora_configs, start=1):
        if not isinstance(config, dict):
            lines.append(f"{index}. [配置无效]")
            continue
        name = str(config.get("name", "")).replace("\\", "/")
        enabled = bool(config.get("enabled", False))
        enabled_label = "开" if enabled else "关"
        try:
            strength_model = float(config.get("strength_model", 1.0))
            strength_clip = float(config.get("strength_clip", 1.0))
        except (TypeError, ValueError):
            strength_model = 1.0
            strength_clip = 1.0
        # 防御性解析：info 输出绝不打断模型加载本身
        try:
            resolved_name = resolve_lora_name(config)
        except Exception as e:
            print(f"[VisualLoRALoader] 解析 LoRA 名称失败 {name}: {e}")
            resolved_name = name
        resolved_display = str(resolved_name).replace("\\", "/")
        download_url = _load_lora_download_url(str(resolved_name)) or _load_lora_download_url(name)
        download_label = download_url if download_url else "（未同步到 Civitai，无下载链接）"
        # sha256 已由 load_loras 统一回填（全局缓存/元数据文件），缺失时明确标注
        sha256 = str(config.get("sha256") or "").strip()
        sha_label = sha256 if sha256 else "（无 sha256）"
        lines.append(
            f"{index}. [{enabled_label}] {resolved_display} | "
            f"M:{strength_model:.2f} C:{strength_clip:.2f} | {download_label} | sha256: {sha_label}"
        )
    return "\n".join(lines)


class VisualLoRALoader:
    """
    可视化LoRA加载器节点
    通过前端JS扩展提供全屏模态弹窗选择LoRA，支持多选、权重控制、预设管理
    所有LoRA配置以JSON格式存储在隐藏的lora_data字段中
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_data": ("STRING", {
                    "default": "[]",
                    "multiline": True,
                    "tooltip": "LoRA配置JSON数据（由前端弹窗UI自动管理，无需手动编辑）"
                }),
            },
            "optional": {
                "model": ("MODEL", {"tooltip": "输入的扩散模型（可选，不连接时仅加载CLIP部分）"}),
                "clip": ("CLIP", {"tooltip": "输入的CLIP模型（可选，不连接时仅加载模型部分）"}),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("model", "clip", "lora_names", "preset_json", "lora_info")
    FUNCTION = "load_loras"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "可视化LoRA加载器节点 - 点击按钮弹出全屏模态弹窗选择LoRA。\n"
        "弹窗支持图片预览、搜索导航、文件夹浏览、网格/列表视图切换。\n"
        "每个LoRA都有独立的启用开关和M/C权重控制（M=Model, C=CLIP）。\n"
        "配置会自动保存到工作流中，支持预设管理。"
    )
    SEARCH_ALIASES = ["naiba", "visual lora", "lora picker", "lora browser", "lora gallery"]

    def load_loras(self, model=None, lora_data="[]", clip=None):
        """
        读取JSON配置，依次应用所有启用的LoRA

        JSON格式示例:
        [
            {
                "name": "some_lora.safetensors",
                "strength_model": 1.0,
                "strength_clip": 1.0,
                "enabled": true
            }
        ]
        """
        # 解析JSON配置
        loras = parse_lora_list(lora_data, "lora_data")

        # 只记录真正成功应用的 LoRA；失败项汇总后让节点明确报错。
        loaded_lora_names = []
        load_failures = []

        # 依次应用每个启用的LoRA
        for preset_index, lora_config in enumerate(loras):
            if not isinstance(lora_config, dict):
                load_failures.append(f"第 {preset_index + 1} 项不是 LoRA 对象")
                continue
            # 检查是否启用
            if not lora_config.get("enabled", False):
                continue

            # 获取LoRA文件名
            configured_name = lora_config.get("name", "")
            if not configured_name:
                load_failures.append(f"第 {preset_index + 1} 项已启用但缺少 name")
                continue

            # 获取权重
            strength_model = float(lora_config.get("strength_model", 1.0))
            strength_clip = float(lora_config.get("strength_clip", 1.0))

            # 如果Model为None，则强制strength_model为0
            if model is None:
                strength_model = 0
            
            # 如果CLIP为None，则强制strength_clip为0
            if clip is None:
                strength_clip = 0

            # 权重都为0则跳过
            if strength_model == 0 and strength_clip == 0:
                continue

            try:
                lora_name = resolve_lora_name(lora_config)
                # 加载LoRA文件
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                lora = ensure_lora_has_compatible_patches(
                    model, clip, lora, strength_model, strength_clip
                )

                # 应用LoRA到模型和CLIP（如果为None则跳过对应部分）
                model, clip = comfy.sd.load_lora_for_models(
                    model, clip, lora, strength_model, strength_clip
                )
                loaded_lora_names.append(lora_name)
            except Exception as e:
                load_failures.append(f"{configured_name}: {type(e).__name__}: {e}")
                continue

        if load_failures:
            details = "\n".join(f"- {item}" for item in load_failures)
            raise RuntimeError(
                f"Visual LoRA Loader 有 {len(load_failures)} 个 LoRA 未能应用：\n{details}"
            )

        lora_names_json = json.dumps(loaded_lora_names, ensure_ascii=False)
        
        # 为每个 LoRA 尝试从缓存读取 SHA256（从 .civitai.info.json）
        loras_with_sha256 = []
        for lora_config in loras:
            lora_entry = dict(lora_config)  # 复制一份，避免修改原始数据
            
            # 如果已经有 sha256 字段则保留，否则尝试从缓存读取
            if "sha256" not in lora_entry:
                lora_name = lora_entry.get("name", "")
                if lora_name:
                    cached_sha256 = _load_lora_cached_sha256(lora_name)
                    if cached_sha256:
                        lora_entry["sha256"] = cached_sha256
            
            loras_with_sha256.append(lora_entry)
        
        # 输出完整的LoRA配置JSON（与预设JSON格式一致）
        # 格式: [{name, strength_model, strength_clip, enabled, sha256?}, ...]
        try:
            preset_json = json.dumps(loras_with_sha256, ensure_ascii=False, indent=2)
        except Exception:
            preset_json = lora_data if lora_data.strip() else "[]"

        # 输出人类可读的 LoRA 信息（名称/开关/权重/Civitai下载链接）
        try:
            lora_info_text = _build_lora_info_text(loras_with_sha256)
        except Exception as e:
            # 信息输出失败不影响模型加载，但要留日志并明确报错占位
            print(f"[VisualLoRALoader] 生成 lora_info 失败: {e}")
            lora_info_text = "（生成 LoRA 信息失败，详见控制台日志）"

        return (model, clip, lora_names_json, preset_json, lora_info_text)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "VisualLoRALoader": VisualLoRALoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VisualLoRALoader": "Visual LoRA Loader",
}
