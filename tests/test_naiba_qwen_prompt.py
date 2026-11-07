"""Single-module contract tests with dependency stubs; no live inference.

Run with the portable distribution's python_embeded/python.exe.
"""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class _Input:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs


class _ImageInput(_Input):
    pass


class _AutogrowInput(_Input):
    pass


class _TemplatePrefix:
    def __init__(self, template, **kwargs):
        self.template = template
        self.kwargs = kwargs


class _Schema:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _ComfyNode:
    pass


def _load_optimizer():
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.models_dir = str(ROOT / "models")
    folder_paths.folder_names_and_paths = {}
    names = ["Qwen-Image-2.1-PE-T2I.gguf", "Qwen-Image-2.1-PE-I2I.gguf", "mmproj-Qwen.gguf"]
    folder_paths.get_filename_list = lambda category: list(names)
    folder_paths.get_folder_paths = lambda category: [str(ROOT / "models")]
    paths = {name: str(ROOT / "models" / name) for name in names}
    # The resolver deliberately returns a path outside its allowed root.
    paths["outside.gguf"] = str(ROOT / "outside.gguf")
    paths["sibling.gguf"] = str(ROOT / "models-other" / "sibling.gguf")
    folder_paths.get_full_path = lambda category, name: paths.get(name) if category == "LLM" else None

    routes = {}

    class _Routes:
        def get(self, path):
            return self._register("GET", path)

        def post(self, path):
            return self._register("POST", path)

        @staticmethod
        def _register(method, path):
            def decorator(fn):
                routes[(method, path)] = fn
                return fn
            return decorator

    server = types.ModuleType("server")
    server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=_Routes()))
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = types.SimpleNamespace(json_response=lambda data, **kwargs: (data, kwargs))
    comfy_api = types.ModuleType("comfy_api")
    comfy_api.__path__ = []
    latest = types.ModuleType("comfy_api.latest")
    latest.io = types.SimpleNamespace(
        ComfyNode=_ComfyNode, Schema=_Schema,
        String=types.SimpleNamespace(Input=_Input, Output=_Input),
        Combo=types.SimpleNamespace(Input=_Input),
        Boolean=types.SimpleNamespace(Input=_Input, Output=_Input),
        Int=types.SimpleNamespace(Input=_Input),
        Image=types.SimpleNamespace(Input=_ImageInput),
        Autogrow=types.SimpleNamespace(Input=_AutogrowInput, TemplatePrefix=_TemplatePrefix, Type=dict),
        ControlAfterGenerate=types.SimpleNamespace(fixed="fixed"),
        NodeOutput=lambda *values, **kwargs: values,
    )
    model_management = types.ModuleType("comfy.model_management")
    model_management.throw_exception_if_processing_interrupted = lambda: None
    model_management.get_torch_device = lambda: "cpu"
    model_management.free_memory = lambda *args: None
    comfy = types.ModuleType("comfy")
    comfy.__path__ = []
    comfy.model_management = model_management
    llama_cpp = types.ModuleType("llama_cpp")
    llama_cpp.Llama = object
    chat_format = types.ModuleType("llama_cpp.llama_chat_format")
    chat_format.Qwen35ChatHandler = object
    stubs = {
        "folder_paths": folder_paths, "server": server, "aiohttp": aiohttp,
        "comfy_api": comfy_api, "comfy_api.latest": latest,
        "comfy": comfy, "comfy.model_management": model_management,
        "llama_cpp": llama_cpp, "llama_cpp.llama_chat_format": chat_format,
    }
    spec = importlib.util.spec_from_file_location(
        "naiba_qwen_prompt_optimizer_test_target", ROOT / "naiba_qwen_prompt_optimizer.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, folder_paths, routes


optimizer, folder_paths, ROUTES = _load_optimizer()


class QwenPromptTests(unittest.TestCase):
    def test_v3_schema_and_mapping(self):
        node = optimizer.NaibaQwenPromptOptimizer
        self.assertTrue(issubclass(node, _ComfyNode))
        self.assertIs(optimizer.NODE_CLASS_MAPPINGS["NaibaQwenPromptOptimizer"], node)
        schema = node.define_schema()
        self.assertEqual(schema.node_id, "NaibaQwenPromptOptimizer")
        self.assertEqual(schema.display_name, "Naiba Qwen 提示词工作台")
        self.assertEqual(schema.category, "naiba-node")
        self.assertEqual([output.name for output in schema.outputs], ["prompt", "json", "是否反推"])
        inputs = {item.name: item for item in schema.inputs}
        self.assertEqual(inputs["用户提示词"].kwargs["default"], "")
        self.assertTrue(inputs["用户提示词"].kwargs["multiline"])
        images = inputs["图像"]
        self.assertIsInstance(images, _AutogrowInput)
        self.assertTrue(images.kwargs["optional"])
        template = images.kwargs["template"]
        self.assertIsInstance(template, _TemplatePrefix)
        self.assertIsInstance(template.template, _ImageInput)
        self.assertEqual(template.kwargs, {"prefix": "图像_", "min": 0, "max": 100})
        self.assertEqual(inputs["文生图模型"].kwargs["default"], "Qwen-Image-2.1-PE-T2I.gguf")
        self.assertEqual(inputs["图生图模型"].kwargs["default"], "Qwen-Image-2.1-PE-I2I.gguf")
        self.assertEqual(inputs["视觉模型"].kwargs["options"], ["mmproj-Qwen.gguf"])
        self.assertEqual(inputs["输出语言"].kwargs["options"], ["自动", "中文", "English"])
        self.assertFalse(inputs["透明背景"].kwargs["default"])
        self.assertEqual(inputs["种子值"].kwargs["control_after_generate"], "fixed")
        self.assertEqual(inputs["种子值"].kwargs["default"], 0)
        self.assertNotIn("种子模式", inputs)
        self.assertNotIn("卸载模型", inputs)

    def test_routes_and_model_path_containment(self):
        self.assertIn(("GET", "/naiba/qwen_prompt_optimizer/llama_status"), ROUTES)
        self.assertIn(("POST", "/naiba/qwen_prompt_optimizer/install_llama"), ROUTES)
        self.assertIn("LLM", folder_paths.folder_names_and_paths)
        self.assertEqual(Path(optimizer._model_path("mmproj-Qwen.gguf", True)), ROOT / "models" / "mmproj-Qwen.gguf")
        self.assertEqual(Path(optimizer._model_path("Qwen-Image-2.1-PE-T2I.gguf", False)), ROOT / "models" / "Qwen-Image-2.1-PE-T2I.gguf")
        for name, vision in (("outside.gguf", False), ("sibling.gguf", False), ("missing.gguf", False),
                             ("mmproj-Qwen.gguf", False), ("Qwen-Image-2.1-PE-T2I.gguf", True)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                optimizer._model_path(name, vision)

    def test_templates_and_prompt_helpers(self):
        t2i, edit, reverse = optimizer.t2i_prompt(), optimizer.edit_prompt(), optimizer.reverse_prompt()
        self.assertIn("rewritten_prompt", t2i)
        self.assertIn("wh_ratio", t2i)
        self.assertIn("ratio_follow", edit)
        self.assertTrue(reverse.startswith(t2i))
        self.assertIn("Reverse-prompting mode", reverse)
        self.assertEqual(optimizer.select_language("自动", "一只猫"), "Chinese")
        self.assertEqual(optimizer.select_language("自动", "a cat"), "English")
        self.assertEqual(optimizer.select_language("自动", "", True), "Chinese")
        self.assertEqual(optimizer.select_language("English", "你好", True), "English")
        system = optimizer.build_system_prompt(t2i, "English", True, True)
        self.assertTrue(system.startswith(t2i))
        self.assertIn("OUTPUT LANGUAGE LOCK", system)
        self.assertIn("TRANSPARENT BACKGROUND OVERRIDE", system)
        self.assertIn("never add ratio_follow", system)
        user = optimizer.build_user_turn("换成雪山", [object(), object()], "Chinese", False, False)
        self.assertIn("<image1>", user)
        self.assertIn("<image2>", user)
        self.assertIn("换成雪山", user)
        parsed = optimizer.extract_json('<think>thinking</think>```json\n{"rewritten_prompt":"cat","wh_ratio":"1:1"}\n```')
        self.assertEqual(optimizer.validate_result(parsed, False), {"rewritten_prompt": "cat", "wh_ratio": "1:1"})
        for bad in ({"rewritten_prompt": "", "wh_ratio": "1:1"}, {"rewritten_prompt": "cat"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                optimizer.validate_result(bad, False)

    def test_collect_images_has_no_custom_frame_cap(self):
        torch = optimizer.torch

        self.assertEqual(optimizer.collect_images({}), [])
        frames = optimizer.collect_images({f"图像_{i:03d}": torch.zeros(1, 2, 2, 3) for i in range(1, 12)})
        self.assertEqual(len(frames), 11)
        # Socket count does not cap batch-expanded image frames.
        self.assertEqual(len(optimizer.collect_images({"图像_001": torch.zeros(101, 2, 2, 3)})), 101)
        frames = optimizer.collect_images({"图像_010": torch.ones(1, 2, 2, 3), "图像_002": torch.zeros(2, 2, 2, 3)})
        self.assertEqual([frame[0, 0, 0].item() for frame in frames], [0, 0, 1])

    def test_transparency_keeps_subject_clause(self):
        value = optimizer.append_transparency("A red apple on a white background, with a small green leaf", True)
        self.assertTrue(value.startswith(optimizer.TRANSPARENT_HEAD))
        self.assertTrue(value.endswith(optimizer.TRANSPARENT_TAIL))
        self.assertNotIn("white background", value)
        self.assertIn("red apple", value)
        self.assertIn("small green leaf", value)
        quoted = optimizer.append_transparency('A can with "BLUE BACKGROUND" label, blue background', True)
        self.assertIn('"BLUE BACKGROUND"', quoted)
        self.assertEqual(optimizer.append_transparency("a cat", False), "a cat")

    def test_json_retry_and_finally_cleanup(self):
        for failure in (None, "encoding", "invalid_retry"):
            with self.subTest(failure=failure):
                calls, closed, resets, streams_closed = [], [], [], []
                result = json.dumps({"rewritten_prompt": "subject", "wh_ratio": "1:1", "ratio_follow": "true"})
                replies = iter(["invalid", "invalid" if failure == "invalid_retry" else result])

                class Stream:
                    def __iter__(self):
                        yield {"choices": [{"delta": {"content": next(replies)}}]}

                    def close(self):
                        streams_closed.append(True)

                class Llama:
                    def __init__(self, **kwargs):
                        pass

                    def create_chat_completion(self, **kwargs):
                        calls.append(kwargs)
                        return Stream()

                    def reset(self):
                        resets.append(True)

                    def close(self):
                        closed.append("llm")

                class Handler:
                    def __init__(self, **kwargs):
                        pass

                    def close(self):
                        closed.append("handler")

                def encode(frame, max_side):
                    if failure == "encoding":
                        raise RuntimeError("encode failed")
                    return "data:image/jpeg;base64,test"

                # Real file only supplies a byte count; stubbed constructors never read weights.
                with patch.object(optimizer, "Llama", Llama), patch.object(optimizer, "Qwen35ChatHandler", Handler), patch.object(
                    optimizer, "_image_data_url", encode
                ), patch.object(optimizer.torch.cuda, "is_available", return_value=False):
                    kwargs = dict(model_path=__file__, mmproj_path=__file__, system_prompt="system",
                                  user_prompt="prompt", images=[object()], edit_mode=True, seed=7)
                    if failure == "encoding":
                        with self.assertRaisesRegex(RuntimeError, "encode failed"):
                            optimizer.complete(**kwargs)
                    elif failure == "invalid_retry":
                        with self.assertRaises(ValueError):
                            optimizer.complete(**kwargs)
                    else:
                        self.assertEqual(optimizer.complete(**kwargs)["ratio_follow"], "true")
                self.assertEqual(closed, ["llm", "handler"])
                if failure == "encoding":
                    self.assertEqual(calls, [])
                else:
                    self.assertEqual(len(calls), 2)
                    self.assertNotIn("response_format", calls[0])
                    self.assertEqual(calls[1]["response_format"], {"type": "json_object"})
                    self.assertEqual(calls[1]["seed"], 7)
                    self.assertEqual(resets, [True])
                    self.assertEqual(streams_closed, [True, True])


if __name__ == "__main__":
    unittest.main(verbosity=2)
