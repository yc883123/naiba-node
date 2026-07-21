"""
List LoRA Loader 节点 - 读取visual lora loader输出的preset json，加载LoRA
UI设计参考：LoRA Loader (List Index)
输入：MODEL, CLIP, LoRA组合列表（纯连接端口，无文本框）
输出：MODEL, CLIP, LORA_NAMES（lora名字数组，供 civitai info reader / custom data reader 使用）
"""

import json
import folder_paths
import comfy.utils
import comfy.sd


class ListLoRALoader:
    """
    从preset JSON加载LoRA的节点
    读取visual lora loader输出的preset json，依次应用所有启用的LoRA
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL", {"tooltip": "输入的扩散模型"}),
                "clip": ("CLIP", {"tooltip": "输入的CLIP模型"}),
                "lora_list": ("STRING", {
                    "forceInput": True,
                    "tooltip": "LoRA组合列表（连接 visual lora loader 的 preset_json 输出）"
                }),
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "LORA_NAMES")
    FUNCTION = "load_loras_from_preset"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "List LoRA Loader 节点 - 读取visual lora loader输出的preset json。\n"
        "依次应用所有启用的LoRA，返回加载后的模型和CLIP，以及启用的LoRA名字数组（JSON字符串）。"
    )
    SEARCH_ALIASES = ["naiba", "preset lora", "json lora", "lora from json", "lora list", "list lora", "list lora loader"]

    def load_loras_from_preset(self, model, clip, lora_list):
        """
        读取JSON配置，依次应用所有启用的LoRA

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
            loras = json.loads(lora_list) if lora_list.strip() else []
        except (json.JSONDecodeError, TypeError):
            loras = []

        # 跟踪所有启用的LoRA名称
        enabled_lora_names = []

        # 依次应用每个启用的LoRA
        for lora_config in loras:
            # 检查是否启用
            if not lora_config.get("enabled", False):
                continue

            # 获取LoRA文件名
            lora_name = lora_config.get("name", "")
            if not lora_name:
                continue

            # 记录所有启用的LoRA名称
            enabled_lora_names.append(lora_name)

            # 获取权重
            strength_model = float(lora_config.get("strength_model", 1.0))
            strength_clip = float(lora_config.get("strength_clip", 1.0))

            # 如果权重都为0则跳过
            if strength_model == 0 and strength_clip == 0:
                continue

            try:
                # 加载LoRA文件
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)

                # 应用LoRA到模型和CLIP
                model, clip = comfy.sd.load_lora_for_models(
                    model, clip, lora, strength_model, strength_clip
                )
            except Exception as e:
                print(f"[ListLoRALoader] 加载LoRA '{lora_name}' 失败: {e}")
                continue

        # 输出所有启用的LoRA名称（JSON数组字符串），用于 civitai info reader / custom data reader
        lora_names_json = json.dumps(enabled_lora_names, ensure_ascii=False)
        return (model, clip, lora_names_json)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "ListLoRALoader": ListLoRALoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ListLoRALoader": "List LoRA Loader",
}
