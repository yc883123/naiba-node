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
    ".preview.bmp",
    ".preview.gif",
    ".preview.tiff",
    ".preview.tif",
    ".custom.preview.webp",
    ".custom.preview.png",
    ".custom.preview.jpg",
    ".custom.preview.jpeg",
    ".custom.preview.bmp",
    ".custom.preview.gif",
    ".webp",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".tiff",
    ".tif",
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
    
    async def search_models(self, query: str, page: int = 1, limit: int = 20, model_type: Optional[str] = None, max_retries: int = 3) -> Tuple[Optional[Dict], Optional[str]]:
        """
        搜索Civitai模型
        
        Args:
            query: 搜索关键词
            page: 页码（从1开始）
            limit: 每页数量（默认20）
            model_type: 模型类型过滤（可选，如 "LORA"）
            max_retries: 最大重试次数
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (搜索结果数据, 错误信息)
        """
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                params = {
                    "query": query,
                    "page": str(page),
                    "limit": str(limit),
                }
                if model_type:
                    params["types"] = model_type
                
                url = f"{self.api_base}/models"
                
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data, None
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
    
    async def download_image(self, image_url: str, save_path: str, validate: bool = True) -> bool:
        """
        下载图片/视频到本地
        
        Args:
            image_url: 资源 URL
            save_path: 保存路径
            validate: 是否校验响应确为图片（静态图默认开启，可拒绝 HTML/JSON
                错误页落地；下载视频/GIF 等动态预览中间文件时应关闭，因其本身非图片）
            
        Returns:
            bool: 是否成功
        """
        try:
            session = await self._get_session()
            
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    content = await response.read()
                    # 校验响应确为图片：拒绝 Civitai/CDN 返回的 HTML/JSON 错误页被当图片存盘
                    if validate and not _looks_like_image(content):
                        print(f"[CivitaiClient] 跳过非图片响应（疑似错误页），URL: {image_url}")
                        return False
                    # 确保目录存在
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    # 写入文件
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
        从图片列表中选择合适的预览（NSFW过滤）。
        优先静态图片；若无静态图片，则回退到视频/GIF 预览
        （由调用方下载后抽首帧作为封面）。音频/视频模型在 Civitai 仅有视频预览，
        此回退可让其也能生成预览封面。

        Returns:
            Optional[Dict]: 选中的图片信息；回退到视频/GIF 时附带标记
                `_is_motion_preview=True`，供调用方抽帧。无可用预览返回 None。
        """
        if not images:
            return None

        # 过滤有效图片
        valid_images = [img for img in images if isinstance(img, dict) and "url" in img]
        if not valid_images:
            return None

        # 视频/GIF 等动态格式（无静态图时回退选用）
        MOTION_FORMATS = {".gif", ".mp4", ".avi", ".mov", ".webm", ".apng"}

        def _classify(img: Dict) -> str:
            url = img.get("url", "")
            ext = os.path.splitext(url.split("?")[0])[1].lower()
            return "motion" if ext in MOTION_FORMATS else "static"

        static_images = [img for img in valid_images if _classify(img) == "static"]
        motion_images = [img for img in valid_images if _classify(img) == "motion"]

        def _pick(pool: List[Dict]) -> Optional[Dict]:
            if not pool:
                return None
            # 优先安全图片（NSFW 级别 <= 阈值）；使用 <= 以便 R 级在 R 阈值下也显示
            safe = [img for img in pool if img.get("nsfwLevel", 0) <= max_nsfw_level]
            if safe:
                return safe[0]
            # 全部超阈值时，取 NSFW 级别最低的
            return min(pool, key=lambda x: x.get("nsfwLevel", 0))

        # 1) 优先静态图片
        chosen = _pick(static_images)
        if chosen is not None:
            return chosen

        # 2) 回退视频/GIF 预览（音频/视频模型场景）
        chosen = _pick(motion_images)
        if chosen is not None:
            chosen = dict(chosen)  # 复制，避免修改原始 API 数据
            chosen["_is_motion_preview"] = True
            return chosen

        return None
    
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


# ============================================================
# 图片 MIME 探测 & 视频/GIF 首帧抽帧（自包含，供 Civitai 同步复用）
# 依赖运行时 import 探测，不写死解释器路径：
#   GIF 用 PIL（随 ComfyUI 自带）；视频用 cv2 / imageio / ffmpeg 兜底。
# 与 preset_routes.py 行为一致，但本文件内独立完成，避免跨模块 import。
# ============================================================
_EXT_MIME_MAP = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tiff": "image/tiff", ".tif": "image/tiff", ".svg": "image/svg+xml",
    ".avif": "image/avif", ".heic": "image/heic", ".heif": "image/heif",
    ".ico": "image/x-icon", ".apng": "image/apng",
}


def detect_image_mime(data: bytes, fallback_ext: str = "") -> str:
    """
    根据文件内容（魔数）检测真实图片 MIME 类型，不依赖扩展名。
    无法识别时回退到扩展名映射（仅当魔数匹配失败时使用）。
    """
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 4 and data[:4] == b"GIF8":
        return "image/gif"
    if len(data) >= 4 and data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if len(data) >= 4 and data[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    if len(data) >= 12 and data[4:8] in (b"avif", b"heic", b"heif", b"mif1"):
        return "image/avif"
    ext = fallback_ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    return _EXT_MIME_MAP.get(ext, "application/octet-stream")


def _looks_like_image(data: bytes) -> bool:
    """严格校验字节是否为真实图片（基于魔数），拒绝 HTML/JSON 错误页。"""
    if len(data) < 4:
        return False
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return True
    if data[:4] == b"GIF8":
        return True
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return True
    return False


_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}
_GIF_EXT = ".gif"

_CV2 = None
_CV2_TRIED = False
_IMAGEIO = None
_IMAGEIO_TRIED = False


def _try_import_cv2():
    global _CV2, _CV2_TRIED
    if _CV2_TRIED:
        return _CV2
    _CV2_TRIED = True
    try:
        import cv2
        _CV2 = cv2
    except Exception:
        _CV2 = None
    return _CV2


def _try_import_imageio():
    global _IMAGEIO, _IMAGEIO_TRIED
    if _IMAGEIO_TRIED:
        return _IMAGEIO
    _IMAGEIO_TRIED = True
    try:
        import imageio.v2 as imageio_mod
        _IMAGEIO = imageio_mod
    except Exception:
        try:
            import imageio
            _IMAGEIO = imageio
        except Exception:
            _IMAGEIO = None
    return _IMAGEIO


def _gif_first_frame_png(path: str):
    """用 PIL 抽取 GIF 首帧为 PNG 字节（PIL 随 ComfyUI 自带）。"""
    try:
        from PIL import Image
        import io
        with Image.open(path) as im:
            im.seek(0)
            frame = im.convert("RGB")
            buf = io.BytesIO()
            frame.save(buf, format="PNG")
            return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        print(f"[CivitaiUtils] GIF 首帧抽取失败 {path}: {e}")
        return None


def _video_first_frame_png(path: str):
    """从视频抽取首帧为 PNG 字节：优先 cv2，其次 imageio，再次 ffmpeg 子进程。"""
    cv2 = _try_import_cv2()
    if cv2 is not None:
        try:
            cap = cv2.VideoCapture(path)
            try:
                if not cap.isOpened():
                    return None
                ret, frame = cap.read()
                if not ret or frame is None:
                    return None
                from PIL import Image
                import numpy as np
                import io
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                im = Image.fromarray(rgb)
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                return buf.getvalue()
            finally:
                cap.release()
        except Exception as e:  # noqa: BLE001
            print(f"[CivitaiUtils] cv2 首帧抽取失败 {path}: {e}")

    imageio = _try_import_imageio()
    if imageio is not None:
        try:
            import numpy as np
            from PIL import Image
            import io
            reader = imageio.get_reader(path)
            try:
                frame = reader.get_data(0)
                rgb = np.asarray(frame)[..., :3] if frame.ndim == 3 else frame
                im = Image.fromarray(rgb)
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                return buf.getvalue()
            finally:
                reader.close()
        except Exception as e:  # noqa: BLE001
            print(f"[CivitaiUtils] imageio 首帧抽取失败 {path}: {e}")

    try:
        from PIL import Image
        import io
        import subprocess
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-vframes", "1", "-f", "image2pipe",
             "-vcodec", "png", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
        )
        if proc.returncode == 0 and proc.stdout and proc.stdout[:8] == b"\x89PNG\r\n\x1a\n":
            return proc.stdout
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        print(f"[CivitaiUtils] ffmpeg 首帧抽取失败 {path}: {e}")
    return None


def extract_first_frame_as_png(path: str) -> "bytes | None":
    """抽取视频/GIF 首帧为 PNG 字节；失败或无可抽帧依赖时返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == _GIF_EXT:
        return _gif_first_frame_png(path)
    if ext in _VIDEO_EXTS:
        return _video_first_frame_png(path)
    return None


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
    
    # 1. 优先查找自定义预览图 (.custom.preview.*) - 用户显式设置，最高优先级
    custom_preview_extensions = ['.webp', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif']
    for ext in custom_preview_extensions:
        preview_path = os.path.join(lora_dir, lora_basename + '.custom.preview' + ext)
        if os.path.exists(preview_path):
            return preview_path
    
    # 2. 查找标准预览图和Civitai预览图
    for ext in PREVIEW_EXTENSIONS:
        preview_path = os.path.join(lora_dir, lora_basename + ext)
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
            # 预览图存在且本地文件存在，直接返回
            preview_path = cached.get("preview_path")
            if preview_path and os.path.exists(preview_path):
                return cached, preview_path, None
            # 已尝试同步但确实无可用预览（守卫标记），避免无图模型反复请求 Civitai
            if cached.get("_preview_resolved") is True:
                return cached, cached.get("preview_path"), None
    
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
            # API/网络错误：仍把已算好的 SHA256 写入缓存，供本地读取；
            # _preview_resolved=False 允许下次同步重试元数据。
            try:
                save_cached_metadata(metadata_path, {
                    "hash": file_hash,
                    "_preview_resolved": False,
                    "_sha_only": True,
                })
            except Exception:
                pass
            return None, None, error
        
        if not version_data:
            # Civitai 无对应模型：同样缓存 SHA256（仍允许下次重试）。
            try:
                save_cached_metadata(metadata_path, {
                    "hash": file_hash,
                    "_preview_resolved": False,
                    "_sha_only": True,
                })
            except Exception:
                pass
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
            # v6 API 将统计字段包在 stats{} 内；此处优先读 stats，并兼容旧 API 顶层字段
            "download_count": (_stats := version_data.get("stats", {}) or {}).get("downloadCount", version_data.get("downloadCount", 0)),
            "rating_count": _stats.get("ratingCount", version_data.get("ratingCount", 0)),
            "rating": _stats.get("rating", version_data.get("rating", 0)),
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

                if selected_image.get("_is_motion_preview"):
                    # 视频/GIF 预览：下载为 motion 文件后抽首帧为 .preview.png 封面
                    from urllib.parse import urlparse
                    url_ext = os.path.splitext(urlparse(image_url).path)[1].lower()
                    if url_ext not in (".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".gif"):
                        url_ext = ".mp4"
                    motion_filename = f"{lora_basename}.preview{url_ext}"
                    motion_path = os.path.join(lora_dir, motion_filename)
                    if await client.download_image(image_url, motion_path, validate=False):
                        png_bytes = extract_first_frame_as_png(motion_path)
                        if png_bytes:
                            preview_filename = f"{lora_basename}.preview.png"
                            preview_path = os.path.join(lora_dir, preview_filename)
                            with open(preview_path, "wb") as f:
                                f.write(png_bytes)
                            metadata["preview_url"] = image_url
                            metadata["preview_path"] = preview_path
                            metadata["preview_nsfw_level"] = selected_image.get("nsfwLevel", 0)
                            metadata["preview_is_motion"] = True
                            # 抽帧成功，删除中间视频/GIF 文件以节省空间
                            try:
                                os.remove(motion_path)
                            except Exception:
                                pass
                        else:
                            preview_path = None
                    else:
                        preview_path = None
                else:
                    # 静态图：直接下载
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

        # 标记预览已处理（无论最终是否有图），避免无图模型反复请求 Civitai API
        metadata["_preview_resolved"] = True

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


def build_civitai_version_info(version_data: Dict) -> Dict:
    """
    从Civitai版本数据中提取关键信息
    
    Args:
        version_data: Civitai API返回的版本数据
        
    Returns:
        Dict: 提取的信息，包含以下字段：
            - model_name: 模型名称
            - version_name: 版本名称
            - model_id: 模型ID
            - version_id: 版本ID
            - base_model: 基础模型
            - download_url: 下载地址
            - model_page_url: 模型页面地址
            - preview_url: 预览图地址
            - trigger_words: 触发词列表
            - description: 描述
            - nsfw_level: NSFW级别
            - download_count: 下载次数
            - rating: 评分
            - rating_count: 评分数量
            - published_at: 发布时间
            - updated_at: 更新时间
    """
    if not version_data or not isinstance(version_data, dict):
        return {}
    
    # 提取模型信息
    model_info = version_data.get("model", {})
    
    # 构建下载地址
    version_id = version_data.get("id")
    download_url = None
    if version_id:
        # 优先使用API提供的downloadUrl
        download_url = version_data.get("downloadUrl")
        if not download_url:
            # 构建标准下载地址
            download_url = f"https://civitai.com/api/download/models/{version_id}"
    
    # 构建模型页面地址
    model_id = model_info.get("id") or version_data.get("modelId")
    model_page_url = None
    if model_id:
        model_page_url = f"https://civitai.com/models/{model_id}"
        if version_id:
            model_page_url += f"?modelVersionId={version_id}"
    
    # 提取预览图
    images = version_data.get("images", [])
    preview_url = None
    if images:
        selected_image = CivitaiClient.select_preview_image(images)
        if selected_image:
            preview_url = selected_image.get("url")
    
    # 提取触发词
    trained_words = version_data.get("trainedWords", [])
    
    # 提取统计信息
    stats = version_data.get("stats", {}) or {}
    
    return {
        "model_name": model_info.get("name", "Unknown"),
        "version_name": version_data.get("name", "Unknown"),
        "model_id": model_id,
        "version_id": version_id,
        "base_model": version_data.get("baseModel", "Unknown"),
        "download_url": download_url,
        "model_page_url": model_page_url,
        "preview_url": preview_url,
        "trigger_words": trained_words,
        "description": version_data.get("description", ""),
        "nsfw_level": version_data.get("nsfwLevel", 0),
        "download_count": stats.get("downloadCount", version_data.get("downloadCount", 0)),
        "rating": stats.get("rating", version_data.get("rating", 0)),
        "rating_count": stats.get("ratingCount", version_data.get("ratingCount", 0)),
        "published_at": version_data.get("publishedAt"),
        "updated_at": version_data.get("updatedAt"),
    }