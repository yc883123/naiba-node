"""
Preset Reader 节点
读取 presets/ 文件夹中的预设文件，输出原始 JSON 文本（不进行任何修改、删除或添加）。

参考 PresetFolderAligner 的 UI 设计，提供下拉选择框选择预设文件。
"""

import os
import json

# 预设存储目录（与 PresetFolderAligner 共享）
PRESETS_DIR = os.path.join(os.path.dirname(__file__), "presets")
os.makedirs(PRESETS_DIR, exist_ok=True)


def list_preset_files() -> "list[str]":
    """列出 presets/ 目录下的预设文件名（不含 .json 后缀），按名称排序。"""
    try:
        return sorted(f[:-5] for f in os.listdir(PRESETS_DIR) if f.endswith(".json"))
    except Exception as e:  # noqa: BLE001
        print(f"[PresetReader] 列出预设失败: {e}")
        return []


def _safe_preset_path(preset_name: str):
    """校验预设名安全性，返回合法的文件路径；非法返回 None。"""
    if not preset_name:
        return None
    name = preset_name.strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    if not name.endswith(".json"):
        name = name + ".json"
    file_path = os.path.realpath(os.path.join(PRESETS_DIR, name))
    presets_real = os.path.realpath(PRESETS_DIR)
    if not file_path.startswith(presets_real + os.sep) and file_path != presets_real:
        return None
    return file_path


class PresetReader:
    """
    读取预设文件并输出原始 JSON 文本的节点。

    用法：
    1. preset_name 下拉选择 presets/ 中的预设（点节点上的「刷新预设列表」可重新扫描）
    2. 输出原始 JSON 文本，不进行任何修改、删除或添加
    """

    @classmethod
    def INPUT_TYPES(cls):
        files = list_preset_files()
        if not files:
            files = ["(无预设文件)"]
        return {
            "required": {
                "preset_name": (files, {
                    "tooltip": "选择 presets 文件夹中的预设；点节点上的『刷新预设列表』按钮可重新扫描"
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("preset_json",)
    FUNCTION = "read_preset"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "读取预设文件并输出原始 JSON 文本。不进行任何修改、删除或添加。\n"
        "直接从 presets/ 文件夹读取预设文件内容。"
    )
    SEARCH_ALIASES = [
        "naiba", "preset reader", "读取预设", "预设读取", "预设文件",
        "preset read", "读预设"
    ]

    def read_preset(self, preset_name):
        """读取预设文件并返回原始 JSON 文本。"""

        if not preset_name or preset_name == "(无预设文件)":
            return ("[]",)

        file_path = _safe_preset_path(preset_name)
        if file_path is None:
            return (json.dumps({"error": f"非法的预设名: {preset_name}"}, ensure_ascii=False),)
        if not os.path.isfile(file_path):
            return (json.dumps({"error": f"预设文件不存在: {preset_name}"}, ensure_ascii=False),)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 验证是否为有效 JSON
            json.loads(content)
            return (content,)
        except json.JSONDecodeError as e:
            return (json.dumps({"error": f"预设文件 JSON 格式错误: {e}"}, ensure_ascii=False),)
        except Exception as e:  # noqa: BLE001
            return (json.dumps({"error": f"读取预设失败 {preset_name}: {e}"}, ensure_ascii=False),)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "PresetReader": PresetReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PresetReader": "Preset Reader (读取预设)",
}