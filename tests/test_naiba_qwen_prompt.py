"""Naiba Qwen 提示词工作台 - 不依赖 ComfyUI 运行时的纯函数自测(独立脚本,无 pytest 依赖)。

运行：python_embeded\\python.exe tests\\test_naiba_qwen_prompt.py
"""
import ast
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

# ── 虚拟包加载(与 test_visual_lora_trigger_words.py 同套路,让相对导入生效) ──
PACKAGE_NAME = "naiba_test_qwen_prompt"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = package


def load_module(filename):
    module_path = ROOT / filename
    module_name = f"{PACKAGE_NAME}.{filename.removesuffix('.py')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


templates = load_module("naiba_qwen_prompt_templates.py")
rt = load_module("naiba_qwen_prompt_runtime.py")


def test_templates():
    t2i = templates.t2i_prompt()
    edit = templates.edit_prompt()
    reverse = templates.reverse_prompt()
    assert len(t2i) > 5000 and "rewritten_prompt" in t2i and "wh_ratio" in t2i
    assert "ratio_follow" in edit
    # 反推 = 文生图模板 + 反推补充规则
    assert reverse.startswith(t2i.split("\n")[0]) and "Reverse-prompting mode" in reverse
    assert "watermarks" in reverse.lower()
    print("ok templates")


def test_select_language():
    assert rt.select_language("中文", "hello") == "Chinese"
    assert rt.select_language("English", "你好") == "English"
    assert rt.select_language("自动", "一只猫") == "Chinese"
    assert rt.select_language("自动", "a cat") == "English"
    assert rt.select_language("自动", "") == "Chinese"
    # 反推模式自动档固定中文,显式选择优先
    assert rt.select_language("自动", "anything", reverse_mode=True) == "Chinese"
    assert rt.select_language("English", "你好", reverse_mode=True) == "English"
    print("ok select language")


def test_prompts_build():
    system = rt.build_system_prompt(templates.t2i_prompt(), "Chinese", transparent=False, reverse_mode=False)
    assert system.startswith(templates.t2i_prompt())
    assert "OUTPUT LANGUAGE LOCK" in system and "使用中文" in system
    system_t = rt.build_system_prompt(templates.t2i_prompt(), "English", transparent=True)
    assert "TRANSPARENT BACKGROUND OVERRIDE" in system_t
    system_r = rt.build_system_prompt(templates.reverse_prompt(), "Chinese", transparent=False, reverse_mode=True)
    assert "never add ratio_follow" in system_r

    user = rt.build_user_turn("把背景换成雪山", [object()] * 2, "Chinese", False, False)
    assert "<image1>" in user and "<image2>" in user and "把背景换成雪山" in user
    user_rev = rt.build_user_turn("", [object()], "Chinese", False, True)
    assert "reverse-prompting rules" in user_rev
    user_t = rt.build_user_turn("a cat", [], "English", True, False)
    assert "transparent background" in user_t and "a cat" in user_t
    print("ok prompts build")


def test_extract_and_validate():
    data = rt.extract_json('```json\n{"rewritten_prompt":"a cat","wh_ratio":"1:1"}\n```')
    assert data["rewritten_prompt"] == "a cat"
    data2 = rt.extract_json('<think>hmm</think>前置说明 {"rewritten_prompt":"x","wh_ratio":""}')
    assert data2["rewritten_prompt"] == "x"
    fields = rt.validate_result(data, edit_mode=False)
    assert "ratio_follow" not in fields
    fields2 = rt.validate_result({"rewritten_prompt": "x", "wh_ratio": "16:9", "ratio_follow": "true"}, edit_mode=True)
    assert fields2["ratio_follow"] == "true"
    for bad in ('{"rewritten_prompt":"","wh_ratio":"1:1"}', "not json at all"):
        try:
            if bad.startswith("{"):
                rt.validate_result(rt.extract_json(bad), edit_mode=False)
            else:
                rt.extract_json(bad)
            raise AssertionError(f"应报错：{bad}")
        except ValueError:
            pass
    print("ok extract and validate")


def test_collect_images():
    import torch

    batch = torch.rand(2, 8, 8, 3)
    assert len(rt.collect_images({"图像_01": batch, "图像_02": None, "其他": 1})) == 2
    assert len(rt.collect_images({"image_05": torch.rand(1, 8, 8, 3)})) == 1
    try:
        rt.collect_images({f"图像_{i:02d}": torch.rand(1, 4, 4, 3) for i in range(1, 12)})
        raise AssertionError("超过10张应报错")
    except ValueError:
        pass
    print("ok collect images")


def test_transparency():
    value = rt.append_transparency("a red apple on a white background", True)
    assert value.startswith(rt.TRANSPARENT_HEAD) and value.endswith(rt.TRANSPARENT_TAIL)
    assert "white background" not in value
    # 引号内画面文字不动
    kept = rt.append_transparency('a can with "BLUE BACKGROUND" label, blue background', True)
    assert '"BLUE BACKGROUND"' in kept
    # 不开启时原样返回
    assert rt.append_transparency("a cat", False) == "a cat"
    print("ok transparency")


def test_runtime_states():
    rt.close_model()
    assert rt._slot.llm is None
    plan = rt._context_plan(1, True)
    assert plan == (16384, 1536)
    assert rt._context_plan(0, False) == (8192, 0)
    assert rt._context_plan(3, False) == (16384, 512)
    assert rt._context_plan(6, False) == (32768, 256)
    print("ok runtime states")


def test_node_full_import_with_stubs():
    """桩替 folder_paths/server,真实导入节点模块:验证路由注册、LLM 目录注册与 INPUT_TYPES。"""
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.models_dir = str(ROOT / "_fake_models")
    folder_paths.folder_names_and_paths = {}
    folder_paths.get_filename_list = lambda category: []
    folder_paths.get_full_path = lambda category, name: None

    class _Routes:
        def get(self, _path):
            return lambda fn: fn

        def post(self, _path):
            return lambda fn: fn

    server = types.ModuleType("server")
    server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=_Routes()))
    sys.modules.setdefault("folder_paths", folder_paths)
    sys.modules.setdefault("server", server)

    optimizer = load_module("naiba_qwen_prompt_optimizer.py")
    assert "NaibaQwenPromptOptimizer" in optimizer.NODE_CLASS_MAPPINGS
    assert optimizer.NODE_DISPLAY_NAME_MAPPINGS["NaibaQwenPromptOptimizer"] == "Naiba Qwen 提示词工作台"
    assert "LLM" in folder_paths.folder_names_and_paths
    inputs = optimizer.NaibaQwenPromptOptimizer.INPUT_TYPES()
    assert inputs["required"]["文生图模型"][0] == ["未找到 GGUF 模型"]
    assert inputs["required"]["视觉模型"][0] == ["未找到 mmproj GGUF 模型"]
    assert "图像_01" in inputs["optional"] and "图像_10" in inputs["optional"]
    assert optimizer.NaibaQwenPromptOptimizer.CATEGORY == "naiba-node"
    assert optimizer.NaibaQwenPromptOptimizer.RETURN_TYPES == ("STRING", "STRING", "BOOLEAN")
    # 依赖状态函数可用
    status = optimizer.llama_dependency_status()
    assert "needs_install" in status and "supported" in status
    print("ok node full import with stubs")


def test_js_contract():
    """JS 与 Python 的接口契约:节点类名、路由路径、widget 名。"""
    js = (ROOT / "js" / "naiba_qwen_prompt_optimizer.js").read_text(encoding="utf-8")
    assert 'NaibaQwenPromptOptimizer' in js
    for route in ("/naiba/qwen_prompt_optimizer/llama_status", "/naiba/qwen_prompt_optimizer/install_llama"):
        assert route in js
    for name in ("用户提示词", "输出语言", "种子值", "种子模式"):
        assert name in js
    source = (ROOT / "naiba_qwen_prompt_optimizer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    routes = [
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("get", "post")
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "routes"
    ]
    assert "get" in routes and "post" in routes
    print("ok js contract")


if __name__ == "__main__":
    test_templates()
    test_select_language()
    test_prompts_build()
    test_extract_and_validate()
    test_collect_images()
    test_transparency()
    test_runtime_states()
    test_node_full_import_with_stubs()
    test_js_contract()
    print("ALL TESTS PASSED")
