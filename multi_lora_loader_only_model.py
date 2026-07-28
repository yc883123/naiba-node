"""
Multi LoRA Loader (only model) 节点
仅加载模型，不处理CLIP
前端UI由 web/extensions/multi_lora_loader_only_model.js 提供
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


class MultiLoraLoaderOnlyModel:
    """
    多Lora加载器节点（仅模型）
    只加载模型，不处理CLIP
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
            }
        }

    RETURN_TYPES = ("MODEL", "STRING")
    RETURN_NAMES = ("model", "lora_names")
    FUNCTION = "load_loras"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "多Lora加载器节点（仅模型）- 只加载模型，不处理CLIP。\n"
        "默认界面简洁，点击 '+ Add Lora' 按钮可随时添加Lora。\n"
        "每个Lora都有独立的启用开关和M权重控制（M=Model）。\n"
        "可以随时添加或删除Lora，配置会自动保存到工作流中。"
    )
    SEARCH_ALIASES = ["naiba", "multi lora", "lora stack", "lora bundle", "lora group", "add lora", "only model"]

    def load_loras(self, model, lora_data="[]"):
        """
        读取JSON配置，依次应用所有启用的Lora

        JSON格式示例:
        [
            {
                "name": "some_lora.safetensors",
                "strength_model": 1.0,
                "enabled": true
            }
        ]
        """
        # 解析JSON配置
        loras = parse_lora_list(lora_data, "lora_data")

        # 只记录真正成功应用的 LoRA；失败项汇总后让节点明确报错。
        loaded_lora_names = []
        load_failures = []

        # 依次应用每个启用的Lora
        for preset_index, lora_config in enumerate(loras):
            if not isinstance(lora_config, dict):
                load_failures.append(f"第 {preset_index + 1} 项不是 LoRA 对象")
                continue
            # 检查是否启用
            if not lora_config.get("enabled", False):
                continue

            # 获取Lora文件名
            configured_name = lora_config.get("name", "")
            if not configured_name:
                load_failures.append(f"第 {preset_index + 1} 项已启用但缺少 name")
                continue

            # 获取权重（仅模型强度）
            strength_model = float(lora_config.get("strength_model", 1.0))

            # 权重为0则跳过
            if strength_model == 0:
                continue

            try:
                lora_name = resolve_lora_name(lora_config)
                # 加载Lora文件
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                ensure_lora_has_compatible_patches(
                    model, None, lora, strength_model, 0
                )

                # 应用Lora到模型（不处理CLIP）
                # comfy.sd.load_lora_for_models 需要 clip 参数，我们传入 None 并忽略返回的 clip
                model, _ = comfy.sd.load_lora_for_models(
                    model, None, lora, strength_model, 0
                )
                loaded_lora_names.append(lora_name)
            except Exception as e:
                load_failures.append(f"{configured_name}: {type(e).__name__}: {e}")
                continue

        if load_failures:
            details = "\n".join(f"- {item}" for item in load_failures)
            raise RuntimeError(
                f"Multi LoRA Loader (only model) 有 {len(load_failures)} 个 LoRA 未能应用：\n{details}"
            )

        # 输出仅包含成功应用的 LoRA 名称。
        lora_names_json = json.dumps(loaded_lora_names, ensure_ascii=False)

        return (model, lora_names_json)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "MultiLoraLoaderOnlyModel": MultiLoraLoaderOnlyModel,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MultiLoraLoaderOnlyModel": "Multi LoRA Loader (only model)",
}
