"""Visual LoRA Loader 触发词输出测试（独立脚本，无 pytest 依赖）。

运行：python tests/test_visual_lora_trigger_words.py
"""

import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMP_DIR = tempfile.TemporaryDirectory()
LORA_DIR = Path(TEMP_DIR.name)
LORA_PATHS = {}


def add_lora(name, metadata=None, raw_metadata=None):
    """在临时目录创建假 LoRA 文件及其 .civitai.info.json。"""
    path = LORA_DIR / name
    path.write_bytes(b"fake lora")
    LORA_PATHS[name] = str(path)
    if metadata is not None or raw_metadata is not None:
        metadata_path = Path(str(path.with_suffix("")) + ".civitai.info.json")
        text = raw_metadata if raw_metadata is not None else json.dumps(metadata, ensure_ascii=False)
        metadata_path.write_text(text, encoding="utf-8")
    return name


# ── 伪造 ComfyUI 运行环境 ─────────────────────────────────────────────
folder_paths = types.ModuleType("folder_paths")
folder_paths.get_full_path = lambda _category, name: LORA_PATHS.get(name)


def get_full_path_or_raise(_category, name):
    if name not in LORA_PATHS:
        raise FileNotFoundError(f"LoRA not found: {name}")
    return LORA_PATHS[name]


folder_paths.get_full_path_or_raise = get_full_path_or_raise
sys.modules["folder_paths"] = folder_paths

comfy = types.ModuleType("comfy")
comfy_utils = types.ModuleType("comfy.utils")
comfy_sd = types.ModuleType("comfy.sd")
comfy_lora = types.ModuleType("comfy.lora")
comfy_lora_convert = types.ModuleType("comfy.lora_convert")

comfy_utils.load_torch_file = lambda path, safe_load=True: {"path": path}
comfy_sd.load_lora_for_models = lambda model, clip, lora, strength_model, strength_clip: (model, clip)
comfy_lora.model_lora_keys_unet = lambda _model, mapping: {**mapping, "model_key": "model.patch"}
comfy_lora.model_lora_keys_clip = lambda _clip, mapping: {**mapping, "clip_key": "clip.patch"}
comfy_lora.load_lora = lambda _lora, _mapping, log_missing=False: {"model.patch": object()}
comfy_lora_convert.convert_lora = lambda lora: lora

comfy.utils = comfy_utils
comfy.sd = comfy_sd
comfy.lora = comfy_lora
comfy.lora_convert = comfy_lora_convert
sys.modules["comfy"] = comfy
sys.modules["comfy.utils"] = comfy_utils
sys.modules["comfy.sd"] = comfy_sd
sys.modules["comfy.lora"] = comfy_lora
sys.modules["comfy.lora_convert"] = comfy_lora_convert

PACKAGE_NAME = "naiba_test_trigger_words"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = package

sha256_cache = types.ModuleType(f"{PACKAGE_NAME}.sha256_cache")
sha256_cache.get = lambda _name: None
sha256_cache.build_sha_candidates_index = lambda: {}
sha256_cache.check_entry_state = lambda _name, _path: "missing"
sys.modules[f"{PACKAGE_NAME}.sha256_cache"] = sha256_cache


def load_module(filename):
    module_path = ROOT / filename
    module_name = f"{PACKAGE_NAME}.{filename.removesuffix('.py')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


load_module("lora_preset_paths.py")
load_module("lora_load_utils.py")
VISUAL = load_module("visual_lora_loader.py")


def enabled_item(name, strength=1.0):
    return {
        "name": name,
        "strength_model": strength,
        "strength_clip": strength,
        "enabled": True,
    }


def execute(items, model=None, clip=None):
    if model is None:
        model = types.SimpleNamespace(model=object())
    if clip is None:
        clip = types.SimpleNamespace(cond_stage_model=object())
    return VISUAL.VisualLoRALoader().load_loras(model, json.dumps(items), clip)


def trigger_output(result):
    assert len(result) == 6, f"expected 6 outputs, got {len(result)}"
    return result[5]


# ── 测试用例 ─────────────────────────────────────────────────────────
def test_trigger_words_follow_node_order_and_dedupe():
    add_lora("alpha.safetensors", {"trigger_words": ["alpha tag", "shared"]})
    add_lora("beta.safetensors", {"trigger_words": ["beta tag", " shared "]})
    add_lora("disabled.safetensors", {"trigger_words": ["disabled tag"]})

    result = execute([
        enabled_item("alpha.safetensors"),
        {**enabled_item("disabled.safetensors"), "enabled": False},
        enabled_item("beta.safetensors"),
    ])

    assert trigger_output(result) == "alpha tag, shared, beta tag"


def test_trained_words_fallback_and_string_value():
    add_lora("fallback.safetensors", {"trained_words": "single tag"})
    add_lora("multiline.safetensors", {"trained_words": ["  multi\n line  tag  "]})

    result = execute([
        enabled_item("fallback.safetensors"),
        enabled_item("multiline.safetensors"),
    ])

    assert trigger_output(result) == "single tag, multi line tag"


def test_missing_or_invalid_metadata_is_skipped_without_failing_load():
    add_lora("no-meta.safetensors")
    add_lora("bad-json.safetensors", raw_metadata="{not valid json")

    result = execute([
        enabled_item("no-meta.safetensors"),
        enabled_item("bad-json.safetensors"),
    ])

    assert trigger_output(result) == ""


def test_enabled_flag_alone_decides_membership():
    add_lora("zero.safetensors", {"trigger_words": ["zero tag"]})
    add_lora("unwired.safetensors", {"trigger_words": ["unwired tag"]})

    zeroed = {**enabled_item("zero.safetensors", strength=0.0)}
    result = execute([zeroed])
    assert trigger_output(result) == "zero tag"

    # 未连接 MODEL/CLIP 时节点会跳过加载，但“已开启”的触发词仍应输出
    result = VISUAL.VisualLoRALoader().load_loras(
        None, json.dumps([enabled_item("unwired.safetensors")]), None
    )
    assert trigger_output(result) == "unwired tag"
    assert json.loads(result[2]) == []


def test_output_names_expose_trigger_words_at_end():
    assert VISUAL.VisualLoRALoader.RETURN_NAMES == (
        "model",
        "clip",
        "lora_names",
        "preset_json",
        "lora_info",
        "trigger_words",
    )
    assert VISUAL.VisualLoRALoader.RETURN_TYPES[-1] == "STRING"


def test_is_changed_tracks_metadata_content():
    name = add_lora("cache.safetensors", {"trigger_words": ["first"]})
    items = [enabled_item(name)]
    loader = VISUAL.VisualLoRALoader()

    first_signature = loader.IS_CHANGED(json.dumps(items))
    assert "cache.safetensors=" in first_signature

    add_lora(name, {"trigger_words": ["first", "second"]})
    second_signature = loader.IS_CHANGED(json.dumps(items))
    assert first_signature != second_signature

    # 无效 JSON 不应在 IS_CHANGED 抛错
    assert loader.IS_CHANGED("{").startswith("invalid-json:")


if __name__ == "__main__":
    test_trigger_words_follow_node_order_and_dedupe()
    test_trained_words_fallback_and_string_value()
    test_missing_or_invalid_metadata_is_skipped_without_failing_load()
    test_enabled_flag_alone_decides_membership()
    test_output_names_expose_trigger_words_at_end()
    test_is_changed_tracks_metadata_content()
    print("visual lora trigger words tests passed")
