"""
Custom Data Reader 节点
读取 LoRA 文件对应的 .custom.info.json 自定义数据文件
输出自定义提示词、预览图片、下载链接、NSFW级别等
"""

import os
import json
import folder_paths

# 尝试导入图片处理库
try:
    from PIL import Image
    import numpy as np
    import torch
    HAS_IMAGE_DEPS = True
except ImportError:
    HAS_IMAGE_DEPS = False
    print("[CustomDataReader] Warning: PIL/numpy/torch not available, image output disabled")


def load_image_as_tensor(image_path, target_size=None):
    """加载图片并转换为 ComfyUI IMAGE tensor (BHWC, float32, 0-1)
    
    Args:
        image_path: 图片路径
        target_size: 目标尺寸 (width, height)，如果指定则resize
    """
    if not HAS_IMAGE_DEPS:
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
    
    try:
        img = Image.open(image_path).convert("RGB")
        if target_size:
            img = img.resize(target_size, Image.Resampling.LANCZOS)
        img_array = np.array(img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(img_array)[None,]  # (1, H, W, C)
        return tensor
    except Exception as e:
        print(f"[CustomDataReader] Failed to load image: {e}")
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)


def load_custom_data(lora_path):
    """加载 LoRA 文件对应的 .custom.info.json 自定义数据"""
    base_path = os.path.splitext(lora_path)[0]
    custom_data_path = base_path + ".custom.info.json"
    
    try:
        if os.path.exists(custom_data_path):
            with open(custom_data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        print(f"[CustomDataReader] Failed to load custom data: {e}")
    
    return None


def load_civitai_metadata(lora_path):
    """加载 LoRA 文件对应的 .civitai.info.json 元数据（用于获取预览图路径）"""
    base_path = os.path.splitext(lora_path)[0]
    info_path = base_path + ".civitai.info.json"
    
    try:
        if os.path.exists(info_path):
            with open(info_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        print(f"[CustomDataReader] Failed to load civitai metadata: {e}")
    
    return None


# 支持的静态图片格式（可转换为ComfyUI IMAGE tensor）
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}

# 不支持的预览格式（视频和动画图片）
UNSUPPORTED_PREVIEW_EXTENSIONS = {".gif", ".mp4", ".avi", ".mov", ".webm", ".apng"}


def is_supported_image(file_path):
    """检查文件是否为支持的静态图片格式"""
    if not file_path or not os.path.exists(file_path):
        return False, ""
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return True, ""
    elif ext in UNSUPPORTED_PREVIEW_EXTENSIONS:
        format_name = ext.upper().replace(".", "")
        return False, f"图片为{format_name}格式，不支持作为图片输出"
    else:
        return False, f"不支持的图片格式: {ext}"


def find_preview_image(lora_path):
    """查找 LoRA 文件对应的预览图（仅返回支持的静态图片格式）"""
    base_path = os.path.splitext(lora_path)[0]
    # 优先级：.preview.* > .custom.preview.* > 直接扩展名
    extensions = [".preview.webp", ".preview.png", ".preview.jpg", ".preview.jpeg",
                  ".custom.preview.webp", ".custom.preview.png", ".custom.preview.jpg", ".custom.preview.jpeg",
                  ".webp", ".png", ".jpg", ".jpeg"]
    
    for ext in extensions:
        preview_path = base_path + ext
        if os.path.exists(preview_path):
            return preview_path
    
    return None


class CustomDataReader:
    """
    自定义数据读取节点
    读取 LoRA 文件对应的 .custom.info.json 自定义数据
    输出自定义提示词、预览图片、下载链接、NSFW级别等
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "lora_names": ("STRING", {"tooltip": "连接 LoRA 加载器的 lora_names 输出端口，支持单个或多个 LoRA"}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("preview_image", "custom_prompt", "model_description", 
                    "download_link", "nsfw_level", "raw_json")
    FUNCTION = "read_custom_data"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "自定义数据读取节点 - 读取 LoRA 文件对应的 .custom.info.json 自定义数据。\n"
        "输入：连接 LoRA 加载器的 lora_names 输出端口。\n"
        "输出：预览图片（多LoRA时输出batch）、自定义提示词、模型介绍、下载链接、NSFW级别、原始JSON。\n"
        "预览图优先级：Civitai预览图 > 自定义预览图 > 空白占位。"
    )
    SEARCH_ALIASES = ["naiba", "custom data", "自定义数据", "custom prompt", "自定义提示词"]
    
    # 无数据时的默认值
    EMPTY_IMAGE = None  # 延迟创建
    EMPTY_PROMPT = ""
    EMPTY_DESCRIPTION = ""
    EMPTY_LINK = ""
    EMPTY_JSON = "{}"
    
    def read_custom_data(self, lora_names=None):
        """读取 LoRA 的自定义数据
        
        Args:
            lora_names: LoRA 文件名（单个字符串或 JSON 数组字符串）
        """
        
        # 初始化空图片（延迟创建）
        if self.EMPTY_IMAGE is None:
            if HAS_IMAGE_DEPS:
                CustomDataReader.EMPTY_IMAGE = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            else:
                self.EMPTY_IMAGE = torch.zeros((1, 64, 64, 3), dtype=torch.float32) if HAS_IMAGE_DEPS else None
        
        # 解析输入，支持单个字符串或JSON数组
        lora_names_to_process = []
        
        if lora_names and lora_names.strip():
            try:
                # 尝试解析为JSON数组
                parsed = json.loads(lora_names)
                if isinstance(parsed, list):
                    lora_names_to_process = [name for name in parsed if name and isinstance(name, str)]
                elif isinstance(parsed, str) and parsed:
                    lora_names_to_process = [parsed]
            except (json.JSONDecodeError, TypeError):
                # 不是JSON，当作单个LoRA名称
                lora_names_to_process = [lora_names.strip()]
        
        # 没有输入时返回空值
        if not lora_names_to_process:
            return self._empty_output()
        
        # 如果是单个 LoRA，使用单 LoRA 处理逻辑
        if len(lora_names_to_process) == 1:
            return self._read_single_lora(lora_names_to_process[0])
        
        # 多个 LoRA，使用合并处理逻辑
        return self._read_multiple_loras(lora_names_to_process)
    
    def _read_single_lora(self, lora_name):
        """读取单个 LoRA 的自定义数据"""
        # 获取 LoRA 文件完整路径
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            print(f"[CustomDataReader] LoRA file not found: {lora_name}")
            return self._empty_output()
        
        # 加载自定义数据
        custom_data = load_custom_data(lora_path)
        
        # 获取预览图（优先级：Civitai预览 > 自定义预览 > 空白）
        preview_image = self.EMPTY_IMAGE
        
        # 首先尝试Civitai预览图
        civitai_metadata = load_civitai_metadata(lora_path)
        civitai_preview_path = None
        if civitai_metadata:
            civitai_preview_path = civitai_metadata.get("preview_path", "")
            if civitai_preview_path and not os.path.exists(civitai_preview_path):
                civitai_preview_path = None
        
        # 如果没有Civitai预览图，查找本地预览图
        if not civitai_preview_path:
            civitai_preview_path = find_preview_image(lora_path)
        
        # 如果有Civitai预览图，使用它
        if civitai_preview_path:
            is_supported, _ = is_supported_image(civitai_preview_path)
            if is_supported:
                preview_image = load_image_as_tensor(civitai_preview_path)
        
        # 如果没有Civitai预览图，尝试自定义预览图
        if preview_image is self.EMPTY_IMAGE and custom_data:
            custom_preview_path = custom_data.get("custom_preview_image_path", "")
            # 如果JSON中没有指定路径，自动查找.custom.preview.*文件
            if not custom_preview_path:
                base_path = os.path.splitext(lora_path)[0]
                custom_preview_extensions = [".custom.preview.webp", ".custom.preview.png", 
                                           ".custom.preview.jpg", ".custom.preview.jpeg"]
                for ext in custom_preview_extensions:
                    test_path = base_path + ext
                    if os.path.exists(test_path):
                        custom_preview_path = test_path
                        break
            
            if custom_preview_path and os.path.exists(custom_preview_path):
                is_supported, _ = is_supported_image(custom_preview_path)
                if is_supported:
                    preview_image = load_image_as_tensor(custom_preview_path)
        
        # 提取自定义数据字段
        custom_prompt = custom_data.get("custom_prompt", "") if custom_data else ""
        model_description = custom_data.get("custom_model_description", "") if custom_data else ""
        download_link = custom_data.get("custom_download_link", "") if custom_data else ""
        nsfw_level = custom_data.get("custom_nsfw_level", 0) if custom_data else 0
        
        if not isinstance(nsfw_level, int):
            nsfw_level = 0
        
        # 原始 JSON
        raw_json = json.dumps(custom_data, ensure_ascii=False, indent=2) if custom_data else self.EMPTY_JSON
        
        return (preview_image, custom_prompt, model_description, 
                download_link, nsfw_level, raw_json)
    
    def _read_multiple_loras(self, lora_names):
        """读取多个 LoRA 的自定义数据并合并输出"""
        
        # 收集所有 LoRA 的数据
        all_custom_prompts = []
        all_model_descriptions = []
        all_download_links = []
        all_raw_jsons = []
        max_nsfw_level = 0
        all_preview_images = []
        
        # 第一遍：收集所有预览图，确定统一尺寸
        preview_images_raw = []
        for lora_name in lora_names:
            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                preview_images_raw.append(None)
                continue
            
            # 优先级：Civitai预览 > 自定义预览 > None
            preview_path = None
            
            # 首先尝试Civitai预览图
            civitai_metadata = load_civitai_metadata(lora_path)
            if civitai_metadata:
                civitai_preview = civitai_metadata.get("preview_path", "")
                if civitai_preview and os.path.exists(civitai_preview):
                    preview_path = civitai_preview
            
            # 如果没有Civitai预览图，查找本地预览图
            if not preview_path:
                preview_path = find_preview_image(lora_path)
            
            # 如果还没有，尝试自定义预览图
            if not preview_path:
                custom_data = load_custom_data(lora_path)
                if custom_data:
                    custom_preview = custom_data.get("custom_preview_image_path", "")
                    if custom_preview and os.path.exists(custom_preview):
                        preview_path = custom_preview
            
            # 检查预览图格式
            if preview_path:
                is_supported, _ = is_supported_image(preview_path)
                if is_supported:
                    preview_images_raw.append(preview_path)
                else:
                    preview_images_raw.append(None)
            else:
                preview_images_raw.append(None)
        
        # 确定目标尺寸（使用第一张有效图片的尺寸，或默认512x512）
        target_size = (512, 512)
        for path in preview_images_raw:
            if path and os.path.exists(path):
                try:
                    with Image.open(path) as img:
                        target_size = img.size
                        break
                except:
                    pass
        
        # 第二遍：加载所有图片并resize到统一尺寸
        for path in preview_images_raw:
            if path and os.path.exists(path):
                img_tensor = load_image_as_tensor(path, target_size)
                all_preview_images.append(img_tensor)
            else:
                # 空白占位图
                blank = torch.zeros((1, target_size[1], target_size[0], 3), dtype=torch.float32)
                all_preview_images.append(blank)
        
        # 拼接所有图片为batch
        if all_preview_images:
            preview_batch = torch.cat(all_preview_images, dim=0)
        else:
            preview_batch = self.EMPTY_IMAGE
        
        # 第三遍：收集自定义数据
        for i, lora_name in enumerate(lora_names):
            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                print(f"[CustomDataReader] LoRA file not found: {lora_name}")
                continue
            
            custom_data = load_custom_data(lora_path)
            if not custom_data:
                continue
            
            # 自定义提示词
            custom_prompt = custom_data.get("custom_prompt", "")
            if custom_prompt:
                all_custom_prompts.append(f"[{i+1}] {lora_name}: {custom_prompt}")
            
            # 模型介绍
            model_description = custom_data.get("custom_model_description", "")
            if model_description:
                all_model_descriptions.append(f"[{i+1}] {lora_name}: {model_description}")
            
            # 下载链接
            download_link = custom_data.get("custom_download_link", "")
            if download_link:
                all_download_links.append(f"[{i+1}] {download_link}")
            
            # NSFW级别
            nsfw_level = custom_data.get("custom_nsfw_level", 0)
            if isinstance(nsfw_level, int) and nsfw_level > max_nsfw_level:
                max_nsfw_level = nsfw_level
            
            # 原始 JSON
            all_raw_jsons.append(json.dumps(custom_data, ensure_ascii=False, indent=2))
        
        # 合并输出
        custom_prompt = "\n".join(all_custom_prompts) if all_custom_prompts else self.EMPTY_PROMPT
        model_description = "\n".join(all_model_descriptions) if all_model_descriptions else self.EMPTY_DESCRIPTION
        download_link = "\n".join(all_download_links) if all_download_links else self.EMPTY_LINK
        nsfw_level = max_nsfw_level
        
        raw_json = "[" + ",\n".join(all_raw_jsons) + "]" if all_raw_jsons else self.EMPTY_JSON
        
        return (preview_batch, custom_prompt, model_description, 
                download_link, nsfw_level, raw_json)
    
    def _empty_output(self):
        """返回空的默认输出"""
        return (self.EMPTY_IMAGE, self.EMPTY_PROMPT, self.EMPTY_DESCRIPTION,
                self.EMPTY_LINK, 0, self.EMPTY_JSON)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "CustomDataReader": CustomDataReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CustomDataReader": "Custom Data Reader",
}
