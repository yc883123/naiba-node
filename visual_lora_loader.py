"""
Visual LoRA Loader 节点 - 带 lora_testing 风格弹窗的可视化LoRA加载器
支持全屏模态弹窗选择LoRA，含图片预览、搜索、文件夹浏览、网格/列表视图切换
前端UI由 js/visual_lora_loader.js 提供
"""

import json
import os
import folder_paths
import comfy.utils
import comfy.sd


def _load_lora_cached_sha256(lora_name: str) -> str | None:
    """
    从 .civitai.info.json 缓存文件中读取 LoRA 的 SHA256 哈希值
    
    Args:
        lora_name: LoRA 文件名
        
    Returns:
        str | None: SHA256 哈希值，如果缓存不存在则返回 None
    """
    try:
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            return None
        
        # 构建元数据缓存文件路径
        metadata_path = os.path.splitext(lora_path)[0] + ".civitai.info.json"
        
        if not os.path.exists(metadata_path):
            return None
        
        # 读取缓存文件
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        
        # 返回 hash 字段（如果存在）
        if isinstance(metadata, dict):
            return metadata.get("hash")
        
        return None
    except Exception:
        return None


class VisualLoRALoader:
    """
    可视化LoRA加载器节点
    通过前端JS扩展提供全屏模态弹窗选择LoRA，支持多选、权重控制、预设管理
    所有LoRA配置以JSON格式存储在隐藏的lora_data字段中
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
            "optional": {
                "model": ("MODEL", {"tooltip": "输入的扩散模型（可选，不连接时仅加载CLIP部分）"}),
                "clip": ("CLIP", {"tooltip": "输入的CLIP模型（可选，不连接时仅加载模型部分）"}),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING")
    RETURN_NAMES = ("model", "clip", "lora_names", "preset_json")
    FUNCTION = "load_loras"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "可视化LoRA加载器节点 - 点击按钮弹出全屏模态弹窗选择LoRA。\n"
        "弹窗支持图片预览、搜索导航、文件夹浏览、网格/列表视图切换。\n"
        "每个LoRA都有独立的启用开关和M/C权重控制（M=Model, C=CLIP）。\n"
        "配置会自动保存到工作流中，支持预设管理。"
    )
    SEARCH_ALIASES = ["naiba", "visual lora", "lora picker", "lora browser", "lora gallery"]

    def load_loras(self, model=None, lora_data="[]", clip=None):
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
            loras = json.loads(lora_data) if lora_data.strip() else []
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

            # 如果Model为None，则强制strength_model为0
            if model is None:
                strength_model = 0
            
            # 如果CLIP为None，则强制strength_clip为0
            if clip is None:
                strength_clip = 0

            # 权重都为0则跳过
            if strength_model == 0 and strength_clip == 0:
                continue

            try:
                # 加载LoRA文件
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)

                # 应用LoRA到模型和CLIP（如果为None则跳过对应部分）
                model, clip = comfy.sd.load_lora_for_models(
                    model, clip, lora, strength_model, strength_clip
                )
            except Exception as e:
                print(f"[VisualLoRALoader] 加载LoRA '{lora_name}' 失败: {e}")
                continue

        lora_names_json = json.dumps(enabled_lora_names, ensure_ascii=False)
        
        # 为每个 LoRA 尝试从缓存读取 SHA256（从 .civitai.info.json）
        loras_with_sha256 = []
        for lora_config in loras:
            lora_entry = dict(lora_config)  # 复制一份，避免修改原始数据
            
            # 如果已经有 sha256 字段则保留，否则尝试从缓存读取
            if "sha256" not in lora_entry:
                lora_name = lora_entry.get("name", "")
                if lora_name:
                    cached_sha256 = _load_lora_cached_sha256(lora_name)
                    if cached_sha256:
                        lora_entry["sha256"] = cached_sha256
            
            loras_with_sha256.append(lora_entry)
        
        # 输出完整的LoRA配置JSON（与预设JSON格式一致）
        # 格式: [{name, strength_model, strength_clip, enabled, sha256?}, ...]
        try:
            preset_json = json.dumps(loras_with_sha256, ensure_ascii=False, indent=2)
        except Exception:
            preset_json = lora_data if lora_data.strip() else "[]"
        
        return (model, clip, lora_names_json, preset_json)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "VisualLoRALoader": VisualLoRALoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VisualLoRALoader": "Visual LoRA Loader",
}
