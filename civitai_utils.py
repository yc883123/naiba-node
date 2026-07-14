"""
Civitai API 工具类
提供SHA256哈希计算、Civitai API查询、NSFW过滤和图片下载功能
支持默认API（无需认证）和用户自定义API（带API密钥）
"""

import hashlib
import os
import json
import asyncio
import aiohttp
from typing import Optional, Dict, List, Tuple, Any
from pathlib import Path

# NSFW级别定义
NSFW_LEVELS = {
    "PG": 1,
    "PG13": 2,
    "R": 4,
    "X": 8,
    "XXX": 16,
    "Blocked": 32,
}

# 默认API配置
DEFAULT_API_BASE = "https://civitai.red/api/v1"
DEFAULT_USER_AGENT = "NaibaLoraPreview/1.0"

# 预览图扩展名优先级
PREVIEW_EXTENSIONS = [
    ".preview.webp",
    ".preview.png",
    ".preview.jpg",
    ".preview.jpeg",
    ".custom.preview.webp",
    ".custom.preview.png",
    ".custom.preview.jpg",
    ".custom.preview.jpeg",
    ".webp",
    ".png",
    ".jpg",
    ".jpeg",
]


class CivitaiClient:
    """Civitai API客户端"""
    
    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None):
        """
        初始化Civitai客户端
        
        Args:
            api_key: Civitai API密钥（可选，不提供则使用公开API）
            api_base: API基础URL（可选，默认使用civitai.red）
        """
        self.api_key = api_key
        self.api_base = api_base or DEFAULT_API_BASE
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建aiohttp会话"""
        if self.session is None or self.session.closed:
            headers = {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=15)
            self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self.session
    
    async def close(self):
        """关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    async def query_by_hash(self, file_hash: str, max_retries: int = 3) -> Tuple[Optional[Dict], Optional[str]]:
        """
        通过SHA256哈希值查询Civitai模型版本信息
        
        Args:
            file_hash: 文件的SHA256哈希值
            max_retries: 最大重试次数
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (模型版本数据, 错误信息)
        """
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                url = f"{self.api_base}/model-versions/by-hash/{file_hash}"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data, None
                    elif response.status == 404:
                        return None, "Model not found on Civitai"
                    elif response.status == 429:
                        # 速率限制，等待后重试
                        if attempt < max_retries - 1:
                            wait_time = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                            await asyncio.sleep(wait_time)
                            continue
                        return None, "Rate limit exceeded, please try again later"
                    else:
                        error_text = await response.text()
                        if attempt < max_retries - 1 and response.status >= 500:
                            # 服务器错误，重试
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None, f"API error {response.status}: {error_text}"
                        
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None, "Request timeout"
            except aiohttp.ClientError as e:
                if attempt < max_retries - 1:
                    # 网络错误，重试
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None, f"Network error: {str(e)}"
            except Exception as e:
                return None, f"Unexpected error: {str(e)}"
        
        return None, "Max retries exceeded"
    
    async def download_image(self, image_url: str, save_path: str) -> bool:
        """
        下载图片到本地
        
        Args:
            image_url: 图片URL
            save_path: 保存路径
            
        Returns:
            bool: 是否成功
        """
        try:
            session = await self._get_session()
            
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    # 确保目录存在
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    
                    # 写入文件
                    content = await response.read()
                    with open(save_path, "wb") as f:
                        f.write(content)
                    return True
                else:
                    return False
                    
        except asyncio.TimeoutError:
            print(f"[CivitaiClient] Download timeout: {image_url}")
            return False
        except Exception as e:
            print(f"[CivitaiClient] Download error: {e}")
            return False
    
    @staticmethod
    def calculate_sha256(file_path: str) -> Optional[str]:
        """
        计算文件的SHA256哈希值
        
        Args:
            file_path: 文件路径
            
        Returns:
            Optional[str]: SHA256哈希值，失败返回None
        """
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                # 分块读取，避免大文件占用过多内存
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"[CivitaiClient] SHA256 calculation error: {e}")
            return None
    
    @staticmethod
    def select_preview_image(images: List[Dict], max_nsfw_level: int = NSFW_LEVELS["R"]) -> Optional[Dict]:
        """
        从图片列表中选择合适的预览图（NSFW过滤，排除视频和GIF）
        
        Args:
            images: 图片列表，每个图片包含nsfwLevel字段
            max_nsfw_level: 最大允许的NSFW级别
            
        Returns:
            Optional[Dict]: 选中的图片信息，如果没有合适的静态图片返回None
        """
        if not images:
            return None
        
        # 过滤有效图片
        valid_images = [img for img in images if isinstance(img, dict) and "url" in img]
        if not valid_images:
            return None
        
        # 排除视频和动画图片（GIF），只保留静态图片
        UNSUPPORTED_FORMATS = {".gif", ".mp4", ".avi", ".mov", ".webm", ".apng"}
        static_images = []
        for img in valid_images:
            url = img.get("url", "")
            ext = os.path.splitext(url.split("?")[0])[1].lower()
            if ext in UNSUPPORTED_FORMATS:
                continue
            static_images.append(img)
        
        # 如果没有静态图片，返回None（不拉取视频/GIF）
        if not static_images:
            return None
        
        # 优先选择安全图片（NSFW级别小于等于阈值）
        # 注意：使用 <= 而不是 <，这样R级图片在R级阈值下也能显示
        safe_images = [img for img in static_images if img.get("nsfwLevel", 0) <= max_nsfw_level]
        if safe_images:
            return safe_images[0]
        
        # 如果所有图片都超过阈值，选择NSFW级别最低的
        return min(static_images, key=lambda x: x.get("nsfwLevel", 0))
    
    @staticmethod
    def get_preview_extension(image_url: str) -> str:
        """
        从图片URL推断文件扩展名
        
        Args:
            image_url: 图片URL
            
        Returns:
            str: 文件扩展名（包含点号）
        """
        try:
            # 从URL路径提取扩展名
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            path = parsed.path
            ext = os.path.splitext(path)[1].lower()
            
            # 验证是否为支持的静态图片格式（排除GIF和视频）
            supported_formats = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
            if ext in supported_formats:
                return ext
            else:
                return ".webp"  # 默认使用webp
        except:
            return ".webp"


def load_cached_metadata(cache_path: str) -> Optional[Dict]:
    """
    加载缓存的元数据
    
    Args:
        cache_path: 缓存文件路径
        
    Returns:
        Optional[Dict]: 缓存的元数据，不存在或无效返回None
    """
    try:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        print(f"[CivitaiUtils] Load cache error: {e}")
    return None


def save_cached_metadata(cache_path: str, metadata: Dict) -> bool:
    """
    保存元数据到缓存
    
    Args:
        cache_path: 缓存文件路径
        metadata: 元数据字典
        
    Returns:
        bool: 是否成功
    """
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[CivitaiUtils] Save cache error: {e}")
        return False


def find_local_preview(lora_path: str) -> Optional[str]:
    """
    查找本地预览图文件
    
    Args:
        lora_path: LoRA文件路径
        
    Returns:
        Optional[str]: 预览图路径，不存在返回None
    """
    lora_dir = os.path.dirname(lora_path)
    lora_basename = os.path.splitext(os.path.basename(lora_path))[0]
    
    # 1. 优先查找标准预览图和Civitai预览图
    for ext in PREVIEW_EXTENSIONS:
        preview_path = os.path.join(lora_dir, lora_basename + ext)
        if os.path.exists(preview_path):
            return preview_path
    
    # 2. 查找自定义预览图 (.custom.preview.*)
    custom_preview_extensions = ['.webp', '.png', '.jpg', '.jpeg', '.gif']
    for ext in custom_preview_extensions:
        preview_path = os.path.join(lora_dir, lora_basename + '.custom.preview' + ext)
        if os.path.exists(preview_path):
            return preview_path
    
    return None


def get_metadata_path(lora_path: str) -> str:
    """
    获取元数据缓存文件路径
    
    Args:
        lora_path: LoRA文件路径
        
    Returns:
        str: 元数据文件路径
    """
    return os.path.splitext(lora_path)[0] + ".civitai.info.json"


async def sync_lora_from_civitai(
    lora_path: str,
    api_key: Optional[str] = None,
    max_nsfw_level: int = NSFW_LEVELS["R"],
    force: bool = False
) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
    """
    从Civitai同步LoRA元数据和预览图
    
    Args:
        lora_path: LoRA文件路径
        api_key: Civitai API密钥（可选）
        max_nsfw_level: 最大NSFW级别
        force: 是否强制更新（忽略缓存）
        
    Returns:
        Tuple[Optional[Dict], Optional[str], Optional[str]]: 
            (元数据, 预览图路径, 错误信息)
    """
    # 检查文件是否存在
    if not os.path.exists(lora_path):
        return None, None, f"LoRA file not found: {lora_path}"
    
    metadata_path = get_metadata_path(lora_path)
    
    # 检查缓存（非强制模式）
    if not force:
        cached = load_cached_metadata(metadata_path)
        if cached:
            # 检查预览图是否存在
            preview_path = cached.get("preview_path")
            if preview_path and os.path.exists(preview_path):
                return cached, preview_path, None
    
    # 计算SHA256哈希（在线程池中运行，避免阻塞事件循环）
    loop = asyncio.get_event_loop()
    file_hash = await loop.run_in_executor(None, CivitaiClient.calculate_sha256, lora_path)
    if not file_hash:
        return None, None, "Failed to calculate SHA256 hash"
    
    # 查询Civitai API
    client = CivitaiClient(api_key=api_key)
    try:
        version_data, error = await client.query_by_hash(file_hash)
        if error:
            return None, None, error
        
        if not version_data:
            return None, None, "No data returned from Civitai"
        
        # 提取元数据
        trained_words = version_data.get("trainedWords", [])
        metadata = {
            "hash": file_hash,
            "model_id": version_data.get("modelId"),
            "version_id": version_data.get("id"),
            "version_name": version_data.get("name"),
            "base_model": version_data.get("baseModel"),
            "description": version_data.get("description"),
            "trained_words": trained_words,
            "trigger_words": trained_words,  # 别名，兼容前端
            "nsfw_level": version_data.get("nsfwLevel", 0),
            "download_count": version_data.get("downloadCount", 0),
            "rating_count": version_data.get("ratingCount", 0),
            "rating": version_data.get("rating", 0),
            "published_at": version_data.get("publishedAt"),
            "updated_at": version_data.get("updatedAt"),
        }
        
        # 提取模型信息
        model_info = version_data.get("model", {})
        if model_info:
            metadata["model_name"] = model_info.get("name")
            metadata["model_type"] = model_info.get("type")
            metadata["model_nsfw"] = model_info.get("nsfw", False)
            metadata["model_tags"] = model_info.get("tags", [])
        
        # 选择预览图
        images = version_data.get("images", [])
        selected_image = CivitaiClient.select_preview_image(images, max_nsfw_level)
        
        preview_path = None
        if selected_image:
            image_url = selected_image.get("url")
            if image_url:
                # 生成预览图保存路径
                lora_dir = os.path.dirname(lora_path)
                lora_basename = os.path.splitext(os.path.basename(lora_path))[0]
                ext = CivitaiClient.get_preview_extension(image_url)
                preview_filename = f"{lora_basename}.preview{ext}"
                preview_path = os.path.join(lora_dir, preview_filename)
                
                # 下载预览图
                success = await client.download_image(image_url, preview_path)
                if success:
                    metadata["preview_url"] = image_url
                    metadata["preview_path"] = preview_path
                    metadata["preview_nsfw_level"] = selected_image.get("nsfwLevel", 0)
                else:
                    preview_path = None
        
        # 保存缓存
        save_cached_metadata(metadata_path, metadata)
        
        return metadata, preview_path, None
        
    finally:
        await client.close()


# 模块级别便捷函数
async def get_lora_preview(
    lora_name: str,
    lora_dirs: List[str],
    api_key: Optional[str] = None,
    max_nsfw_level: int = NSFW_LEVELS["R"],
    auto_sync: bool = True
) -> Tuple[Optional[str], Optional[Dict], Optional[str]]:
    """
    获取LoRA预览图（优先本地，可选自动同步）
    
    Args:
        lora_name: LoRA文件名（可能包含子目录）
        lora_dirs: LoRA目录列表
        api_key: Civitai API密钥（可选）
        max_nsfw_level: 最大NSFW级别
        auto_sync: 是否自动同步
        
    Returns:
        Tuple[Optional[str], Optional[Dict], Optional[str]]: 
            (预览图路径, 元数据, 错误信息)
    """
    # 查找LoRA文件路径
    lora_path = None
    for lora_dir in lora_dirs:
        candidate = os.path.join(lora_dir, lora_name)
        if os.path.exists(candidate):
            lora_path = candidate
            break
    
    if not lora_path:
        return None, None, f"LoRA file not found: {lora_name}"
    
    # 查找本地预览图
    local_preview = find_local_preview(lora_path)
    if local_preview:
        # 尝试加载元数据
        metadata_path = get_metadata_path(lora_path)
        metadata = load_cached_metadata(metadata_path)
        return local_preview, metadata, None
    
    # 如果没有本地预览且启用自动同步
    if auto_sync:
        metadata, preview_path, error = await sync_lora_from_civitai(
            lora_path, api_key, max_nsfw_level
        )
        return preview_path, metadata, error
    
    return None, None, "No local preview found and auto_sync is disabled"