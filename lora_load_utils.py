"""共享的 LoRA 加载验证工具。"""

import json

import folder_paths
import comfy.lora
import comfy.lora_convert

from .lora_preset_paths import normalize_lora_name, normalize_sha256


def parse_lora_list(raw_value, field_name):
    """严格解析加载器配置，避免无效 JSON 被静默当成空预设。"""
    if not isinstance(raw_value, str):
        raise ValueError(f"{field_name} 必须是 JSON 字符串")
    if not raw_value.strip():
        return []
    try:
        items = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError(f"{field_name} 不是有效 JSON: {error}") from error
    if not isinstance(items, list):
        raise ValueError(f"{field_name} 顶层必须是 LoRA 数组")
    return items


def resolve_lora_name(item):
    """优先采用实际存在的配置路径，缺失时才按缓存 SHA256 唯一回退。"""
    configured_name = normalize_lora_name(item.get("name", ""))
    try:
        if configured_name and folder_paths.get_full_path("loras", configured_name):
            return configured_name
    except Exception:
        pass

    sha = normalize_sha256(item.get("sha256"))
    if not sha:
        return configured_name

    from . import sha256_cache

    current_candidates = []
    for candidate in sha256_cache.build_sha_candidates_index().get(sha, []):
        try:
            full_path = folder_paths.get_full_path("loras", candidate)
        except Exception:
            full_path = None
        if full_path and sha256_cache.check_entry_state(candidate, full_path) == "current":
            current_candidates.append(candidate)

    if len(current_candidates) == 1:
        return current_candidates[0]
    if len(current_candidates) > 1:
        choices = "、".join(current_candidates)
        raise ValueError(f"SHA256 对应多个有效本地路径，请先确认：{choices}")
    return configured_name


def ensure_lora_has_compatible_patches(
    model, clip, lora, strength_model, strength_clip
):
    """确认 LoRA 至少能向一个非零权重目标添加补丁。"""
    key_map = {}
    if model is not None and strength_model != 0:
        key_map = comfy.lora.model_lora_keys_unet(model.model, key_map)
    if clip is not None and strength_clip != 0:
        key_map = comfy.lora.model_lora_keys_clip(clip.cond_stage_model, key_map)

    converted = comfy.lora_convert.convert_lora(lora)
    compatible_patches = comfy.lora.load_lora(
        converted, key_map, log_missing=False
    )
    if not compatible_patches:
        raise ValueError("未找到可应用到当前模型或 CLIP 的兼容 LoRA 键")
