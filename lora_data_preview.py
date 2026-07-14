"""
LoRA Data Preview 节点
从Civitai自动同步LoRA封面图片和元数据
预览节点，带lora names输出口，通过前端弹窗UI浏览和同步LoRA
"""

import json


class LoraDataPreview:
    """
    LoRA数据预览节点
    从Civitai自动同步LoRA封面图片和元数据
    通过弹窗界面浏览LoRA列表、查看元数据、执行同步操作
    输出所有启用的LoRA名称列表，可连接到Civitai Info Reader等节点
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
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("lora_names",)
    OUTPUT_NODE = True
    FUNCTION = "execute"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "LoRA数据预览节点 - 从Civitai自动同步封面图片和元数据。\n"
        "通过弹窗界面浏览LoRA列表、查看元数据、执行同步操作。\n"
        "输出所有启用的LoRA名称列表，可连接到Civitai Info Reader等节点。"
    )
    SEARCH_ALIASES = ["naiba", "lora preview", "civitai", "lora metadata"]
    
    def execute(self, lora_data="[]"):
        """
        解析LoRA配置，输出所有启用的LoRA名称列表
        """
        try:
            loras = json.loads(lora_data) if lora_data.strip() else []
        except (json.JSONDecodeError, TypeError):
            loras = []
        
        # 收集所有启用的LoRA名称
        enabled_lora_names = []
        for lora_config in loras:
            if not isinstance(lora_config, dict):
                continue
            if not lora_config.get("enabled", False):
                continue
            lora_name = lora_config.get("name", "")
            if lora_name:
                enabled_lora_names.append(lora_name)
        
        lora_names_json = json.dumps(enabled_lora_names, ensure_ascii=False)
        return (lora_names_json,)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "LoraDataPreview": LoraDataPreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoraDataPreview": "Lora Data Preview",
}
