"""
Multi LoRA Loader 节点 - 基于官方LoraLoader扩展
支持动态添加/删除Lora，带独立开关和权重控制
前端UI由 web/extensions/multi_lora_loader.js 提供
"""

import json
import folder_paths
import comfy.utils
import comfy.sd


class MultiLoraLoader:
    """
    多Lora加载器节点
    默认只显示模型和CLIP接口，通过前端JS扩展提供"+ Add Lora"动态UI
    所有Lora配置以JSON格式存储在隐藏的lora_data字段中
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL", {"tooltip": "输入的扩散模型"}),
                "lora_data": ("STRING", {
                    "default": "[]",
                    "multiline": True,
                    "tooltip": "Lora配置JSON数据（由前端UI自动管理，无需手动编辑）"
                }),
            },
            "optional": {
                "clip": ("CLIP", {"tooltip": "输入的CLIP模型（可选，不连接时仅加载模型部分）"}),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("model", "clip", "lora_names")
    FUNCTION = "load_loras"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "多Lora加载器节点 - 默认界面简洁，点击 '+ Add Lora' 按钮可随时添加Lora。\n"
        "每个Lora都有独立的启用开关和M/C权重控制（M=Model, C=CLIP）。\n"
        "可以随时添加或删除Lora，配置会自动保存到工作流中。"
    )
    SEARCH_ALIASES = ["naiba", "multi lora", "lora stack", "lora bundle", "lora group", "add lora"]

    def load_loras(self, model, lora_data="[]", clip=None):
        """
        读取JSON配置，依次应用所有启用的Lora

        JSON格式示例:
        [
            {
                "name": "some_lora.safetensors",
                "strength_model": 1.0,
                "strength_clip": 1.0,
                "enabled": true
            }
        ]
        """
        # 解析JSON配置
        try:
            loras = json.loads(lora_data) if lora_data.strip() else []
        except (json.JSONDecodeError, TypeError):
            loras = []

        # 跟踪所有启用的LoRA名称
        enabled_lora_names = []

        # 依次应用每个启用的Lora
        for lora_config in loras:
            # 检查是否启用
            if not lora_config.get("enabled", False):
                continue

            # 获取Lora文件名
            lora_name = lora_config.get("name", "")
            if not lora_name:
                continue

            # 记录所有启用的LoRA名称
            enabled_lora_names.append(lora_name)

            # 获取权重
            strength_model = float(lora_config.get("strength_model", 1.0))
            strength_clip = float(lora_config.get("strength_clip", 1.0))

            # 如果CLIP为None，则强制strength_clip为0
            if clip is None:
                strength_clip = 0

            # 权重都为0则跳过
            if strength_model == 0 and strength_clip == 0:
                continue

            try:
                # 加载Lora文件
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)

                # 应用Lora到模型和CLIP（如果CLIP为None，则只加载模型部分）
                model, clip = comfy.sd.load_lora_for_models(
                    model, clip, lora, strength_model, strength_clip
                )
            except Exception as e:
                print(f"[MultiLoraLoader] 加载Lora '{lora_name}' 失败: {e}")
                continue

        # 始终输出已启用的LoRA名称列表
        lora_names_json = json.dumps(enabled_lora_names, ensure_ascii=False)

        return (model, clip, lora_names_json)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "MultiLoraLoader": MultiLoraLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MultiLoraLoader": "Multi LoRA Loader",
}