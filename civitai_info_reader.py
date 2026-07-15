"""
Civitai Info Reader 节点
读取 LoRA 文件对应的 .civitai.info.json 元数据文件
输出模型信息、触发词、预览图片、评分等
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
    print("[CivitaiInfoReader] Warning: PIL/numpy/torch not available, image output disabled")


def load_image_as_tensor(image_path, target_size=None):
    """加载图片并转换为 ComfyUI IMAGE tensor (BHWC, float32, 0-1)
    
    Args:
        image_path: 图片路径
        target_size: 目标尺寸 (width, height)，如果指定则resize
    """
    if not HAS_IMAGE_DEPS:
        if target_size:
            return torch.zeros((1, target_size[1], target_size[0], 3), dtype=torch.float32)
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
    
    try:
        img = Image.open(image_path).convert("RGB")
        if target_size:
            img = img.resize(target_size, Image.Resampling.LANCZOS)
        img_array = np.array(img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(img_array)[None,]  # (1, H, W, C)
        return tensor
    except Exception as e:
        print(f"[CivitaiInfoReader] Failed to load image: {e}")
        if target_size:
            return torch.zeros((1, target_size[1], target_size[0], 3), dtype=torch.float32)
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)


def find_civitai_info_file(lora_path):
    """查找 LoRA 文件对应的 .civitai.info.json 文件"""
    base_path = os.path.splitext(lora_path)[0]
    info_path = base_path + ".civitai.info.json"
    
    if os.path.exists(info_path):
        return info_path
    
    return None


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
        print(f"[CivitaiInfoReader] Failed to load custom data: {e}")
    
    return None


# 支持的静态图片格式（可转换为ComfyUI IMAGE tensor）
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}

# 不支持的预览格式（视频和动画图片，不拉取）
UNSUPPORTED_PREVIEW_EXTENSIONS = {".gif", ".mp4", ".avi", ".mov", ".webm", ".apng"}


def is_supported_preview_image(file_path):
    """检查文件是否为支持的静态图片格式"""
    if not file_path or not os.path.exists(file_path):
        return False, ""
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return True, ""
    elif ext in UNSUPPORTED_PREVIEW_EXTENSIONS:
        format_name = ext.upper().replace(".", "")
        return False, f"预览图为{format_name}格式，不支持作为图片输出"
    else:
        return False, f"不支持的预览图格式: {ext}"


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


def find_any_preview(lora_path):
    """查找任意格式的预览文件（包括GIF和视频），用于备注信息"""
    base_path = os.path.splitext(lora_path)[0]
    extensions = [".preview.webp", ".preview.png", ".preview.jpg", ".preview.jpeg",
                  ".preview.gif", ".preview.mp4", ".preview.webm",
                  ".webp", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".webm"]
    
    for ext in extensions:
        preview_path = base_path + ext
        if os.path.exists(preview_path):
            return preview_path
    
    return None


class CivitaiInfoReader:
    """
    Civitai 信息读取节点
    读取 LoRA 文件对应的 .civitai.info.json 元数据
    输出模型信息、触发词、预览图片等
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "lora_names": ("STRING", {"tooltip": "连接 LoRA 加载器的 lora_names 输出端口，支持单个或多个 LoRA"}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "STRING", "INT", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("preview_image", "model_info", "trigger_words", "rating_info", 
                    "model_tags", "nsfw_level", "preview_url", "civitai_url", "raw_json", "custom_prompt")
    FUNCTION = "read_info"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "Civitai 信息读取节点 - 读取 LoRA 文件对应的 .civitai.info.json 元数据。\n"
        "输入：连接 LoRA 加载器的 lora_names 输出端口。\n"
        "输出：预览图片（多LoRA时输出batch）、模型信息、触发词、评分信息、标签等。\n"
        "支持单个或多个 LoRA 信息合并输出。没有输入时输出空值。"
    )
    SEARCH_ALIASES = ["naiba", "civitai", "lora info", "model info", "trigger words", "触发词", "模型信息"]
    
    # 无数据时的默认值
    EMPTY_IMAGE = None  # 延迟创建
    EMPTY_MODEL_INFO = "无元数据"
    EMPTY_TRIGGER = "无触发词"
    EMPTY_RATING = "无评分数据"
    EMPTY_TAGS = "无标签"
    EMPTY_URL = ""
    EMPTY_JSON = "{}"
    EMPTY_CUSTOM_PROMPT = ""
    
    @classmethod
    def IS_CHANGED(cls, lora_names=None):
        """基于引用 LoRA 的 .civitai.info.json 与 .custom.info.json 文件的 mtime+size 生成签名。
        任何元数据和自定义提示词被保存修改后签名变化，ComfyUI 将重新执行本节点，
        无需重启即可读取最新数据。"""
        if not lora_names or not str(lora_names).strip():
            return ""

        names = []
        try:
            parsed = json.loads(lora_names)
            if isinstance(parsed, list):
                names = [n for n in parsed if n and isinstance(n, str)]
            elif isinstance(parsed, str) and parsed:
                names = [parsed]
        except (json.JSONDecodeError, TypeError):
            names = [str(lora_names).strip()]

        parts = []
        for name in names:
            lora_path = folder_paths.get_full_path("loras", name)
            if not lora_path:
                parts.append(f"{name}:MISSING")
                continue
            base = os.path.splitext(lora_path)[0]
            sig_files = [base + ".civitai.info.json", base + ".custom.info.json"]
            sub = []
            for sf in sig_files:
                if os.path.exists(sf):
                    try:
                        st = os.stat(sf)
                        sub.append(f"{os.path.basename(sf)}={st.st_mtime:.3f}:{st.st_size}")
                    except OSError:
                        sub.append(f"{os.path.basename(sf)}=ERR")
                else:
                    sub.append(f"{os.path.basename(sf)}=NONE")
            parts.append(f"{name}[{';'.join(sub)}]")
        return "|".join(parts)

    def read_info(self, lora_names=None):
        """读取 LoRA 的 Civitai 元数据
        
        Args:
            lora_names: LoRA 文件名（单个字符串或 JSON 数组字符串）
        """
        
        # 初始化空图片（延迟创建）
        if self.EMPTY_IMAGE is None:
            if HAS_IMAGE_DEPS:
                CivitaiInfoReader.EMPTY_IMAGE = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
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
        
        # 如果是单个 LoRA，使用原有的单 LoRA 处理逻辑
        if len(lora_names_to_process) == 1:
            return self._read_single_lora(lora_names_to_process[0])
        
        # 多个 LoRA，使用合并处理逻辑
        return self._read_multiple_loras(lora_names_to_process)
    
    def _read_single_lora(self, lora_name):
        """读取单个 LoRA 的元数据"""
        # 获取 LoRA 文件完整路径
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            print(f"[CivitaiInfoReader] LoRA file not found: {lora_name}")
            return self._empty_output()
        
        # 查找 .civitai.info.json 文件
        info_path = find_civitai_info_file(lora_path)
        if not info_path:
            # 即使没有元数据，也尝试加载预览图
            preview_path = find_preview_image(lora_path)
            preview_image = self.EMPTY_IMAGE
            preview_note = ""
            
            if preview_path:
                is_supported, reason = is_supported_preview_image(preview_path)
                if is_supported:
                    preview_image = load_image_as_tensor(preview_path)
                else:
                    preview_note = reason
            else:
                # 检查是否有不支持格式的预览文件
                any_preview = find_any_preview(lora_path)
                if any_preview:
                    _, preview_note = is_supported_preview_image(any_preview)
            
            model_info = preview_note if preview_note else self.EMPTY_MODEL_INFO
            # 尝试加载自定义数据获取 custom_prompt
            custom_data = load_custom_data(lora_path)
            custom_prompt = custom_data.get("custom_prompt", "") if custom_data else ""
            return (preview_image, model_info, self.EMPTY_TRIGGER,
                    self.EMPTY_RATING, self.EMPTY_TAGS, 0, self.EMPTY_URL,
                    self.EMPTY_URL, self.EMPTY_JSON, custom_prompt)
        
        # 读取 JSON 元数据
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"[CivitaiInfoReader] Failed to read JSON: {e}")
            return self._empty_output()
        
        # 提取各字段
        model_name = metadata.get("model_name", "未知")
        version_name = metadata.get("version_name", "")
        base_model = metadata.get("base_model", "未知")
        model_type = metadata.get("model_type", "未知")
        description = metadata.get("description", "")
        if description == "null" or description is None:
            description = ""
        
        # 构建合并的模型信息
        model_info_parts = []
        model_info_parts.append(f"模型名称: {model_name}")
        if version_name:
            model_info_parts.append(f"版本: {version_name}")
        model_info_parts.append(f"基础模型: {base_model}")
        model_info_parts.append(f"类型: {model_type}")
        if description:
            # 清理 HTML 标签
            clean_desc = self._strip_html(description)
            if clean_desc:
                model_info_parts.append(f"描述: {clean_desc}")
        model_info = "\n".join(model_info_parts)
        
        # 触发词
        trigger_words = metadata.get("trigger_words", []) or metadata.get("trained_words", [])
        if isinstance(trigger_words, list):
            trigger_str = ", ".join(str(w) for w in trigger_words if w)
        else:
            trigger_str = str(trigger_words)
        
        # 如果触发词为空，显示提示信息
        if not trigger_str or trigger_str.strip() == "":
            trigger_str = "无触发词"
        
        # 评分信息
        rating = metadata.get("rating", 0)
        rating_count = metadata.get("rating_count", 0)
        download_count = metadata.get("download_count", 0)
        rating_info_parts = []
        if rating:
            rating_info_parts.append(f"评分: {rating:.1f} ({rating_count}次评价)")
        else:
            rating_info_parts.append(f"评分: 暂无")
        rating_info_parts.append(f"下载量: {download_count}")
        rating_info = "\n".join(rating_info_parts)
        
        # 标签
        model_tags = metadata.get("model_tags", [])
        if isinstance(model_tags, list):
            tags_str = ", ".join(str(t) for t in model_tags if t)
        else:
            tags_str = str(model_tags)
        if not tags_str or tags_str.strip() == "":
            tags_str = "无标签"
        
        # NSFW 级别
        nsfw_level = metadata.get("nsfw_level", 0)
        if not isinstance(nsfw_level, int):
            nsfw_level = 0
        
        # URL
        preview_url = metadata.get("preview_url", "")
        model_id = metadata.get("model_id", "")
        civitai_url = f"https://civitai.com/models/{model_id}" if model_id else ""
        
        # 预览图（检查格式，视频/GIF不作为图片输出）
        preview_path = metadata.get("preview_path", "")
        if not preview_path or not os.path.exists(preview_path):
            preview_path = find_preview_image(lora_path)
        
        preview_image = self.EMPTY_IMAGE
        if preview_path:
            is_supported, reason = is_supported_preview_image(preview_path)
            if is_supported:
                preview_image = load_image_as_tensor(preview_path)
            else:
                # 不支持的格式，添加备注到model_info
                model_info_parts.append(f"⚠ {reason}")
        else:
            # 没有找到预览图，检查是否有不支持格式的预览文件
            any_preview = find_any_preview(lora_path)
            if any_preview:
                _, note = is_supported_preview_image(any_preview)
                if note:
                    model_info_parts.append(f"⚠ {note}")
        
        # 重新构建model_info（因为可能添加了备注）
        model_info = "\n".join(model_info_parts)
        
        # 原始 JSON
        raw_json = json.dumps(metadata, ensure_ascii=False, indent=2)
        
        # 加载自定义数据获取 custom_prompt
        custom_data = load_custom_data(lora_path)
        custom_prompt = custom_data.get("custom_prompt", "") if custom_data else ""
        
        return (preview_image, model_info, trigger_str, rating_info,
                tags_str, nsfw_level, preview_url, civitai_url, raw_json, custom_prompt)
    
    def _read_multiple_loras(self, lora_names):
        """读取多个 LoRA 的元数据并合并输出"""
        
        # 收集所有 LoRA 的数据
        all_model_info = []
        all_trigger_words = []
        all_rating_info = []
        all_model_tags = []
        all_preview_urls = []
        all_civitai_urls = []
        all_raw_jsons = []
        all_custom_prompts = []
        max_nsfw_level = 0
        all_preview_images = []
        
        # 第一遍：收集所有预览图，确定统一尺寸（排除视频/GIF格式）
        preview_images_raw = []
        preview_notes = {}  # 存储不支持格式的备注
        for lora_name in lora_names:
            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                preview_images_raw.append(None)
                continue
            
            # 尝试从元数据获取预览图路径
            info_path = find_civitai_info_file(lora_path)
            preview_path = None
            if info_path:
                try:
                    with open(info_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    preview_path = metadata.get("preview_path", "")
                    if not preview_path or not os.path.exists(preview_path):
                        preview_path = None
                except:
                    pass
            
            # 尝试查找本地预览图
            if not preview_path:
                preview_path = find_preview_image(lora_path)
            
            # 检查预览图格式
            if preview_path:
                is_supported, reason = is_supported_preview_image(preview_path)
                if is_supported:
                    preview_images_raw.append(preview_path)
                else:
                    preview_images_raw.append(None)
                    preview_notes[lora_name] = reason
            else:
                # 没有找到预览图，检查是否有不支持格式的预览文件
                any_preview = find_any_preview(lora_path)
                if any_preview:
                    _, note = is_supported_preview_image(any_preview)
                    if note:
                        preview_notes[lora_name] = note
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
        
        # 第三遍：收集元数据信息
        for i, lora_name in enumerate(lora_names):
            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                print(f"[CivitaiInfoReader] LoRA file not found: {lora_name}")
                continue
            
            info_path = find_civitai_info_file(lora_path)
            if not info_path:
                # 没有元数据文件，但可能有预览格式备注
                if lora_name in preview_notes:
                    all_model_info.append(f"[{i+1}] {lora_name}\n⚠ {preview_notes[lora_name]}")
                continue
            
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception as e:
                print(f"[CivitaiInfoReader] Failed to read JSON for {lora_name}: {e}")
                continue
            
            # 提取各字段
            model_name = metadata.get("model_name", "未知")
            version_name = metadata.get("version_name", "")
            base_model = metadata.get("base_model", "未知")
            model_type = metadata.get("model_type", "未知")
            description = metadata.get("description", "")
            if description == "null" or description is None:
                description = ""
            
            # 构建单个 LoRA 的模型信息
            lora_info_parts = []
            lora_info_parts.append(f"[{i+1}] {model_name}")
            if version_name:
                lora_info_parts.append(f"版本: {version_name}")
            lora_info_parts.append(f"基础模型: {base_model}")
            lora_info_parts.append(f"类型: {model_type}")
            if description:
                clean_desc = self._strip_html(description)
                if clean_desc:
                    lora_info_parts.append(f"描述: {clean_desc}")
            # 添加预览格式备注
            if lora_name in preview_notes:
                lora_info_parts.append(f"⚠ {preview_notes[lora_name]}")
            all_model_info.append("\n".join(lora_info_parts))
            
            # 触发词
            trigger_words = metadata.get("trigger_words", []) or metadata.get("trained_words", [])
            if isinstance(trigger_words, list):
                all_trigger_words.extend([str(w) for w in trigger_words if w])
            elif trigger_words:
                all_trigger_words.append(str(trigger_words))
            
            # 评分信息
            rating = metadata.get("rating", 0)
            rating_count = metadata.get("rating_count", 0)
            download_count = metadata.get("download_count", 0)
            rating_parts = []
            if rating:
                rating_parts.append(f"评分: {rating:.1f} ({rating_count}次评价)")
            else:
                rating_parts.append(f"评分: 暂无")
            rating_parts.append(f"下载量: {download_count}")
            all_rating_info.append(f"[{i+1}] {model_name}: " + ", ".join(rating_parts))
            
            # 标签
            model_tags = metadata.get("model_tags", [])
            if isinstance(model_tags, list):
                all_model_tags.extend([str(t) for t in model_tags if t])
            
            # NSFW 级别
            nsfw_level = metadata.get("nsfw_level", 0)
            if isinstance(nsfw_level, int) and nsfw_level > max_nsfw_level:
                max_nsfw_level = nsfw_level
            
            # URL
            preview_url = metadata.get("preview_url", "")
            if preview_url:
                all_preview_urls.append(f"[{i+1}] {preview_url}")
            
            model_id = metadata.get("model_id", "")
            if model_id:
                all_civitai_urls.append(f"[{i+1}] https://civitai.com/models/{model_id}")
            
            # 原始 JSON
            all_raw_jsons.append(json.dumps(metadata, ensure_ascii=False, indent=2))
            
            # 自定义数据中的 custom_prompt
            custom_data = load_custom_data(lora_path)
            if custom_data and custom_data.get("custom_prompt"):
                all_custom_prompts.append(f"[{i+1}] {model_name}: {custom_data['custom_prompt']}")
        
        # 合并输出
        model_info = "\n\n".join(all_model_info) if all_model_info else self.EMPTY_MODEL_INFO
        
        unique_triggers = list(dict.fromkeys(all_trigger_words))
        trigger_str = ", ".join(unique_triggers) if unique_triggers else "无触发词"
        
        rating_info = "\n".join(all_rating_info) if all_rating_info else self.EMPTY_RATING
        
        unique_tags = list(dict.fromkeys(all_model_tags))
        tags_str = ", ".join(unique_tags) if unique_tags else "无标签"
        
        nsfw_level = max_nsfw_level
        
        preview_url = "\n".join(all_preview_urls) if all_preview_urls else self.EMPTY_URL
        civitai_url = "\n".join(all_civitai_urls) if all_civitai_urls else self.EMPTY_URL
        
        raw_json = "[" + ",\n".join(all_raw_jsons) + "]" if all_raw_jsons else self.EMPTY_JSON
        
        custom_prompt = "\n".join(all_custom_prompts) if all_custom_prompts else self.EMPTY_CUSTOM_PROMPT
        
        return (preview_batch, model_info, trigger_str, rating_info,
                tags_str, nsfw_level, preview_url, civitai_url, raw_json, custom_prompt)
    
    def _empty_output(self):
        """返回空的默认输出"""
        return (self.EMPTY_IMAGE, self.EMPTY_MODEL_INFO, self.EMPTY_TRIGGER,
                self.EMPTY_RATING, self.EMPTY_TAGS, 0, self.EMPTY_URL,
                self.EMPTY_URL, self.EMPTY_JSON, self.EMPTY_CUSTOM_PROMPT)
    
    @staticmethod
    def _strip_html(html_str):
        """简单的 HTML 标签清理"""
        import re
        if not html_str:
            return ""
        # 移除 HTML 标签
        clean = re.sub(r'<[^>]+>', '', html_str)
        # 清理多余空白
        clean = re.sub(r'\s+', ' ', clean).strip()
        # 截断过长的描述
        if len(clean) > 500:
            clean = clean[:500] + "..."
        return clean


# 节点映射
NODE_CLASS_MAPPINGS = {
    "CivitaiInfoReader": CivitaiInfoReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CivitaiInfoReader": "Civitai Info Reader",
}
