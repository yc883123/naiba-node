"""共享的 LoRA 加载验证工具。"""

import json
import logging

import folder_paths
import comfy.lora
import comfy.lora_convert

from .lora_preset_paths import normalize_lora_name, normalize_sha256


_MINIMAX_LORA_SUFFIXES = (".lora_A.weight", ".lora_B.weight")


def _is_minimax_h3_model(model):
    inner_model = getattr(model, "model", None)
    model_config = getattr(inner_model, "model_config", None)
    unet_config = getattr(model_config, "unet_config", {})
    return (
        isinstance(unet_config, dict)
        and unet_config.get("image_model") == "minimax_h3"
    ) or inner_model.__class__.__name__ == "MiniMaxH3"


def _minimax_lora_base(key):
    for suffix in _MINIMAX_LORA_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return None


def _linear_lora_shapes_match(target, lora_a, lora_b):
    target_shape = getattr(target, "shape", ())
    a_shape = getattr(lora_a, "shape", ())
    b_shape = getattr(lora_b, "shape", ())
    if len(target_shape) != 2 or len(a_shape) != 2 or len(b_shape) != 2:
        return True
    return (
        a_shape[0] == b_shape[1]
        and a_shape[1] == target_shape[1]
        and b_shape[0] == target_shape[0]
    )


def _normalize_minimax_h3_lora(model, lora):
    """Translate native MiniMax H3 adapter keys to ComfyUI model keys."""
    if model is None or not _is_minimax_h3_model(model):
        return lora

    model_state = model.model.state_dict()
    normalized = {}
    renamed = 0
    for key, value in lora.items():
        normalized_key = key
        base = _minimax_lora_base(key)
        if base is not None and not base.startswith("diffusion_model."):
            candidate = "diffusion_model.{}".format(key)
            candidate_base = _minimax_lora_base(candidate)
            if "{}.weight".format(candidate_base) in model_state:
                normalized_key = candidate
                renamed += 1
        normalized[normalized_key] = value

    incompatible_bases = set()
    bases = {
        base
        for key in normalized
        if (base := _minimax_lora_base(key)) is not None
    }
    for base in bases:
        target = model_state.get("{}.weight".format(base))
        lora_a = normalized.get("{}.lora_A.weight".format(base))
        lora_b = normalized.get("{}.lora_B.weight".format(base))
        if target is None or lora_a is None or lora_b is None:
            continue
        if not _linear_lora_shapes_match(target, lora_a, lora_b):
            incompatible_bases.add(base)

    if incompatible_bases:
        for base in incompatible_bases:
            normalized.pop("{}.lora_A.weight".format(base), None)
            normalized.pop("{}.lora_B.weight".format(base), None)
            normalized.pop("{}.alpha".format(base), None)
        logging.warning(
            "[naiba-node] MiniMax H3 LoRA skipped %d adapter pair(s) "
            "whose shapes do not match the current model (usually full-model "
            "AdaLN adapters used with a pruned/curve checkpoint).",
            len(incompatible_bases),
        )

    if renamed:
        logging.info(
            "[naiba-node] Normalized %d native MiniMax H3 LoRA key(s) for ComfyUI.",
            renamed,
        )
    return normalized


def prepare_lora_for_models(model, lora):
    """Apply ComfyUI conversions plus model-specific compatibility handling."""
    converted = comfy.lora_convert.convert_lora(lora)
    return _normalize_minimax_h3_lora(model, converted)


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

    converted = prepare_lora_for_models(model, lora)
    compatible_patches = comfy.lora.load_lora(
        converted, key_map, log_missing=False
    )
    if not compatible_patches:
        raise ValueError("未找到可应用到当前模型或 CLIP 的兼容 LoRA 键")
    return converted
