import importlib.util
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


folder_paths = types.ModuleType("folder_paths")


def get_full_path_or_raise(_category, name):
    if name == "missing.safetensors":
        raise FileNotFoundError(f"LoRA not found: {name}")
    return name


folder_paths.get_full_path_or_raise = get_full_path_or_raise
folder_paths.get_full_path = lambda _category, name: (
    None if name in ("missing.safetensors", "old-path.safetensors") else name
)
sys.modules["folder_paths"] = folder_paths

comfy = types.ModuleType("comfy")
comfy_utils = types.ModuleType("comfy.utils")
comfy_sd = types.ModuleType("comfy.sd")
comfy_lora = types.ModuleType("comfy.lora")
comfy_lora_convert = types.ModuleType("comfy.lora_convert")


class FakeModel:
    model = object()


class FakeClip:
    cond_stage_model = object()


class FakeTensor:
    def __init__(self, shape):
        self.shape = shape


class FakeMiniMaxInner:
    model_config = types.SimpleNamespace(unet_config={"image_model": "minimax_h3"})

    def state_dict(self):
        return {
            "diffusion_model.blocks.0.attn.qkv_proj.weight": FakeTensor((300, 100)),
            "diffusion_model.blocks.0.adaln_proj.linear.weight": FakeTensor((96768, 8)),
        }


class FakeMiniMaxModel:
    model = FakeMiniMaxInner()


def load_torch_file(path, safe_load=True):
    assert safe_load is True
    return {"path": path}


def load_lora_for_models(model, clip, lora, strength_model, strength_clip):
    if lora["path"] == "incompatible.safetensors":
        raise ValueError("incompatible LoRA")
    return model, clip


comfy_lora.model_lora_keys_unet = lambda _model, mapping: {**mapping, "model_key": "model.patch"}
comfy_lora.model_lora_keys_clip = lambda _clip, mapping: {**mapping, "clip_key": "clip.patch"}
comfy_lora.load_lora = lambda lora, _mapping, log_missing=False: (
    {} if lora["path"] == "unmatched.safetensors" else {"model.patch": object()}
)
comfy_lora_convert.convert_lora = lambda lora: lora


comfy_utils.load_torch_file = load_torch_file
comfy_sd.load_lora_for_models = load_lora_for_models
comfy.utils = comfy_utils
comfy.sd = comfy_sd
comfy.lora = comfy_lora
comfy.lora_convert = comfy_lora_convert
sys.modules["comfy"] = comfy
sys.modules["comfy.utils"] = comfy_utils
sys.modules["comfy.sd"] = comfy_sd
sys.modules["comfy.lora"] = comfy_lora
sys.modules["comfy.lora_convert"] = comfy_lora_convert

PACKAGE_NAME = "naiba_test_loader_tests"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = package

sha256_cache = types.ModuleType(f"{PACKAGE_NAME}.sha256_cache")
sha256_cache.build_sha_candidates_index = lambda: {
    "a" * 64: ["local-path.safetensors", "old-path.safetensors"]
}
sha256_cache.check_entry_state = lambda name, _path: (
    "current" if name == "local-path.safetensors" else "missing"
)
sys.modules[f"{PACKAGE_NAME}.sha256_cache"] = sha256_cache


def load_module(filename):
    module_path = ROOT / filename
    module_name = f"{PACKAGE_NAME}.{filename.removesuffix('.py')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


MODULES = {
    "multi": load_module("multi_lora_loader.py"),
    "only": load_module("multi_lora_loader_only_model.py"),
    "visual": load_module("visual_lora_loader.py"),
    "list": load_module("lora_loader_from_preset.py"),
}
LOAD_UTILS = sys.modules[f"{PACKAGE_NAME}.lora_load_utils"]


def execute_loader(kind, items):
    payload = json.dumps(items)
    if kind == "multi":
        return MODULES[kind].MultiLoraLoader().load_loras(FakeModel(), payload, FakeClip())
    if kind == "only":
        return MODULES[kind].MultiLoraLoaderOnlyModel().load_loras(FakeModel(), payload)
    if kind == "visual":
        return MODULES[kind].VisualLoRALoader().load_loras(FakeModel(), payload, FakeClip())
    return MODULES[kind].ListLoRALoader().load_loras_from_preset(FakeModel(), payload, FakeClip())


def loaded_names(kind, result):
    return json.loads(result[1] if kind == "only" else result[2])


def enabled_item(name, strength=1.0):
    return {
        "name": name,
        "strength_model": strength,
        "strength_clip": strength,
        "enabled": True,
    }


def test_all_loaders_only_output_successfully_applied_names():
    for kind in MODULES:
        result = execute_loader(kind, [
            enabled_item("good.safetensors"),
            {**enabled_item("disabled.safetensors"), "enabled": False},
        ])
        assert loaded_names(kind, result) == ["good.safetensors"]


def test_all_loaders_raise_visible_error_for_missing_enabled_lora():
    for kind in MODULES:
        try:
            execute_loader(kind, [enabled_item("missing.safetensors")])
        except RuntimeError as error:
            message = str(error)
            assert "missing.safetensors" in message
            assert "未能应用" in message
        else:
            raise AssertionError(f"{kind} silently ignored a missing LoRA")


def test_zero_weight_missing_lora_is_intentionally_skipped():
    for kind in MODULES:
        result = execute_loader(kind, [enabled_item("missing.safetensors", strength=0.0)])
        assert loaded_names(kind, result) == []


def test_apply_failure_is_reported_after_file_resolution():
    for kind in MODULES:
        try:
            execute_loader(kind, [enabled_item("incompatible.safetensors")])
        except RuntimeError as error:
            message = str(error)
            assert "incompatible.safetensors" in message
            assert "incompatible LoRA" in message
        else:
            raise AssertionError(f"{kind} silently ignored an incompatible LoRA")


def test_no_compatible_patch_keys_is_reported_as_not_applied():
    for kind in MODULES:
        try:
            execute_loader(kind, [enabled_item("unmatched.safetensors")])
        except RuntimeError as error:
            message = str(error)
            assert "unmatched.safetensors" in message
            assert "兼容 LoRA 键" in message
        else:
            raise AssertionError(f"{kind} accepted a LoRA with no compatible keys")


def test_invalid_json_is_not_silently_treated_as_an_empty_preset():
    for kind in MODULES:
        try:
            if kind == "multi":
                MODULES[kind].MultiLoraLoader().load_loras(FakeModel(), "{", FakeClip())
            elif kind == "only":
                MODULES[kind].MultiLoraLoaderOnlyModel().load_loras(FakeModel(), "{")
            elif kind == "visual":
                MODULES[kind].VisualLoRALoader().load_loras(FakeModel(), "{", FakeClip())
            else:
                MODULES[kind].ListLoRALoader().load_loras_from_preset(FakeModel(), "{", FakeClip())
        except ValueError as error:
            assert "不是有效 JSON" in str(error)
        else:
            raise AssertionError(f"{kind} silently accepted invalid JSON")


def test_enabled_item_without_name_is_reported():
    for kind in MODULES:
        try:
            execute_loader(kind, [{"enabled": True}])
        except RuntimeError as error:
            assert "已启用但缺少 name" in str(error)
        else:
            raise AssertionError(f"{kind} silently skipped an enabled nameless item")


def test_all_loaders_fall_back_from_missing_path_to_unique_current_sha_candidate():
    for kind in MODULES:
        item = {**enabled_item("old-path.safetensors"), "sha256": "a" * 64}
        result = execute_loader(kind, [item])
        assert loaded_names(kind, result) == ["local-path.safetensors"]


def test_native_minimax_keys_are_normalized_and_incompatible_adaln_is_removed():
    lora = {
        "blocks.0.attn.qkv_proj.lora_A.weight": FakeTensor((16, 100)),
        "blocks.0.attn.qkv_proj.lora_B.weight": FakeTensor((300, 16)),
        "blocks.0.adaln_proj.linear.lora_A.weight": FakeTensor((16, 2688)),
        "blocks.0.adaln_proj.linear.lora_B.weight": FakeTensor((96768, 16)),
    }

    prepared = LOAD_UTILS.prepare_lora_for_models(FakeMiniMaxModel(), lora)

    assert "diffusion_model.blocks.0.attn.qkv_proj.lora_A.weight" in prepared
    assert "diffusion_model.blocks.0.attn.qkv_proj.lora_B.weight" in prepared
    assert "blocks.0.attn.qkv_proj.lora_A.weight" not in prepared
    assert "diffusion_model.blocks.0.adaln_proj.linear.lora_A.weight" not in prepared
    assert "diffusion_model.blocks.0.adaln_proj.linear.lora_B.weight" not in prepared


def test_native_minimax_adaln_is_kept_when_full_model_shapes_match():
    class FullMiniMaxInner(FakeMiniMaxInner):
        def state_dict(self):
            state = super().state_dict()
            state["diffusion_model.blocks.0.adaln_proj.linear.weight"] = FakeTensor((96768, 2688))
            return state

    full_model = types.SimpleNamespace(model=FullMiniMaxInner())
    lora = {
        "blocks.0.adaln_proj.linear.lora_A.weight": FakeTensor((16, 2688)),
        "blocks.0.adaln_proj.linear.lora_B.weight": FakeTensor((96768, 16)),
    }

    prepared = LOAD_UTILS.prepare_lora_for_models(full_model, lora)

    assert "diffusion_model.blocks.0.adaln_proj.linear.lora_A.weight" in prepared
    assert "diffusion_model.blocks.0.adaln_proj.linear.lora_B.weight" in prepared


if __name__ == "__main__":
    test_all_loaders_only_output_successfully_applied_names()
    test_all_loaders_raise_visible_error_for_missing_enabled_lora()
    test_zero_weight_missing_lora_is_intentionally_skipped()
    test_apply_failure_is_reported_after_file_resolution()
    test_no_compatible_patch_keys_is_reported_as_not_applied()
    test_invalid_json_is_not_silently_treated_as_an_empty_preset()
    test_enabled_item_without_name_is_reported()
    test_all_loaders_fall_back_from_missing_path_to_unique_current_sha_candidate()
    test_native_minimax_keys_are_normalized_and_incompatible_adaln_is_removed()
    test_native_minimax_adaln_is_kept_when_full_model_shapes_match()
    print("lora loader failure tests passed")
