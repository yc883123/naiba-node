"""Civitai Info Reader custom_prompt 输出测试（独立脚本，无 pytest 依赖）。

运行：python tests/test_civitai_info_reader_custom_prompt.py

覆盖场景：多 LoRA 合并时，某个 LoRA 没有 .civitai.info.json、
但有 .custom.info.json（自定义提示词），custom_prompt 仍应输出。
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


def add_lora(name, civitai_metadata=None, custom_metadata=None):
    """在临时目录创建假 LoRA 文件及可选的元数据/自定义数据文件。"""
    path = LORA_DIR / name
    path.write_bytes(b"fake lora")
    LORA_PATHS[name] = str(path)
    base = str(path.with_suffix(""))
    if civitai_metadata is not None:
        Path(base + ".civitai.info.json").write_text(
            json.dumps(civitai_metadata, ensure_ascii=False), encoding="utf-8"
        )
    if custom_metadata is not None:
        Path(base + ".custom.info.json").write_text(
            json.dumps(custom_metadata, ensure_ascii=False), encoding="utf-8"
        )
    return name


# ── 伪造 ComfyUI 运行环境 ─────────────────────────────────────────────
folder_paths = types.ModuleType("folder_paths")
folder_paths.get_full_path = lambda _category, name: LORA_PATHS.get(name)
sys.modules["folder_paths"] = folder_paths

# civitai_info_reader 顶层会 import PIL/numpy/torch，这里用最小桩替代，
# 保证 HAS_IMAGE_DEPS 为真且多 LoRA 分支的 torch.cat 可用。
PIL = types.ModuleType("PIL")
PIL_Image = types.ModuleType("PIL.Image")
PIL.Image = PIL_Image
sys.modules["PIL"] = PIL
sys.modules["PIL.Image"] = PIL_Image

numpy = types.ModuleType("numpy")
sys.modules["numpy"] = numpy

torch = types.ModuleType("torch")
torch.float32 = "float32"
torch.zeros = lambda shape, dtype=None: object()
torch.cat = lambda tensors, dim=0: object()
sys.modules["torch"] = torch

spec = importlib.util.spec_from_file_location(
    "civitai_info_reader_test", ROOT / "civitai_info_reader.py"
)
MODULE = importlib.util.module_from_spec(spec)
sys.modules["civitai_info_reader_test"] = MODULE
spec.loader.exec_module(MODULE)


def custom_prompt_output(result):
    assert len(result) == 10, f"expected 10 outputs, got {len(result)}"
    return result[9]


# ── 测试用例 ─────────────────────────────────────────────────────────
def test_multi_lora_custom_prompt_without_civitai_metadata():
    add_lora(
        "with-meta.safetensors",
        civitai_metadata={"model_name": "WithMeta"},
        custom_metadata={"custom_prompt": "meta custom"},
    )
    add_lora(
        "no-meta.safetensors",
        custom_metadata={"custom_prompt": "moss custom"},
    )

    result = MODULE.CivitaiInfoReader().read_info(
        json.dumps(["with-meta.safetensors", "no-meta.safetensors"])
    )

    assert custom_prompt_output(result) == (
        "[1] WithMeta: meta custom\n[2] no-meta.safetensors: moss custom"
    )


def test_multi_lora_without_custom_prompt_stays_empty():
    add_lora("plain-a.safetensors", civitai_metadata={"model_name": "PlainA"})
    add_lora("plain-b.safetensors", custom_metadata={"custom_prompt": "b prompt"})

    result = MODULE.CivitaiInfoReader().read_info(
        json.dumps(["plain-a.safetensors", "plain-b.safetensors"])
    )

    assert custom_prompt_output(result) == "[2] plain-b.safetensors: b prompt"


def test_single_lora_custom_prompt_without_civitai_metadata():
    add_lora("single-no-meta.safetensors", custom_metadata={"custom_prompt": "single custom"})

    result = MODULE.CivitaiInfoReader().read_info("single-no-meta.safetensors")

    assert custom_prompt_output(result) == "single custom"


if __name__ == "__main__":
    test_multi_lora_custom_prompt_without_civitai_metadata()
    test_multi_lora_without_custom_prompt_stays_empty()
    test_single_lora_custom_prompt_without_civitai_metadata()
    print("civitai info reader custom prompt tests passed")
