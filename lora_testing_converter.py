"""
Lora Testing Preset Converter - 将 lora_testing 预设转换为 Multi LoRA Loader 格式
支持从下拉框选择预设或手动输入文件路径
"""

import os
import json
import folder_paths


class LoraTestingConverter:
    """
    读取 lora_testing 的预设文件，转换为 Multi LoRA Loader 可用的格式
    支持两种输入方式：下拉框选择预设 或 手动输入文件路径
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        # 获取 lora_testing 预设列表
        presets = cls._get_lora_testing_presets()
        
        return {
            "required": {
                "preset_source": (["从下拉框选择", "手动输入路径"], {
                    "default": "从下拉框选择",
                    "tooltip": "选择预设来源方式"
                }),
            },
            "optional": {
                "preset_name": (presets, {
                    "tooltip": "从下拉框选择 lora_testing 预设（当选择'从下拉框选择'时使用）"
                }),
                "file_path": ("STRING", {
                    "default": "",
                    "tooltip": "JSON 文件的完整路径（当选择'手动输入路径'时使用）"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("lora_data",)
    FUNCTION = "convert_preset"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "Lora Testing 预设转换器 - 读取 lora_testing 的预设文件，\n"
        "转换为 Multi LoRA Loader 可用的 JSON 格式。\n\n"
        "输入方式：\n"
        "1. 从下拉框选择：选择 lora_testing/presets 目录下的预设\n"
        "2. 手动输入路径：输入任意 JSON 文件的完整路径"
    )
    SEARCH_ALIASES = ["naiba", "lora testing", "convert", "import", "preset"]
    
    @staticmethod
    def _get_lora_testing_presets():
        """获取 lora_testing 的预设列表"""
        presets_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "lora_testing",
            "presets"
        )
        
        if not os.path.exists(presets_dir):
            return ["(无预设)"]
        
        try:
            files = [f[:-5] for f in os.listdir(presets_dir) if f.endswith('.json')]
            if not files:
                return ["(无预设)"]
            files.sort()
            return files
        except Exception:
            return ["(读取失败)"]
    
    def convert_preset(self, preset_source, preset_name="(无预设)", file_path=""):
        """读取并转换 lora_testing 预设"""
        
        # 确定输入文件路径
        if preset_source == "从下拉框选择":
            if preset_name in ("(无预设)", "(读取失败)"):
                return (json.dumps([]),)
            
            # 构建预设文件路径
            presets_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "lora_testing",
                "presets"
            )
            input_file = os.path.join(presets_dir, f"{preset_name}.json")
        else:
            # 手动输入路径
            input_file = file_path.strip()
            if not input_file:
                print("[LoraTestingConverter] 请输入文件路径")
                return (json.dumps([]),)
        
        # 安全检查
        if not os.path.exists(input_file):
            print(f"[LoraTestingConverter] 文件不存在: {input_file}")
            return (json.dumps([]),)
        
        try:
            # 读取 lora_testing 预设
            with open(input_file, 'r', encoding='utf-8') as f:
                lora_testing_data = json.load(f)
            
            # 转换为 Multi LoRA Loader 格式
            converted = self._convert_format(lora_testing_data)
            
            print(f"[LoraTestingConverter] 已转换 {len(converted)} 个 LoRA")
            
            return (json.dumps(converted, ensure_ascii=False),)
            
        except Exception as e:
            print(f"[LoraTestingConverter] 转换失败: {e}")
            return (json.dumps([]),)
    
    @staticmethod
    def _convert_format(lora_testing_data):
        """
        将 lora_testing 格式转换为 Multi LoRA Loader 格式
        
        lora_testing 格式:
        [
            {
                "dimension_index": 1,
                "lora_name_list": ["lora1.safetensors"],
                "min_weight": [0.5],
                "step": [0.1],
                "max_weight": [0.5],
                "enabled_list": [true],
                "cover_list": ["http://..."]
            }
        ]
        
        Multi LoRA Loader 格式:
        [
            {
                "name": "lora1.safetensors",
                "strength_model": 0.5,
                "strength_clip": 0.5,
                "enabled": true
            }
        ]
        """
        result = []
        
        if not isinstance(lora_testing_data, list):
            return result
        
        for dimension in lora_testing_data:
            if not isinstance(dimension, dict):
                continue
            
            lora_names = dimension.get("lora_name_list", [])
            min_weights = dimension.get("min_weight", [])
            enabled_list = dimension.get("enabled_list", [])
            
            # 遍历该维度中的所有 LoRA
            for i, lora_name in enumerate(lora_names):
                if not lora_name:
                    continue
                
                # 获取权重，使用 min_weight（固定权重时 min = max）
                strength = min_weights[i] if i < len(min_weights) else 1.0
                
                # 获取启用状态
                enabled = enabled_list[i] if i < len(enabled_list) else True
                
                result.append({
                    "name": lora_name,
                    "strength_model": strength,
                    "strength_clip": strength,
                    "enabled": enabled
                })
        
        return result


# 节点注册
NODE_CLASS_MAPPINGS = {
    "LoraTestingConverter": LoraTestingConverter
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoraTestingConverter": "Lora Testing Converter"
}
