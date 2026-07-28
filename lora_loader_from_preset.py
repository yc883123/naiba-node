"""
List LoRA Loader 节点 - 读取visual lora loader输出的preset json，加载LoRA
UI设计参考：LoRA Loader (List Index)
输入：MODEL, [CLIP(可选)], LoRA组合列表（纯连接端口，无文本框）
输出：MODEL, CLIP, LORA_NAMES（lora名字数组，供 civitai info reader / custom data reader 使用）
"""

import json
import folder_paths
import comfy.utils
import comfy.sd

from .lora_load_utils import (
    ensure_lora_has_compatible_patches,
    parse_lora_list,
    resolve_lora_name,
)


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
                "lora_list": ("STRING", {
                    "forceInput": True,
                    "tooltip": "LoRA组合列表（连接 visual lora loader 的 preset_json 输出）"
                }),
            },
            "optional": {
                "clip": ("CLIP", {"tooltip": "输入的CLIP模型（可选，不连接则只加载模型侧的LoRA）"}),
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

    def load_loras_from_preset(self, model, lora_list, clip=None):
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
        loras = parse_lora_list(lora_list, "lora_list")

        # 只记录真正成功应用的 LoRA；失败项汇总后让节点明确报错。
        loaded_lora_names = []
        load_failures = []

        # 依次应用每个启用的LoRA
        for preset_index, lora_config in enumerate(loras):
            if not isinstance(lora_config, dict):
                load_failures.append(f"第 {preset_index + 1} 项不是 LoRA 对象")
                continue
            # 检查是否启用
            if not lora_config.get("enabled", False):
                continue

            # 获取LoRA文件名
            configured_name = lora_config.get("name", "")
            if not configured_name:
                load_failures.append(f"第 {preset_index + 1} 项已启用但缺少 name")
                continue

            # 获取权重
            strength_model = float(lora_config.get("strength_model", 1.0))
            strength_clip = float(lora_config.get("strength_clip", 1.0))

            # 如果CLIP未传入（为None），则只加载模型侧，强制strength_clip为0
            if clip is None:
                strength_clip = 0

            # 如果权重都为0则跳过
            if strength_model == 0 and strength_clip == 0:
                continue

            try:
                lora_name = resolve_lora_name(lora_config)
                # 加载LoRA文件
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                ensure_lora_has_compatible_patches(
                    model, clip, lora, strength_model, strength_clip
                )

                # 应用LoRA到模型和CLIP
                model, clip = comfy.sd.load_lora_for_models(
                    model, clip, lora, strength_model, strength_clip
                )
                loaded_lora_names.append(lora_name)
            except Exception as e:
                load_failures.append(f"{configured_name}: {type(e).__name__}: {e}")
                continue

        if load_failures:
            details = "\n".join(f"- {item}" for item in load_failures)
            raise RuntimeError(
                f"List LoRA Loader 有 {len(load_failures)} 个 LoRA 未能应用：\n{details}"
            )

        # 仅输出成功应用的 LoRA 名称，用于下游节点判断实际加载结果。
        lora_names_json = json.dumps(loaded_lora_names, ensure_ascii=False)
        return (model, clip, lora_names_json)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "ListLoRALoader": ListLoRALoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ListLoRALoader": "List LoRA Loader",
}
