"""
Multi LoRA Loader 预设管理 API 路由
提供预设的增删改查功能，支持服务端预设存储
"""

import os
import json
import glob
import time
import asyncio
import hashlib
from pathlib import Path
from aiohttp import web
from server import PromptServer
import folder_paths
from typing import Optional, Dict, Tuple

# 图片缓存系统
class ImageCache:
    """简单的内存缓存系统，用于缓存图片数据"""
    
    def __init__(self, max_size=100, ttl=3600):
        """
        初始化缓存
        max_size: 最大缓存条目数
        ttl: 缓存过期时间（秒）
        """
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl
        self.access_times = {}
    
    def get(self, key):
        """获取缓存内容"""
        if key not in self.cache:
            return None
        
        # 检查是否过期
        if time.time() - self.access_times[key] > self.ttl:
            self._remove(key)
            return None
        
        # 更新访问时间
        self.access_times[key] = time.time()
        return self.cache[key]
    
    def set(self, key, value):
        """设置缓存内容"""
        # 如果缓存已满，删除最旧的条目
        if len(self.cache) >= self.max_size:
            self._remove_oldest()
        
        self.cache[key] = value
        self.access_times[key] = time.time()
    
    def _remove(self, key):
        """删除缓存条目"""
        if key in self.cache:
            del self.cache[key]
            del self.access_times[key]
    
    def _remove_oldest(self):
        """删除最旧的缓存条目"""
        if not self.cache:
            return
        
        oldest_key = min(self.access_times.items(), key=lambda x: x[1])[0]
        self._remove(oldest_key)
    
    def delete(self, key):
        """删除指定缓存条目"""
        self._remove(key)
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.access_times.clear()
    
    def size(self):
        """获取缓存大小"""
        return len(self.cache)

# 创建全局缓存实例
image_cache = ImageCache(max_size=200, ttl=3600)  # 缓存200张图片，1小时过期

# 依据扩展名的 MIME 回退映射（当无法从文件内容识别时使用）
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

    Civitai 同步封面等场景下常出现“扩展名与实际格式不符”（例如文件实为 PNG
    却被命名为 .jpeg）。若仅按扩展名返回 MIME，前端 <img> 可能裂图。此函数优先
    用魔数识别，无法识别时回退到扩展名映射。

    Args:
        data: 图片二进制内容
        fallback_ext: 扩展名（含点或不含均可），用于无法识别时的回退

    Returns:
        str: MIME 类型，例如 image/png
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
    # 回退：依据扩展名
    ext = fallback_ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    return _EXT_MIME_MAP.get(ext, "application/octet-stream")

# ============================================================
# 视频 / GIF 首帧抽取（用于 LoRA 预览静态封面）
# 依赖为运行时 import 探测，路径无关：自动在运行 ComfyUI 的 Python 内探测，
# 不写死任何 Python 解释器路径。GIF 用 PIL（随 ComfyUI 自带，开箱即用）；
# 视频用 cv2 / imageio / ffmpeg 其一，全缺失时优雅降级（返回 None）。
# ============================================================
_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}
_GIF_EXT = ".gif"

# 懒加载的可选依赖（仅探测一次）
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
        print(f"[Naiba] GIF 首帧抽取失败 {path}: {e}")
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
            print(f"[Naiba] cv2 首帧抽取失败 {path}: {e}")

    # imageio 兜底
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
            print(f"[Naiba] imageio 首帧抽取失败 {path}: {e}")

    # ffmpeg 子进程兜底
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
        print(f"[Naiba] ffmpeg 首帧抽取失败 {path}: {e}")
    return None


def extract_first_frame_as_png(path: str) -> "bytes | None":
    """抽取视频/GIF 首帧为 PNG 字节；失败或无可抽帧依赖时返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == _GIF_EXT:
        return _gif_first_frame_png(path)
    if ext in _VIDEO_EXTS:
        return _video_first_frame_png(path)
    return None


# 预设存储目录
PRESETS_DIR = os.path.join(os.path.dirname(__file__), "presets")
PRESETS_EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), "presets.example")
PRESETS_IMAGES_DIR = os.path.join(PRESETS_DIR, "images")
os.makedirs(PRESETS_DIR, exist_ok=True)
os.makedirs(PRESETS_IMAGES_DIR, exist_ok=True)

# 首次使用时，如果presets目录为空，自动复制示例预设
def init_default_presets():
    """如果presets目录为空，从presets.example复制示例预设"""
    try:
        # 检查presets目录是否为空
        existing_presets = [f for f in os.listdir(PRESETS_DIR) if f.endswith('.json')]
        
        if not existing_presets and os.path.exists(PRESETS_EXAMPLE_DIR):
            # 复制示例预设
            example_files = [f for f in os.listdir(PRESETS_EXAMPLE_DIR) if f.endswith('.json')]
            for filename in example_files:
                src = os.path.join(PRESETS_EXAMPLE_DIR, filename)
                dst = os.path.join(PRESETS_DIR, filename)
                try:
                    with open(src, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    with open(dst, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"✅ 已复制示例预设: {filename}")
                except Exception as e:
                    print(f"⚠ 复制示例预设失败 {filename}: {e}")
            
            if example_files:
                print(f"✅ 已初始化 {len(example_files)} 个示例预设")
    except Exception as e:
        print(f"⚠ 初始化示例预设失败: {e}")

# 初始化示例预设
init_default_presets()


def validate_preset_name(name: str) -> tuple[bool, str]:
    """
    验证预设名称的安全性
    返回: (is_valid, error_message)
    """
    if not name or not name.strip():
        return False, "预设名称不能为空"
    
    name = name.strip()
    
    # 检查路径遍历攻击
    if '..' in name or '/' in name or '\\' in name:
        return False, f"非法名称: {name}"
    
    # 提取纯文件名
    safe_name = os.path.basename(name)
    if safe_name != name:
        return False, f"非法名称: {name}"
    
    # 验证最终路径仍在 presets 目录内
    target_path = os.path.realpath(os.path.join(PRESETS_DIR, f"{name}.json"))
    presets_real = os.path.realpath(PRESETS_DIR)
    if not target_path.startswith(presets_real):
        return False, f"路径遍历攻击被拒绝: {name}"
    
    return True, ""


def delete_preset_image(name):
    """删除指定预设的封面图（若存在）"""
    try:
        for f in os.listdir(PRESETS_IMAGES_DIR):
            if os.path.splitext(f)[0] == name:
                os.remove(os.path.join(PRESETS_IMAGES_DIR, f))
    except Exception as e:
        print(f"[Naiba] 删除预设封面失败 {name}: {e}")


def rename_preset_image(old_name, new_name):
    """原子重命名预设封面图（若存在）"""
    try:
        for f in os.listdir(PRESETS_IMAGES_DIR):
            if os.path.splitext(f)[0] == old_name:
                ext = os.path.splitext(f)[1]
                os.replace(
                    os.path.join(PRESETS_IMAGES_DIR, f),
                    os.path.join(PRESETS_IMAGES_DIR, f"{new_name}{ext}"),
                )
                break
    except Exception as e:
        print(f"[Naiba] 重命名预设封面失败 {old_name}->{new_name}: {e}")


# ============================================================
# API 路由：列出所有预设
# ============================================================
@PromptServer.instance.routes.get('/naiba/presets/list')
async def list_presets_handler(request):
    """列出所有可用的预设名称"""
    try:
        files = [f[:-5] for f in os.listdir(PRESETS_DIR) if f.endswith('.json')]
        files.sort()
        return web.json_response({"presets": files})
    except Exception as e:
        print(f"Error listing presets: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：加载预设
# ============================================================
@PromptServer.instance.routes.get('/naiba/presets/load')
async def load_preset_handler(request):
    """加载指定预设的数据"""
    name = request.query.get('name', '')
    
    # 验证名称
    is_valid, error_msg = validate_preset_name(name)
    if not is_valid:
        return web.json_response({"error": error_msg}, status=400)
    
    name = name.strip()
    file_path = os.path.join(PRESETS_DIR, f"{name}.json")
    
    if not os.path.exists(file_path):
        return web.json_response({"error": "预设不存在"}, status=404)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return web.json_response({"data": data})
    except Exception as e:
        print(f"Error loading preset {name}: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：保存预设
# ============================================================
@PromptServer.instance.routes.post('/naiba/presets/save')
async def save_preset_handler(request):
    """保存预设（如果已存在则覆盖）"""
    try:
        body = await request.json()
        data = body.get('data', [])
        return_data = body.get('return_data', False)
        name = (body.get('name', '') or '').strip()

        # 验证数据格式
        if not isinstance(data, list):
            return web.json_response({"error": "数据格式错误，需要是数组"}, status=400)

        if not return_data:
            # 验证名称（仅「保存预设」需要落盘文件名；「导出」只补全数据不写盘）
            is_valid, error_msg = validate_preset_name(name)
            if not is_valid:
                return web.json_response({"error": error_msg}, status=400)
        
        # 导出时为每个 LoRA 补全 sha256：优先用全局缓存（第一步批量同步/离线缓存已写入），
        # 缓存缺失且本地文件存在时现场计算并回写缓存。修复「预设导出不带 sha256」问题。
        from . import sha256_cache
        from .civitai_utils import CivitaiClient

        enriched = []
        loop = asyncio.get_event_loop()
        for item in data:
            new_item = dict(item)
            nm = item.get("name", "")
            sha = None
            if nm:
                sha = sha256_cache.get(nm)
                if not sha:
                    norm = nm.replace("\\", "/").lstrip("/")
                    if norm != nm:
                        sha = sha256_cache.get(norm)
                if not sha:
                    full = None
                    try:
                        full = folder_paths.get_full_path("loras", nm)
                    except Exception:
                        full = None
                    if full and os.path.exists(full) and sha256_cache.needs_update(nm, full):
                        try:
                            sha = await loop.run_in_executor(
                                None, CivitaiClient.calculate_sha256, full
                            )
                            if sha:
                                sha256_cache.update_entry(nm, sha, full)
                        except Exception as _e:  # noqa: BLE001
                            print(f"[Naiba] save_preset 计算 sha256 失败 {nm}: {_e}")
            if sha:
                new_item["sha256"] = sha
            enriched.append(new_item)

        # 「导出」模式：补齐 sha256 后直接返回数据，不落盘
        if return_data:
            return web.json_response({"data": enriched})

        file_path = os.path.join(PRESETS_DIR, f"{name}.json")

        # 保存预设
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(enriched, f, indent=2, ensure_ascii=False)
        
        return web.json_response({"success": True})
    except Exception as e:
        print(f"Error saving preset: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：解析/校验预设（导入时按 sha256 定位改名文件，非破坏性）
# ============================================================
def _lora_exists(name):
    """判断某 LoRA 相对名是否能在本地 loras 目录中定位到（不引发异常）。"""
    if not name:
        return False
    try:
        return folder_paths.get_full_path("loras", name) is not None
    except Exception:
        return False


def resolve_preset_items(items):
    """导入预设时按 sha256 重定位改名文件，并归一化名称。

    非破坏性：绝不丢弃任何条目，返回与输入一一对应的新列表。
    - 含 sha256 且本地存在同哈希文件 -> name 改为全局缓存中的真实相对路径（支持改名匹配）
    - 含 sha256 但本地无匹配 / 不含 sha256 -> 归一化 name（反斜杠转正斜杠、剥离前导斜杠），
      若可在本地定位则采用归一化名，否则保留原名（缺失项由前端以 (missing) 显示）
    """
    if not isinstance(items, list):
        return items
    from . import sha256_cache
    # sha256(小写) -> 本地真实相对路径，用于改名匹配
    cache = sha256_cache.build_sha_index()

    resolved = []
    for item in items:
        if not isinstance(item, dict):
            resolved.append(item)
            continue
        name = item.get("name", "") or ""
        sha = (item.get("sha256") or "").strip().lower()
        new_name = name

        # 1) 优先按 sha256 重定位到本地真实相对路径（支持改名/换目录匹配）
        if sha and sha in cache:
            new_name = cache[sha]
        else:
            # 2) 归一化 name（与导出/校验规则一致）：反斜杠->正斜杠，剥离前导斜杠
            norm = name.replace("\\", "/").lstrip("/")
            if norm and norm != name and _lora_exists(norm):
                new_name = norm
            elif name and _lora_exists(name):
                new_name = name  # 原名即可定位，保底

        new_item = dict(item)
        new_item["name"] = new_name
        resolved.append(new_item)
    return resolved


@PromptServer.instance.routes.post('/naiba/presets/resolve')
async def resolve_preset_handler(request):
    """导入预设时按 sha256 定位改名文件（非破坏性）。

    旧预设（保存时尚未写入 sha256）不含 sha256，会按归一化规则尝试匹配本地文件，
    仍匹配不到则保留原名（缺失项由前端以 (missing) 显示），可正常导入。
    """
    try:
        from . import sha256_cache
        body = await request.json()
        data = body.get('data', [])
        resolved = resolve_preset_items(data)
        return web.json_response({"data": resolved})
    except Exception as e:
        print(f"Error resolving preset: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：删除预设
# ============================================================
@PromptServer.instance.routes.delete('/naiba/presets/delete')
async def delete_preset_handler(request):
    """删除指定预设"""
    name = request.query.get('name', '')
    
    # 验证名称
    is_valid, error_msg = validate_preset_name(name)
    if not is_valid:
        return web.json_response({"error": error_msg}, status=400)
    
    name = name.strip()
    file_path = os.path.join(PRESETS_DIR, f"{name}.json")
    
    if not os.path.exists(file_path):
        return web.json_response({"error": "预设不存在"}, status=404)
    
    try:
        os.remove(file_path)
        # 同步删除该预设的封面图
        delete_preset_image(name)
        return web.json_response({"success": True})
    except Exception as e:
        print(f"Error deleting preset {name}: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：重命名预设
# ============================================================
@PromptServer.instance.routes.post('/naiba/presets/rename')
async def rename_preset_handler(request):
    """重命名预设（原子操作）"""
    try:
        body = await request.json()
        old_name = body.get('old_name', '').strip()
        new_name = body.get('new_name', '').strip()
        
        # 验证旧名称
        is_valid, error_msg = validate_preset_name(old_name)
        if not is_valid:
            return web.json_response({"error": f"原名称无效: {error_msg}"}, status=400)
        
        # 验证新名称
        is_valid, error_msg = validate_preset_name(new_name)
        if not is_valid:
            return web.json_response({"error": f"新名称无效: {error_msg}"}, status=400)
        
        old_path = os.path.join(PRESETS_DIR, f"{old_name}.json")
        new_path = os.path.join(PRESETS_DIR, f"{new_name}.json")
        
        # 检查原预设是否存在
        if not os.path.exists(old_path):
            return web.json_response({"error": "原预设不存在"}, status=404)
        
        # 检查新名称是否已存在
        if os.path.exists(new_path):
            return web.json_response({"error": "目标名称已存在"}, status=409)
        
        # 原子重命名
        os.replace(old_path, new_path)
        # 同步重命名封面图（若存在）
        rename_preset_image(old_name, new_name)
        return web.json_response({"success": True})
    except Exception as e:
        print(f"Error renaming preset: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：上传预设封面图（独立目录，与 LoRA 预览图隔离）
# ============================================================
@PromptServer.instance.routes.post('/naiba/presets/upload-image')
async def upload_preset_image_handler(request):
    """上传预设封面图到 presets/images/（与 LoRA 预览图目录隔离，互不冲突）"""
    try:
        reader = await request.multipart()
        preset_name = None
        image_data = None
        image_filename = None
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == 'name':
                preset_name = (await part.read()).decode('utf-8').strip()
            elif part.name == 'file':
                image_data = await part.read()
                image_filename = part.filename

        if not preset_name:
            return web.json_response({"error": "预设名称缺失"}, status=400)
        if not image_data:
            return web.json_response({"error": "未提供图片"}, status=400)

        # 复用预设名称安全校验（拒绝路径遍历）
        is_valid, error_msg = validate_preset_name(preset_name)
        if not is_valid:
            return web.json_response({"error": error_msg}, status=400)

        ext = os.path.splitext(image_filename)[1].lower() if image_filename else '.webp'
        if ext not in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
            ext = '.webp'

        image_path = os.path.join(PRESETS_IMAGES_DIR, f"{preset_name}{ext}")
        with open(image_path, 'wb') as f:
            f.write(image_data)

        return web.json_response({"success": True, "filename": f"{preset_name}{ext}"})
    except Exception as e:
        print(f"Error uploading preset image: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：获取预设封面图
# ============================================================
@PromptServer.instance.routes.get('/naiba/presets/image')
async def get_preset_image_handler(request):
    """获取预设封面图（404 表示无封面，前端显示占位图）"""
    name = request.query.get('name', '').strip()
    if not name:
        return web.Response(status=400, text="Missing preset name")

    is_valid, error_msg = validate_preset_name(name)
    if not is_valid:
        return web.Response(status=400, text=error_msg)

    try:
        for f in os.listdir(PRESETS_IMAGES_DIR):
            if os.path.splitext(f)[0] == name:
                image_path = os.path.join(PRESETS_IMAGES_DIR, f)
                with open(image_path, 'rb') as fh:
                    image_data = fh.read()
                # 依据真实文件内容（魔数）检测 MIME，避免扩展名与真实格式不符导致裂图
                content_type = detect_image_mime(image_data, os.path.splitext(f)[1])
                return web.Response(
                    body=image_data,
                    content_type=content_type,
                    headers={'Cache-Control': 'max-age=3600'}
                )
        return web.Response(status=404, text="No preset image")
    except Exception as e:
        return web.Response(status=500, text=str(e))


# ============================================================
# API 路由：获取 LoRA 预览图
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/preview')
async def get_lora_preview(request):
    """
    获取 LoRA 预览图
    查找与 LoRA 文件同名的图片文件（支持多种图片格式）
    """
    lora_name = request.query.get('name', '')
    
    if not lora_name:
        return web.Response(status=400, text="Missing lora name")
    
    # 安全检查：防止路径遍历攻击
    if '..' in lora_name or os.path.isabs(lora_name):
        return web.Response(status=400, text="Invalid lora name for security reasons")
    
    try:
        # 获取 LoRA 文件的完整路径
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path:
            return web.Response(status=404, text="LoRA not found")
        
        # 验证路径安全性：确保路径在 LoRA 目录内
        lora_dirs = folder_paths.get_folder_paths("loras")
        if not lora_dirs:
            return web.Response(status=500, text="LoRA directory not configured")
        
        # 检查路径是否在允许的目录内
        real_lora_path = os.path.realpath(lora_path)
        is_safe = False
        for lora_dir_root in lora_dirs:
            real_root = os.path.realpath(lora_dir_root)
            if real_lora_path.startswith(real_root + os.sep) or real_lora_path == real_root:
                is_safe = True
                break
        
        if not is_safe:
            print(f"SECURITY ALERT: Blocked attempt to access file outside LoRA directory: {lora_name}")
            return web.Response(status=403, text="Access denied")
        
        # 获取 LoRA 文件的目录和基本名称
        lora_dir = os.path.dirname(lora_path)
        lora_basename = os.path.splitext(os.path.basename(lora_path))[0]
        
        # 调试信息（仅在找不到预览图时打印）
        
        # 支持的图片扩展名（扩展支持更多格式）
        # 注意：.gif 已从静态搜索中移除，改为由视频/GIF 首帧抽帧逻辑处理
        # （同名 gif 会抽取首帧作为静态封面，避免浏览器动画开销）
        image_extensions = [
            '.png', '.jpg', '.jpeg', '.webp', '.bmp',  # 常见格式
            '.tiff', '.tif', '.svg',  # 额外格式
            '.avif', '.heic', '.heif',  # 现代格式
            '.ico', '.apng'  # 其他格式
        ]
        
        # 生成缓存键
        cache_key = f"lora_preview:{lora_name}"
        
        # 检查缓存
        cached_data = image_cache.get(cache_key)
        if cached_data:
            return web.Response(
                body=cached_data['data'],
                content_type=cached_data['content_type'],
                headers={'Cache-Control': 'max-age=3600'}
            )
        
        # 搜索模式列表（按优先级排序）：
        # 1. .custom.preview.* （用户自定义预览图 - 最高优先级）
        # 2. .preview.* （Civitai 同步的预览图）
        # 3. 直接同名图片（如 lora.png）
        search_patterns = [
            (lora_basename + '.custom.preview{}', "Custom preview"),
            (lora_basename + '.preview{}', "Civitai preview"),
            (lora_basename + '{}', "Direct image"),
        ]
        
        for pattern_template, _desc in search_patterns:
            for ext in image_extensions:
                preview_path = os.path.join(lora_dir, pattern_template.format(ext))
                if os.path.exists(preview_path):
                    # 读取并返回图片
                    with open(preview_path, 'rb') as f:
                        image_data = f.read()

                    # 依据真实文件内容（魔数）检测 MIME，避免扩展名与真实格式不符导致裂图
                    content_type = detect_image_mime(image_data, ext)
                    
                    # 存入缓存
                    image_cache.set(cache_key, {
                        'data': image_data,
                        'content_type': content_type,
                        'path': preview_path
                    })
                    
                    return web.Response(
                        body=image_data,
                        content_type=content_type,
                        headers={'Cache-Control': 'max-age=3600'}
                    )
        
        # 没找到静态预览图 → 尝试从同名视频/GIF 抽取首帧作为静态封面
        cached_cover = os.path.join(lora_dir, lora_basename + ".naiba.preview.png")
        cover_bytes = None
        if os.path.exists(cached_cover):
            with open(cached_cover, "rb") as f:
                cover_bytes = f.read()
        else:
            video_gif_cands = [lora_basename + ext for ext in
                               (".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".gif")]
            # 兼容 Civitai 同步 / 用户自定义 gif 预览封面（同样抽首帧）
            video_gif_cands += [lora_basename + ".preview.gif",
                                lora_basename + ".custom.preview.gif"]
            for cand in video_gif_cands:
                cand_path = os.path.join(lora_dir, cand)
                if os.path.exists(cand_path):
                    frame = extract_first_frame_as_png(cand_path)
                    if frame:
                        try:
                            with open(cached_cover, "wb") as f:
                                f.write(frame)
                        except Exception as e:  # noqa: BLE001
                            print(f"[Naiba] 写入首帧缓存失败: {e}")
                        cover_bytes = frame
                        break

        if cover_bytes:
            image_cache.set(cache_key, {
                'data': cover_bytes,
                'content_type': "image/png",
                'path': cached_cover,
            })
            return web.Response(
                body=cover_bytes,
                content_type="image/png",
                headers={'Cache-Control': 'max-age=3600'}
            )

        # 没找到预览图
        return web.Response(status=404, text="No preview found")
        
    except Exception as e:
        print(f"Error getting lora preview: {e}")
        return web.Response(status=500, text=str(e))


# ============================================================
# API 路由：清理图片缓存
# ============================================================
@PromptServer.instance.routes.post('/naiba/cache/clear')
async def clear_image_cache(request):
    """清理图片缓存"""
    try:
        cache_size = image_cache.size()
        image_cache.clear()
        print(f"[VisualLoRA] Cache cleared: {cache_size} items removed")
        return web.json_response({
            "success": True, 
            "cleared_items": cache_size,
            "message": f"已清理 {cache_size} 个缓存条目"
        })
    except Exception as e:
        print(f"Error clearing cache: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：获取缓存状态
# ============================================================
@PromptServer.instance.routes.get('/naiba/cache/status')
async def get_cache_status(request):
    """获取缓存状态信息"""
    try:
        return web.json_response({
            "success": True,
            "cache_size": image_cache.size(),
            "max_size": image_cache.max_size,
            "ttl": image_cache.ttl
        })
    except Exception as e:
        print(f"Error getting cache status: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：Civitai 同步
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/civitai-sync')
async def civitai_sync_handler(request):
    """
    触发从Civitai同步LoRA元数据和预览图
    
    参数:
        name: LoRA文件名（必需）
        api_key: Civitai API密钥（可选）
        nsfw_level: NSFW级别（可选，默认为R）
        force: 是否强制更新（可选，默认为false）
    """
    lora_name = request.query.get('name', '')
    api_key = request.query.get('api_key', '')
    nsfw_level = request.query.get('nsfw_level', 'R')
    force = request.query.get('force', 'false').lower() == 'true'
    
    if not lora_name:
        return web.json_response({"error": "Missing lora name"}, status=400)
    
    # 安全检查
    if '..' in lora_name or os.path.isabs(lora_name):
        return web.json_response({"error": "Invalid lora name"}, status=400)
    
    try:
        # 导入Civitai工具类
        from .civitai_utils import (
            sync_lora_from_civitai,
            NSFW_LEVELS,
            find_local_preview,
            get_metadata_path,
            load_cached_metadata,
        )
        
        # 获取LoRA文件路径
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            return web.json_response({"error": "LoRA file not found"}, status=404)
        
        # 验证路径安全性
        lora_dirs = folder_paths.get_folder_paths("loras")
        real_lora_path = os.path.realpath(lora_path)
        is_safe = False
        for lora_dir_root in lora_dirs:
            real_root = os.path.realpath(lora_dir_root)
            if real_lora_path.startswith(real_root + os.sep) or real_lora_path == real_root:
                is_safe = True
                break
        
        if not is_safe:
            return web.json_response({"error": "Access denied"}, status=403)
        
        # 获取NSFW级别阈值
        max_nsfw = NSFW_LEVELS.get(nsfw_level, NSFW_LEVELS["R"])
        
        # 处理API密钥
        api_key_value = api_key.strip() if api_key else None
        
        # 执行同步
        metadata, preview_path, error = await sync_lora_from_civitai(
            lora_path, api_key_value, max_nsfw, force
        )
        
        if error:
            return web.json_response({
                "success": False,
                "error": error,
                "metadata": metadata,
                "preview_path": preview_path
            })
        
        # 同步成功后清除该LoRA的图片缓存，确保前端能加载新图片
        cache_key = f"lora_preview:{lora_name}"
        image_cache.delete(cache_key)
        print(f"[VisualLoRA] Cache cleared for: {lora_name}")
        
        return web.json_response({
            "success": True,
            "metadata": metadata,
            "preview_path": preview_path,
            "message": "Sync completed successfully"
        })
        
    except Exception as e:
        print(f"Error in civitai sync: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：获取 LoRA 元数据
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/metadata')
async def get_lora_metadata_handler(request):
    """
    获取LoRA元数据（优先从缓存获取）
    
    参数:
        name: LoRA文件名（必需）
    """
    lora_name = request.query.get('name', '')
    
    if not lora_name:
        return web.json_response({"error": "Missing lora name"}, status=400)
    
    # 安全检查
    if '..' in lora_name or os.path.isabs(lora_name):
        return web.json_response({"error": "Invalid lora name"}, status=400)
    
    try:
        # 导入Civitai工具类
        from .civitai_utils import (
            get_metadata_path,
            load_cached_metadata,
            find_local_preview,
        )
        
        # 获取LoRA文件路径
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            return web.json_response({"error": "LoRA file not found"}, status=404)
        
        # 验证路径安全性
        lora_dirs = folder_paths.get_folder_paths("loras")
        real_lora_path = os.path.realpath(lora_path)
        is_safe = False
        for lora_dir_root in lora_dirs:
            real_root = os.path.realpath(lora_dir_root)
            if real_lora_path.startswith(real_root + os.sep) or real_lora_path == real_root:
                is_safe = True
                break
        
        if not is_safe:
            return web.json_response({"error": "Access denied"}, status=403)
        
        # 获取元数据路径
        metadata_path = get_metadata_path(lora_path)
        
        # 加载元数据
        metadata = load_cached_metadata(metadata_path)
        
        # 查找本地预览图
        local_preview = find_local_preview(lora_path)
        
        return web.json_response({
            "success": True,
            "metadata": metadata,
            "local_preview": local_preview,
            "has_cached_metadata": metadata is not None,
            "has_local_preview": local_preview is not None
        })
        
    except Exception as e:
        print(f"Error getting lora metadata: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：批量同步所有LoRA（SSE 流式进度推送）
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/batch-sync')
async def batch_sync_handler(request):
    """
    批量同步LoRA文件的元数据和预览图（使用SSE实时推送进度）
    
    参数:
        api_key: Civitai API密钥（可选）
        nsfw_level: NSFW级别（可选，默认为R）
        mode: 同步模式（可选，默认为"sync_unsynced"）
            - "sync_unsynced": 只同步未同步的（跳过已有缓存的）
            - "sync_all": 同步全部（强制更新已同步的）
        folder: 指定文件夹路径（可选，空表示全部）
    
    返回:
        SSE 流，每个事件格式：
        - progress: {"current": N, "total": N, "name": "xxx", "status": "syncing"}
        - item_done: {"current": N, "total": N, "name": "xxx", "status": "success|failed", ...}
        - complete: {"results": {...}}
        - error: {"error": "xxx"}
    """
    try:
        # 解析请求体
        body = await request.json()
        api_key = body.get('api_key', '')
        nsfw_level = body.get('nsfw_level', 'R')
        mode = body.get('mode', 'sync_unsynced')
        target_folder = body.get('folder', '')
        
        # 导入Civitai工具类
        from .civitai_utils import (
            sync_lora_from_civitai,
            NSFW_LEVELS,
            get_metadata_path,
            load_cached_metadata,
            CivitaiClient,
        )
        from . import sha256_cache
        
        # 获取NSFW级别阈值
        max_nsfw = NSFW_LEVELS.get(nsfw_level, NSFW_LEVELS["R"])
        
        # 处理API密钥
        api_key_value = api_key.strip() if api_key else None
        
        # 强制更新模式
        force = (mode == 'sync_all')
        
        # 获取所有LoRA文件路径
        all_lora_paths = []
        lora_dirs = folder_paths.get_folder_paths("loras")
        
        for lora_dir in lora_dirs:
            if not os.path.exists(lora_dir):
                continue
            
            # 遍历目录
            for root, dirs, files in os.walk(lora_dir):
                # 如果指定了文件夹，只处理该文件夹
                if target_folder:
                    rel_path = os.path.relpath(root, lora_dir)
                    if not rel_path.startswith(target_folder) and rel_path != '.':
                        continue
                
                for file in files:
                    if file.lower().endswith(('.safetensors', '.pt', '.ckpt', '.pth')):
                        file_path = os.path.join(root, file)
                        # 计算相对路径作为LoRA名称
                        rel_path = os.path.relpath(file_path, lora_dir)
                        all_lora_paths.append((rel_path, file_path))
        
        # 根据模式过滤需要同步的LoRA
        lora_paths = []
        skipped_count = 0
        
        for lora_name, lora_path in all_lora_paths:
            # sync_all 模式：不跳过任何
            # sync_unsynced 模式：也全部进入 sync_lora_from_civitai，由其内部处理缓存
            lora_paths.append((lora_name, lora_path))
        
        # 同步结果
        results = {
            "total": len(all_lora_paths),
            "to_sync": len(lora_paths),
            "already_synced": skipped_count,
            "success": 0,
            "failed": 0,
            "details": []
        }
        
        # 创建 SSE 流式响应
        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            }
        )
        await response.prepare(request)
        
        # 发送初始进度信息（包含跳过的数量）
        import asyncio
        import json
        
        async def send_sse(event_type, data):
            """发送SSE事件"""
            msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
            await response.write(msg.encode('utf-8'))
        
        # 发送开始事件
        await send_sse("start", {
            "total": len(all_lora_paths),
            "to_sync": len(lora_paths),
            "already_synced": skipped_count
        })
        
        # 批量同步
        current_index = 0
        for lora_name, lora_path in lora_paths:
            current_index += 1
            
            # 发送进度事件（正在同步）
            await send_sse("progress", {
                "current": current_index,
                "total": len(lora_paths),
                "name": lora_name,
                "status": "syncing"
            })
            
            try:
                # 执行同步
                metadata, preview_path, error = await sync_lora_from_civitai(lora_path, api_key_value, max_nsfw, force)
                
                # 无论同步成功与否，都尽量把该 LoRA 的 sha256 写入全局缓存
                # （sync_lora_from_civitai 在成功/失败/无数据各分支都会把 hash 写入 .civitai.info.json）
                try:
                    file_hash = None
                    if metadata and isinstance(metadata, dict):
                        file_hash = metadata.get("hash")
                    if not file_hash:
                        meta_cached = load_cached_metadata(get_metadata_path(lora_path))
                        if meta_cached:
                            file_hash = meta_cached.get("hash")
                    if not file_hash and sha256_cache.needs_update(lora_name, lora_path):
                        _loop = asyncio.get_event_loop()
                        file_hash = await _loop.run_in_executor(
                            None, CivitaiClient.calculate_sha256, lora_path
                        )
                    if file_hash:
                        sha256_cache.update_entry(lora_name, file_hash, lora_path)
                except Exception as _ce:  # noqa: BLE001
                    print(f"[Naiba-SHA256Cache] 缓存 {lora_name} 失败: {_ce}")
                
                if error:
                    results["failed"] += 1
                    results["details"].append({
                        "name": lora_name,
                        "status": "failed",
                        "error": error
                    })
                    # 发送失败事件
                    await send_sse("item_done", {
                        "current": current_index,
                        "total": len(lora_paths),
                        "name": lora_name,
                        "status": "failed",
                        "error": error
                    })
                else:
                    # 同步成功，清除该LoRA的图片缓存
                    cache_key = f"lora_preview:{lora_name}"
                    image_cache.delete(cache_key)
                    
                    results["success"] += 1
                    results["details"].append({
                        "name": lora_name,
                        "status": "success",
                        "preview_path": preview_path,
                        "metadata": metadata
                    })
                    # 发送成功事件
                    await send_sse("item_done", {
                        "current": current_index,
                        "total": len(lora_paths),
                        "name": lora_name,
                        "status": "success",
                        "preview_path": preview_path
                    })
                
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "name": lora_name,
                    "status": "error",
                    "error": str(e)
                })
                # 发送错误事件
                await send_sse("item_done", {
                    "current": current_index,
                    "total": len(lora_paths),
                    "name": lora_name,
                    "status": "failed",
                    "error": str(e)
                })
        
        # 让出控制权，避免阻塞
        await asyncio.sleep(0)
        
        # 发送完成事件
        await send_sse("complete", {
            "results": results,
            "message": f"Batch sync completed: {results['success']} success, {results['failed']} failed"
        })
        
        await response.write_eof()
        return response
        
    except Exception as e:
        print(f"Error in batch sync: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)


# ============================================================
# API 路由：查询全局 sha256 缓存状态
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/sha256-cache')
async def sha256_cache_status_handler(request):
    """
    返回全局 sha256 缓存状态：
        cached_count : 已缓存 sha256 的条目数
        total_loras  : 本地 LoRA 总数
        missing_count: 尚未缓存的本地 LoRA 数
        all_cached   : 是否所有本地 LoRA 都已缓存
    可选 query: include_map=1 时附带完整 cache 映射与 missing 列表（前 200 条）。
    """
    try:
        from . import sha256_cache

        include_map = request.query.get('include_map', '') in ('1', 'true', 'yes')
        cache = sha256_cache.get_all()
        cached_count = len(cache)

        try:
            local_loras = folder_paths.get_filename_list("loras")
        except Exception:
            local_loras = []
        # 统一分隔符后比较
        local_norm = [str(n).replace("\\", "/") for n in local_loras]
        total = len(local_norm)
        missing = [n for n in local_norm if n not in cache]

        resp = {
            "success": True,
            "cached_count": cached_count,
            "total_loras": total,
            "missing_count": len(missing),
            "all_cached": (total > 0 and len(missing) == 0),
        }
        if include_map:
            resp["cache"] = cache
            resp["missing"] = missing[:200]
        return web.json_response(resp)
    except Exception as e:
        print(f"[Naiba] sha256-cache status error: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)


# ============================================================
# API 路由：纯离线计算所有本地 LoRA 的 sha256 并写入全局缓存（不查询 C 站）
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/cache-sha256-only')
async def cache_sha256_only_handler(request):
    """
    仅扫描本地所有 LoRA 文件并计算 sha256，写入全局缓存；完全不调用 Civitai。
    用于网络不佳时先把本地 sha256 全部收齐，供后续上传预设做本地匹配。
    通过 SSE 流式返回进度。
    请求体（可选）：{"folder": "子目录名"} 仅处理指定子目录。
    """
    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        target_folder = (body.get("folder") or "").strip()

        from .civitai_utils import CivitaiClient
        from . import sha256_cache

        # 收集所有本地 LoRA 文件路径
        all_lora_paths = []
        lora_dirs = folder_paths.get_folder_paths("loras")
        for lora_dir in lora_dirs:
            if not os.path.exists(lora_dir):
                continue
            for root, dirs, files in os.walk(lora_dir):
                if target_folder:
                    rel_path = os.path.relpath(root, lora_dir)
                    if not rel_path.startswith(target_folder) and rel_path != ".":
                        continue
                for file in files:
                    if file.lower().endswith((".safetensors", ".pt", ".ckpt", ".pth")):
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, lora_dir)
                        all_lora_paths.append((rel_path, file_path))

        results = {
            "total": len(all_lora_paths),
            "cached": 0,
            "skipped": 0,   # 缓存已是最新，跳过
            "failed": 0,
            "details": [],
        }

        # 创建 SSE 流式响应
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)

        import asyncio as _asyncio
        import json as _json

        async def send_sse(event_type, data):
            msg = f"event: {event_type}\ndata: {_json.dumps(data)}\n\n"
            await response.write(msg.encode("utf-8"))

        await send_sse("start", {"total": len(all_lora_paths)})

        loop = _asyncio.get_event_loop()
        current_index = 0
        for lora_name, lora_path in all_lora_paths:
            current_index += 1
            await send_sse("progress", {
                "current": current_index,
                "total": len(all_lora_paths),
                "name": lora_name,
                "status": "hashing",
            })
            try:
                if not sha256_cache.needs_update(lora_name, lora_path):
                    results["skipped"] += 1
                    await send_sse("item_done", {
                        "current": current_index,
                        "total": len(all_lora_paths),
                        "name": lora_name,
                        "status": "skipped",
                    })
                    continue
                file_hash = await loop.run_in_executor(
                    None, CivitaiClient.calculate_sha256, lora_path
                )
                if file_hash:
                    sha256_cache.update_entry(lora_name, file_hash, lora_path)
                    results["cached"] += 1
                    status = "cached"
                else:
                    results["failed"] += 1
                    status = "failed"
                await send_sse("item_done", {
                    "current": current_index,
                    "total": len(all_lora_paths),
                    "name": lora_name,
                    "status": status,
                })
            except Exception as e:
                results["failed"] += 1
                await send_sse("item_done", {
                    "current": current_index,
                    "total": len(all_lora_paths),
                    "name": lora_name,
                    "status": "failed",
                    "error": str(e),
                })

        await _asyncio.sleep(0)

        # 收尾：返回缓存概览
        cache = sha256_cache.get_all()
        local_norm = [str(n).replace("\\", "/")
                      for n in folder_paths.get_filename_list("loras")]
        total = len(local_norm)
        missing = [n for n in local_norm if n not in cache]
        results["cached_count"] = len(cache)
        results["missing_count"] = len(missing)
        results["all_cached"] = (total > 0 and len(missing) == 0)

        await send_sse("complete", {
            "results": results,
            "cached_count": len(cache),
            "missing_count": len(missing),
            "all_cached": results["all_cached"],
            "message": (
                f"SHA256 缓存完成：新增/更新 {results['cached']} 个，"
                f"跳过 {results['skipped']} 个，失败 {results['failed']} 个；"
                f"当前已缓存共 {len(cache)} 个"
            ),
        })

        await response.write_eof()
        return response

    except Exception as e:
        print(f"[Naiba] cache-sha256-only error: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)


# ============================================================
# API 路由：上传预设校验（本地匹配 + Civitai 实时查询，四分类）
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/verify-preset')
async def verify_preset_handler(request):
    """
    上传预设校验聚合接口（SSE 流式，实时回传进度）：
      1) 按预设条目中的 sha256 与本地全局缓存 / 磁盘匹配，判断本地是否存在；
      2) 对去重后的唯一 sha256 实时查询 Civitai，判断是否上站；
    事件流格式（每行 data: {json}\\n\\n）:
      {"type":"progress","stage":"init","done":0,"total":N,"msg":"..."}
      {"type":"progress","stage":"civitai","done":k,"total":N,"msg":"已查询 Civitai k/N"}
      {"type":"done","success":true,"green":[...],"gray":[...],"not_found":[...],"no_sha256":[...],"summary":{...}}
      {"type":"error","message":"..."}
    四分类：
      green      本地存在且 C 站上也有（含 civitai_info，可显示绿色卡片）
      gray       本地不存在但 C 站上有（含 civitai_info + 下载地址，灰色卡片）
      not_found  本地不存在且 C 站上也没有（置底「找不到地址」）
      no_sha256  预设条目本身没有 sha256（置底「预设内无sha256」）
    请求体：{"lora_list":[{"name","sha256"?,"strength_model","strength_clip","enabled"}...], "api_key":""}
    """
    try:
        body = await request.json()
        lora_list = body.get("lora_list", [])
        api_key = (body.get("api_key") or "").strip()
        if not isinstance(lora_list, list):
            return web.json_response({"error": "lora_list 需为数组"}, status=400)

        from . import sha256_cache
        from .civitai_utils import CivitaiClient, build_civitai_version_info

        # 全局缓存：sha256(小写) -> 相对名，用于本地存在性匹配
        cache = sha256_cache.get_all()
        sha_to_name = {}
        for n, info in cache.items():
            if isinstance(info, dict) and info.get("sha256"):
                sha_to_name[info["sha256"].lower()] = n

        def is_local(name, sha):
            norm = (name or "").replace("\\", "/").lstrip("/")
            if norm:
                try:
                    fp = folder_paths.get_full_path("loras", norm)
                except Exception:
                    fp = None
                if fp and os.path.exists(fp):
                    return True, norm
            if sha:
                key = sha.lower()
                if key in sha_to_name:
                    return True, sha_to_name[key]
            return False, None

        # 收集需查 Civitai 的唯一 sha256（去重，仅限有 sha256 的条目）
        unique_shas = []
        seen = set()
        for item in lora_list:
            sha = (item.get("sha256") or "").strip().lower()
            if sha and sha not in seen:
                seen.add(sha)
                unique_shas.append(sha)

        total = len(unique_shas)

        # ---- 建立 SSE 流式响应 ----
        prepared = False
        resp = web.StreamResponse()
        resp.headers["Content-Type"] = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        resp.headers["Connection"] = "keep-alive"
        resp.enable_chunked_encoding()
        await resp.prepare(request)
        prepared = True

        write_lock = asyncio.Lock()

        async def send(obj):
            payload = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
            async with write_lock:
                await resp.write(payload.encode("utf-8"))

        await send({
            "type": "progress", "stage": "init", "done": 0, "total": total,
            "msg": f"准备校验 {len(lora_list)} 条（唯一 sha256 {total} 个）",
        })

        sha_info_map = {}
        client = None
        if unique_shas:
            client = CivitaiClient(api_key=api_key)
            sem = asyncio.Semaphore(6)
            done_count = 0

            async def _query(sha):
                nonlocal done_count
                async with sem:
                    info = None
                    try:
                        data, err = await client.query_by_hash(sha)
                        if data and isinstance(data, dict):
                            info = build_civitai_version_info(data)
                    except Exception as _e:  # noqa: BLE001
                        print(f"[Naiba] verify-preset 查询 {sha} 失败: {_e}")
                    sha_info_map[sha] = info
                done_count += 1
                await send({
                    "type": "progress", "stage": "civitai",
                    "done": done_count, "total": total,
                    "msg": f"已查询 Civitai {done_count}/{total}",
                })

            await asyncio.gather(*[_query(s) for s in unique_shas])
        else:
            await send({
                "type": "progress", "stage": "civitai", "done": 0, "total": 0,
                "msg": "无 sha256 可查询 Civitai",
            })

        # 分类
        green, gray, not_found, no_sha256 = [], [], [], []
        for item in lora_list:
            name = item.get("name", "")
            sha = (item.get("sha256") or "").strip().lower()
            entry = {
                "name": name,
                "sha256": sha or None,
                "strength_model": item.get("strength_model", 1.0),
                "strength_clip": item.get("strength_clip", 1.0),
                "enabled": item.get("enabled", True),
            }
            if not sha:
                no_sha256.append(entry)
                continue
            local, local_name = is_local(name, sha)
            info = sha_info_map.get(sha)
            if local:
                entry["local_name"] = local_name
                entry["civitai_found"] = info is not None
                entry["civitai_info"] = info
                green.append(entry)
            elif info is not None:
                entry["civitai_info"] = info
                gray.append(entry)
            else:
                entry["civitai_info"] = None
                not_found.append(entry)

        await send({
            "type": "done",
            "success": True,
            "green": green,
            "gray": gray,
            "not_found": not_found,
            "no_sha256": no_sha256,
            "summary": {
                "total": len(lora_list),
                "green": len(green),
                "gray": len(gray),
                "not_found": len(not_found),
                "no_sha256": len(no_sha256),
            },
        })
        await resp.write_eof()
        return resp
    except Exception as e:
        print(f"[Naiba] verify-preset error: {e}")
        if "prepared" in dir() and prepared:
            try:
                payload = "data: " + json.dumps(
                    {"type": "error", "message": str(e)}, ensure_ascii=False
                ) + "\n\n"
                await resp.write(payload.encode("utf-8"))
                await resp.write_eof()
                return resp
            except Exception:
                pass
        return web.json_response({"success": False, "error": str(e)}, status=500)
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


# ============================================================
# 收藏功能存储目录
# ============================================================
FAVORITES_DIR = os.path.join(os.path.dirname(__file__), "favorites")
FAVORITES_IMAGES_DIR = os.path.join(FAVORITES_DIR, "images")
os.makedirs(FAVORITES_DIR, exist_ok=True)
os.makedirs(FAVORITES_IMAGES_DIR, exist_ok=True)


def get_favorites_data_path() -> str:
    """获取收藏数据文件路径"""
    return os.path.join(FAVORITES_DIR, "favorites.json")


def load_favorites_data() -> dict:
    """加载所有收藏数据"""
    path = get_favorites_data_path()
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        print(f"[Naiba] Error loading favorites: {e}")
    return {}


def save_favorites_data(data: dict) -> bool:
    """保存收藏数据"""
    path = get_favorites_data_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Naiba] Error saving favorites: {e}")
        return False


def is_lora_favorited(lora_name: str) -> bool:
    """检查 LoRA 是否被收藏"""
    favorites = load_favorites_data()
    return lora_name in favorites


# ============================================================
# API 路由：获取所有收藏列表
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/favorites/list')
async def list_favorites_handler(request):
    """获取所有收藏的 LoRA 列表"""
    try:
        favorites = load_favorites_data()
        return web.json_response({
            "success": True,
            "favorites": favorites
        })
    except Exception as e:
        print(f"Error listing favorites: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：添加收藏
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/favorites/add')
async def add_favorite_handler(request):
    """
    添加 LoRA 到收藏
    
    请求体:
        name: LoRA 文件名（必需）
        custom_prompt: 自定义提示词（可选）
        custom_image_path: 自定义图片路径（可选）
    """
    try:
        body = await request.json()
        lora_name = body.get('name', '').strip()
        custom_prompt = body.get('custom_prompt', '')
        custom_image_path = body.get('custom_image_path', '')
        
        if not lora_name:
            return web.json_response({"error": "LoRA name is required"}, status=400)
        
        # 安全检查
        if '..' in lora_name or os.path.isabs(lora_name):
            return web.json_response({"error": "Invalid lora name"}, status=400)
        
        favorites = load_favorites_data()
        
        # 如果已收藏，保留原有数据并更新
        existing = favorites.get(lora_name, {})
        
        favorites[lora_name] = {
            "name": lora_name,
            "custom_prompt": custom_prompt or existing.get("custom_prompt", ""),
            "custom_image_path": custom_image_path or existing.get("custom_image_path", ""),
            "favorited_at": existing.get("favorited_at", __import__('datetime').datetime.now().isoformat())
        }
        
        if save_favorites_data(favorites):
            return web.json_response({
                "success": True,
                "favorite": favorites[lora_name]
            })
        else:
            return web.json_response({"error": "Failed to save favorite"}, status=500)
            
    except Exception as e:
        print(f"Error adding favorite: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：取消收藏
# ============================================================
@PromptServer.instance.routes.delete('/naiba/lora/favorites/remove')
async def remove_favorite_handler(request):
    """
    取消收藏 LoRA
    
    参数:
        name: LoRA 文件名（必需）
    """
    lora_name = request.query.get('name', '').strip()
    
    if not lora_name:
        return web.json_response({"error": "LoRA name is required"}, status=400)
    
    # 安全检查
    if '..' in lora_name or os.path.isabs(lora_name):
        return web.json_response({"error": "Invalid lora name"}, status=400)
    
    try:
        favorites = load_favorites_data()
        
        if lora_name not in favorites:
            return web.json_response({"error": "LoRA not in favorites"}, status=404)
        
        # 删除自定义图片（如果存在）
        favorite = favorites[lora_name]
        custom_image_path = favorite.get("custom_image_path", "")
        if custom_image_path and os.path.exists(custom_image_path):
            try:
                os.remove(custom_image_path)
            except Exception as e:
                print(f"[Naiba] Warning: Could not delete custom image: {e}")
        
        del favorites[lora_name]
        
        if save_favorites_data(favorites):
            return web.json_response({"success": True})
        else:
            return web.json_response({"error": "Failed to save favorites"}, status=500)
            
    except Exception as e:
        print(f"Error removing favorite: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：更新收藏信息
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/favorites/update')
async def update_favorite_handler(request):
    """
    更新收藏的 LoRA 信息（提示词、图片路径等）
    
    请求体:
        name: LoRA 文件名（必需）
        custom_prompt: 自定义提示词（可选）
        custom_image_path: 自定义图片路径（可选）
    """
    try:
        body = await request.json()
        lora_name = body.get('name', '').strip()
        
        if not lora_name:
            return web.json_response({"error": "LoRA name is required"}, status=400)
        
        # 安全检查
        if '..' in lora_name or os.path.isabs(lora_name):
            return web.json_response({"error": "Invalid lora name"}, status=400)
        
        favorites = load_favorites_data()
        
        if lora_name not in favorites:
            return web.json_response({"error": "LoRA not in favorites"}, status=404)
        
        # 更新字段
        if 'custom_prompt' in body:
            favorites[lora_name]['custom_prompt'] = body['custom_prompt']
        if 'custom_image_path' in body:
            favorites[lora_name]['custom_image_path'] = body['custom_image_path']
        
        if save_favorites_data(favorites):
            return web.json_response({
                "success": True,
                "favorite": favorites[lora_name]
            })
        else:
            return web.json_response({"error": "Failed to save favorite"}, status=500)
            
    except Exception as e:
        print(f"Error updating favorite: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：上传自定义收藏图片
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/favorites/upload-image')
async def upload_favorite_image_handler(request):
    """
    上传自定义收藏图片
    
    表单数据:
        file: 图片文件
        name: LoRA 文件名
    """
    try:
        reader = await request.multipart()
        
        lora_name = None
        image_data = None
        image_filename = None
        
        # 解析 multipart 数据
        while True:
            part = await reader.next()
            if part is None:
                break
            
            if part.name == 'name':
                lora_name = (await part.read()).decode('utf-8').strip()
            elif part.name == 'file':
                image_data = await part.read()
                image_filename = part.filename
        
        if not lora_name:
            return web.json_response({"error": "LoRA name is required"}, status=400)
        
        if not image_data:
            return web.json_response({"error": "No image file provided"}, status=400)
        
        # 安全检查
        if '..' in lora_name or os.path.isabs(lora_name):
            return web.json_response({"error": "Invalid lora name"}, status=400)
        
        # 生成安全的文件名
        safe_name = lora_name.replace('/', '_').replace('\\', '_').replace('.', '_')
        ext = os.path.splitext(image_filename)[1] if image_filename else '.webp'
        if ext not in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
            ext = '.webp'
        
        image_filename = f"{safe_name}_custom{ext}"
        image_path = os.path.join(FAVORITES_IMAGES_DIR, image_filename)
        
        # 保存图片
        with open(image_path, 'wb') as f:
            f.write(image_data)
        
        # 更新收藏数据
        favorites = load_favorites_data()
        if lora_name in favorites:
            favorites[lora_name]['custom_image_path'] = image_path
            save_favorites_data(favorites)
        
        return web.json_response({
            "success": True,
            "image_path": image_path
        })
        
    except Exception as e:
        print(f"Error uploading favorite image: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：获取收藏的自定义图片
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/favorites/image')
async def get_favorite_image_handler(request):
    """
    获取收藏的自定义图片
    
    参数:
        name: LoRA 文件名
    """
    lora_name = request.query.get('name', '').strip()
    
    if not lora_name:
        return web.Response(status=400, text="Missing lora name")
    
    # 安全检查
    if '..' in lora_name or os.path.isabs(lora_name):
        return web.Response(status=400, text="Invalid lora name")
    
    try:
        favorites = load_favorites_data()
        
        if lora_name not in favorites:
            return web.Response(status=404, text="Not in favorites")
        
        custom_image_path = favorites[lora_name].get("custom_image_path", "")
        
        if not custom_image_path or not os.path.exists(custom_image_path):
            return web.Response(status=404, text="No custom image")
        
        # 读取图片
        with open(custom_image_path, 'rb') as f:
            image_data = f.read()

        # 依据真实文件内容（魔数）检测 MIME，避免扩展名与真实格式不符导致裂图
        content_type = detect_image_mime(image_data, os.path.splitext(custom_image_path)[1])
        
        return web.Response(
            body=image_data,
            content_type=content_type,
            headers={'Cache-Control': 'max-age=3600'}
        )
        
    except Exception as e:
        print(f"Error getting favorite image: {e}")
        return web.Response(status=500, text=str(e))


# ============================================================
# API 路由：获取 Civitai 元数据预览图（仅同步封面，不含自定义封面）
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/metadata/preview')
async def get_metadata_preview_handler(request):
    """
    获取 Civitai 同步的元数据预览图（即 {lora}.preview.*，不含用户自定义封面）

    参数:
        name: LoRA文件名（必需）
    """
    lora_name = request.query.get('name', '').strip()

    if not lora_name:
        return web.Response(status=400, text="Missing lora name")

    # 验证LoRA名称并返回完整路径
    is_valid, error_msg, lora_path = validate_lora_name(lora_name)
    if not is_valid:
        status = 400 if "Missing" in error_msg else 404 if "not found" in error_msg else 403
        return web.Response(status=status, text=error_msg)

    try:
        metadata_preview = find_metadata_preview(lora_path)
        if not metadata_preview or not os.path.exists(metadata_preview):
            return web.Response(status=404, text="No metadata preview found")

        with open(metadata_preview, 'rb') as f:
            image_data = f.read()

        # 依据真实文件内容（魔数）检测 MIME，避免扩展名与真实格式不符导致裂图
        content_type = detect_image_mime(image_data, os.path.splitext(metadata_preview)[1])

        return web.Response(
            body=image_data,
            content_type=content_type,
            headers={'Cache-Control': 'max-age=3600'}
        )
    except Exception as e:
        print(f"Error getting metadata preview: {e}")
        return web.Response(status=500, text=str(e))


# ============================================================
# API 路由：删除 Civitai 元数据预览图（仅删除同步封面，保留自定义封面）
# ============================================================
@PromptServer.instance.routes.delete('/naiba/lora/metadata/preview')
async def delete_metadata_preview_handler(request):
    """
    删除 Civitai 同步的元数据预览图（{lora}.preview.*）

    仅删除 Civitai 元数据封面，不会影响用户自定义封面 (.custom.preview.*)
    或同名直接图片 (lora.png)。

    参数:
        name: LoRA文件名（必需）
    """
    lora_name = request.query.get('name', '').strip()

    if not lora_name:
        return web.json_response({"error": "Missing lora name"}, status=400)

    # 验证LoRA名称并返回完整路径
    is_valid, error_msg, lora_path = validate_lora_name(lora_name)
    if not is_valid:
        status = 400 if "Missing" in error_msg else 404 if "not found" in error_msg else 403
        return web.json_response({"error": error_msg}, status=status)

    try:
        deleted = delete_metadata_preview(lora_path)

        # 清除该LoRA的图片缓存，确保前端能加载最新预览图（删除后会回退到自定义封面/无图）
        cache_key = f"lora_preview:{lora_name}"
        image_cache.delete(cache_key)

        return web.json_response({
            "success": True,
            "deleted": deleted
        })
    except Exception as e:
        print(f"Error deleting metadata preview: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：列出所有本地LoRA文件（调试用）
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/list-all')
async def list_all_loras(request):
    """列出本地所有LoRA文件，用于调试"""
    try:
        lora_paths = folder_paths.get_filename_list("loras")
        return web.json_response({"loras": lora_paths, "count": len(lora_paths)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：批量检查 LoRA 本地存在性（支持SHA256或文件名匹配）
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/check-local')
async def check_lora_local_existence(request):
    """
    批量检查 LoRA 文件是否在本地存在，同时返回预览图路径
    支持两种模式：
    1. 如果有hash字段，用SHA256匹配
    2. 如果没有hash字段，用文件名匹配
    
    POST body: { "lora_list": [{"name": "xxx.safetensors", "hash": "ac9a447b46", ...}, ...] }
    Returns: { "results": { "lora_name_or_hash": { "exists": true/false, "has_preview": true/false, "local_path": "...", "local_name": "..." }, ... } }
    """
    try:
        data = await request.json()
        lora_list = data.get('lora_list', [])
        
        if not lora_list:
            return web.json_response({"results": {}})
        
        print(f"[Naiba-Debug] check-local: 收到 {len(lora_list)} 个LoRA条目")
        
        results = {}
        
        def check_preview_exists(lora_path):
            """检查LoRA文件是否有预览图"""
            try:
                lora_dir = os.path.dirname(lora_path)
                lora_basename = os.path.splitext(os.path.basename(lora_path))[0]
                preview_extensions = ['.png', '.jpg', '.jpeg', '.webp', '.preview.png', '.preview.jpg', '.custom.preview.png', '.custom.preview.jpg']
                for ext in preview_extensions:
                    for pattern in [lora_basename + ext, lora_basename + '.preview' + os.path.splitext(ext)[0], lora_basename + '.custom.preview' + os.path.splitext(ext)[0]]:
                        if os.path.exists(os.path.join(lora_dir, pattern)):
                            return True
                # 检查视频/GIF封面缓存
                cached_cover = os.path.join(lora_dir, lora_basename + ".naiba.preview.png")
                if os.path.exists(cached_cover):
                    return True
            except:
                pass
            return False
        
        # 分离有hash和没有hash的LoRA
        loras_with_hash = []
        loras_without_hash = []
        for item in lora_list:
            h = item.get("hash", "") or item.get("sha256", "")
            if h:
                loras_with_hash.append(item)
            else:
                loras_without_hash.append(item)
        
        print(f"[Naiba-Debug] check-local: {len(loras_with_hash)} 个有sha256，{len(loras_without_hash)} 个无sha256")
        
        # 处理没有hash的LoRA - 直接标记为无法匹配
        for item in loras_without_hash:
            name = item.get("name", "")
            if name:
                results[name] = {
                    "exists": False,
                    "has_preview": False,
                    "no_hash": True,
                    "original_name": name
                }
        
        # SHA256 匹配模式（处理有sha256的LoRA）
        if loras_with_hash:
            sha256_to_lora = {}
            for item in loras_with_hash:
                h = item.get("sha256", "").lower()
                if h:
                    sha256_to_lora[h] = item
            
            print(f"[Naiba-Debug] check-local: 需要匹配 {len(sha256_to_lora)} 个sha256值")
            
            lora_files = folder_paths.get_filename_list("loras")
            print(f"[Naiba-Debug] check-local: 本地有 {len(lora_files)} 个LoRA文件")
            
            matched_hashes = set()
            
            for lora_file in lora_files:
                if len(matched_hashes) >= len(sha256_to_lora):
                    break
                    
                try:
                    lora_path = folder_paths.get_full_path("loras", lora_file)
                    if not lora_path or not os.path.exists(lora_path):
                        continue
                    
                    # 计算SHA256
                    sha256 = hashlib.sha256()
                    with open(lora_path, 'rb') as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            sha256.update(chunk)
                    file_hash = sha256.hexdigest()
                    
                    if file_hash in sha256_to_lora and file_hash not in matched_hashes:
                        matched_hashes.add(file_hash)
                        original_item = sha256_to_lora[file_hash]
                        
                        has_preview = check_preview_exists(lora_path)
                        
                        results[file_hash] = {
                            "exists": True,
                            "has_preview": has_preview,
                            "local_path": lora_path,
                            "local_name": lora_file,
                            "original_name": original_item.get("name", "")
                        }
                        
                        if len(matched_hashes) <= 5:
                            print(f"[Naiba-Debug] check-local: 匹配成功 sha256={file_hash[:12]}... -> {lora_file}")
                        
                except Exception as e:
                    print(f"[Naiba-Debug] check-local: 处理 {lora_file} 时出错: {e}")
                    continue
            
            # 对于没有匹配到的sha256，标记为不存在
            for h, item in sha256_to_lora.items():
                if h not in matched_hashes:
                    results[h] = {
                        "exists": False,
                        "has_preview": False,
                        "original_name": item.get("name", "")
                    }
                
                if list(name_to_lora.keys()).index(lora_name) < 3:
                    print(f"[Naiba-Debug] check-local: {lora_name} -> exists={exists}")
        
        # 调试：打印统计
        found_count = sum(1 for v in results.values() if v.get("exists"))
        print(f"[Naiba-Debug] check-local: 完成，{found_count}/{len(results)} 存在本地")
        
        return web.json_response({"results": results})
        
    except Exception as e:
        print(f"Error checking lora local existence: {e}")
        return web.json_response({"error": str(e)}, status=500)


print("✅ Naiba Routes loaded: /naiba/presets/*, /naiba/presets/resolve, /naiba/presets/upload-image, /naiba/presets/image, /naiba/lora/preview, /naiba/lora/metadata/preview, /naiba/lora/civitai-sync, /naiba/lora/batch-sync, /naiba/lora/metadata, /naiba/cache/*, /naiba/lora/favorites/*, /naiba/lora/detail, /naiba/lora/custom-data/*, /naiba/lora/civitai-by-hash, /naiba/lora/civitai-search, /naiba/lora/resolve-sha256, /naiba/lora/check-local, /naiba/lora/list-all")


# ============================================================
# 自定义数据管理
# ============================================================

def get_custom_data_path(lora_path: str) -> str:
    """
    获取自定义数据文件路径
    
    Args:
        lora_path: LoRA文件路径
        
    Returns:
        str: 自定义数据文件路径
    """
    return os.path.splitext(lora_path)[0] + ".custom.info.json"


def load_custom_data(lora_path: str) -> Optional[Dict]:
    """
    加载自定义数据
    
    Args:
        lora_path: LoRA文件路径
        
    Returns:
        Optional[Dict]: 自定义数据，不存在返回None
    """
    custom_data_path = get_custom_data_path(lora_path)
    try:
        if os.path.exists(custom_data_path):
            with open(custom_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        print(f"[Naiba] Error loading custom data: {e}")
    return None


def save_custom_data(lora_path: str, data: Dict) -> bool:
    """
    保存自定义数据
    
    Args:
        lora_path: LoRA文件路径
        data: 自定义数据字典
        
    Returns:
        bool: 是否成功
    """
    custom_data_path = get_custom_data_path(lora_path)
    try:
        os.makedirs(os.path.dirname(custom_data_path), exist_ok=True)
        with open(custom_data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Naiba] Error saving custom data: {e}")
        return False


def get_custom_image_path(lora_path: str, extension: str = ".webp") -> str:
    """
    获取自定义预览图路径
    
    Args:
        lora_path: LoRA文件路径
        extension: 图片扩展名
        
    Returns:
        str: 自定义预览图路径
    """
    lora_dir = os.path.dirname(lora_path)
    lora_basename = os.path.splitext(os.path.basename(lora_path))[0]
    return os.path.join(lora_dir, f"{lora_basename}.custom.preview{extension}")


def find_metadata_preview(lora_path: str) -> Optional[str]:
    """
    查找 Civitai 同步的元数据预览图（即 {lora}.preview.*，不含用户自定义封面）

    采用目录扫描而非固定扩展名列表，可兼容 Civitai 同步可能产生的任意扩展名
    （如 .preview.bmp / .preview.tiff 等），避免漏匹配。

    Args:
        lora_path: LoRA文件路径

    Returns:
        Optional[str]: 元数据预览图路径，不存在返回None
    """
    lora_dir = os.path.dirname(lora_path)
    lora_basename = os.path.splitext(os.path.basename(lora_path))[0]

    # 仅匹配 Civitai 同步产生的 .preview.* 文件（排除 .custom.preview.*）
    meta_prefix = lora_basename + ".preview."
    custom_prefix = lora_basename + ".custom.preview."
    try:
        for f in os.listdir(lora_dir):
            if not f.startswith(meta_prefix) or f.startswith(custom_prefix):
                continue
            candidate = os.path.join(lora_dir, f)
            if os.path.isfile(candidate):
                return candidate
    except OSError:
        return None
    return None


def delete_metadata_preview(lora_path: str) -> bool:
    """
    删除 Civitai 同步的元数据预览图（{lora}.preview.*）

    注意：仅删除 Civitai 元数据封面，不会影响用户自定义封面 (.custom.preview.*)
    或同名直接图片 (lora.png)。采用目录扫描以兼容任意扩展名。

    Returns:
        bool: 是否实际删除了文件
    """
    lora_dir = os.path.dirname(lora_path)
    lora_basename = os.path.splitext(os.path.basename(lora_path))[0]

    meta_prefix = lora_basename + ".preview."
    custom_prefix = lora_basename + ".custom.preview."
    deleted = False
    try:
        for f in os.listdir(lora_dir):
            if not f.startswith(meta_prefix) or f.startswith(custom_prefix):
                continue
            candidate = os.path.join(lora_dir, f)
            if not os.path.isfile(candidate):
                continue
            try:
                os.remove(candidate)
                deleted = True
                print(f"[Naiba] Deleted metadata preview image: {candidate}")
            except Exception as e:
                print(f"[Naiba] Warning: Failed to delete {candidate}: {e}")
    except OSError as e:
        print(f"[Naiba] Warning: Could not list directory {lora_dir}: {e}")
    return deleted


def validate_lora_name(lora_name: str) -> Tuple[bool, str, Optional[str]]:
    """
    验证LoRA名称并返回完整路径
    
    Args:
        lora_name: LoRA文件名（可能包含子目录）
        
    Returns:
        Tuple[bool, str, Optional[str]]: (是否有效, 错误信息, LoRA文件路径)
    """
    if not lora_name:
        return False, "Missing lora name", None
    
    # 安全检查：防止路径遍历攻击
    if '..' in lora_name or os.path.isabs(lora_name):
        return False, "Invalid lora name for security reasons", None
    
    # 获取LoRA文件路径
    lora_path = folder_paths.get_full_path("loras", lora_name)
    if not lora_path or not os.path.exists(lora_path):
        return False, "LoRA file not found", None
    
    # 验证路径安全性：确保路径在LoRA目录内
    lora_dirs = folder_paths.get_folder_paths("loras")
    real_lora_path = os.path.realpath(lora_path)
    is_safe = False
    for lora_dir_root in lora_dirs:
        real_root = os.path.realpath(lora_dir_root)
        if real_lora_path.startswith(real_root + os.sep) or real_lora_path == real_root:
            is_safe = True
            break
    
    if not is_safe:
        print(f"SECURITY ALERT: Blocked attempt to access file outside LoRA directory: {lora_name}")
        return False, "Access denied", None
    
    return True, "", lora_path


# ============================================================
# API 路由：获取 LoRA 详情（合并 Civitai 元数据 + 自定义数据）
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/detail')
async def get_lora_detail_handler(request):
    """
    获取 LoRA 详情（合并 Civitai 元数据 + 自定义数据）
    
    参数:
        name: LoRA文件名（必需）
    """
    lora_name = request.query.get('name', '')
    
    # 验证LoRA名称
    is_valid, error_msg, lora_path = validate_lora_name(lora_name)
    if not is_valid:
        return web.json_response({"error": error_msg}, status=400 if "Missing" in error_msg else 404 if "not found" in error_msg else 403)
    
    try:
        # 导入Civitai工具类
        from .civitai_utils import (
            get_metadata_path,
            load_cached_metadata,
            find_local_preview,
        )
        
        # 获取Civitai元数据
        metadata_path = get_metadata_path(lora_path)
        metadata = load_cached_metadata(metadata_path)
        
        # 查找本地预览图
        local_preview = find_local_preview(lora_path)

        # 查找 Civitai 元数据预览图（不含自定义封面）
        metadata_preview = find_metadata_preview(lora_path)

        # 获取自定义数据
        custom_data = load_custom_data(lora_path)
        
        return web.json_response({
            "success": True,
            "metadata": metadata,
            "local_preview": local_preview,
            "metadata_preview": metadata_preview,
            "custom_data": custom_data,
            "has_cached_metadata": metadata is not None,
            "has_local_preview": local_preview is not None,
            "has_metadata_preview": metadata_preview is not None,
            "has_custom_data": custom_data is not None
        })
        
    except Exception as e:
        print(f"Error getting lora detail: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：保存自定义数据
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/custom-data/save')
async def save_custom_data_handler(request):
    """
    保存自定义数据
    
    请求体:
        name: LoRA文件名（必需）
        custom_data: 自定义数据对象（必需）
    """
    try:
        body = await request.json()
        lora_name = body.get('name', '').strip()
        custom_data = body.get('custom_data', {})
        
        # 验证LoRA名称
        is_valid, error_msg, lora_path = validate_lora_name(lora_name)
        if not is_valid:
            return web.json_response({"error": error_msg}, status=400 if "Missing" in error_msg else 404 if "not found" in error_msg else 403)
        
        # 验证数据格式
        if not isinstance(custom_data, dict):
            return web.json_response({"error": "custom_data must be a JSON object"}, status=400)
        
        # 添加更新时间
        from datetime import datetime
        custom_data['updated_at'] = datetime.now().isoformat()

        # 如果 custom_preview_image_path 被清空，删除磁盘上对应的 .custom.preview.* 文件
        new_image_path = custom_data.get('custom_preview_image_path', None)
        if new_image_path is not None and (not new_image_path or new_image_path.strip() == ""):
            # 读取旧数据，获取旧的图片路径
            old_custom_data = load_custom_data(lora_path)
            if old_custom_data:
                old_image_path = old_custom_data.get('custom_preview_image_path', '')
                if old_image_path and os.path.exists(old_image_path):
                    try:
                        os.remove(old_image_path)
                        print(f"[Naiba] Deleted old custom preview image: {old_image_path}")
                    except Exception as e:
                        print(f"[Naiba] Warning: Failed to delete old custom preview image: {e}")

            # 同时尝试删除所有可能的 .custom.preview.* 文件（以防路径不匹配）
            lora_dir = os.path.dirname(lora_path)
            lora_basename = os.path.splitext(os.path.basename(lora_path))[0]
            custom_preview_extensions = [".custom.preview.webp", ".custom.preview.png",
                                         ".custom.preview.jpg", ".custom.preview.jpeg",
                                         ".custom.preview.gif"]
            for ext in custom_preview_extensions:
                candidate = os.path.join(lora_dir, lora_basename + ext)
                if os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                        print(f"[Naiba] Deleted custom preview file: {candidate}")
                    except Exception as e:
                        print(f"[Naiba] Warning: Failed to delete {candidate}: {e}")

        # 保存自定义数据
        if save_custom_data(lora_path, custom_data):
            # 清除该LoRA的图片缓存，确保前端能加载最新预览图
            cache_key = f"lora_preview:{lora_name}"
            image_cache.delete(cache_key)
            
            return web.json_response({
                "success": True,
                "custom_data": custom_data
            })
        else:
            return web.json_response({"error": "Failed to save custom data"}, status=500)
            
    except Exception as e:
        print(f"Error saving custom data: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：上传自定义预览图
# ============================================================
@PromptServer.instance.routes.post('/naiba/lora/custom-data/upload-image')
async def upload_custom_image_handler(request):
    """
    上传自定义预览图
    
    表单数据:
        file: 图片文件
        name: LoRA文件名
    """
    try:
        reader = await request.multipart()
        
        lora_name = None
        image_data = None
        image_filename = None
        
        # 解析 multipart 数据
        while True:
            part = await reader.next()
            if part is None:
                break
            
            if part.name == 'name':
                lora_name = (await part.read()).decode('utf-8').strip()
            elif part.name == 'file':
                image_data = await part.read()
                image_filename = part.filename
        
        if not lora_name:
            return web.json_response({"error": "LoRA name is required"}, status=400)
        
        if not image_data:
            return web.json_response({"error": "No image file provided"}, status=400)
        
        # 验证LoRA名称
        is_valid, error_msg, lora_path = validate_lora_name(lora_name)
        if not is_valid:
            return web.json_response({"error": error_msg}, status=400 if "Missing" in error_msg else 404 if "not found" in error_msg else 403)
        
        # 确定图片扩展名
        ext = os.path.splitext(image_filename)[1].lower() if image_filename else '.webp'
        if ext not in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
            ext = '.webp'
        
        # 生成自定义预览图路径
        custom_image_path = get_custom_image_path(lora_path, ext)
        
        # 保存图片
        with open(custom_image_path, 'wb') as f:
            f.write(image_data)
        
        # 更新自定义数据中的图片路径
        custom_data = load_custom_data(lora_path) or {}
        custom_data['custom_preview_image_path'] = custom_image_path
        custom_data['updated_at'] = __import__('datetime').datetime.now().isoformat()
        save_custom_data(lora_path, custom_data)
        
        # 清除该LoRA的图片缓存，确保前端能加载新图片
        cache_key = f"lora_preview:{lora_name}"
        image_cache.delete(cache_key)
        
        return web.json_response({
            "success": True,
            "image_path": custom_image_path
        })
        
    except Exception as e:
        print(f"Error uploading custom image: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：获取自定义预览图
# ============================================================
@PromptServer.instance.routes.get('/naiba/lora/custom-data/image')
async def get_custom_image_handler(request):
    """
    获取自定义预览图
    
    参数:
        name: LoRA文件名
    """
    lora_name = request.query.get('name', '').strip()
    
    # 验证LoRA名称
    is_valid, error_msg, lora_path = validate_lora_name(lora_name)
    if not is_valid:
        return web.Response(status=400 if "Missing" in error_msg else 404 if "not found" in error_msg else 403, text=error_msg)
    
    try:
        # 加载自定义数据
        custom_data = load_custom_data(lora_path)
        if not custom_data:
            return web.Response(status=404, text="No custom data found")
        
        # 获取自定义图片路径
        custom_image_path = custom_data.get('custom_preview_image_path', '')
        if not custom_image_path or not os.path.exists(custom_image_path):
            return web.Response(status=404, text="No custom preview image")
        
        # 读取图片
        with open(custom_image_path, 'rb') as f:
            image_data = f.read()

        # 依据真实文件内容（魔数）检测 MIME，避免扩展名与真实格式不符导致裂图
        content_type = detect_image_mime(image_data, os.path.splitext(custom_image_path)[1])
        
        return web.Response(
            body=image_data,
            content_type=content_type,
            headers={'Cache-Control': 'max-age=3600'}
        )
        
    except Exception as e:
        print(f"Error getting custom image: {e}")
        return web.Response(status=500, text=str(e))


# ============================================================
# API 路由：删除自定义数据（整个 .custom.info.json 及自定义封面）
# ============================================================
@PromptServer.instance.routes.delete('/naiba/lora/custom-data')
async def delete_custom_data_handler(request):
    """
    删除某个 LoRA 的全部自定义数据

    删除内容：
        - {lora}.custom.info.json（自定义提示词/下载链接/NSFW/介绍等）
        - {lora}.custom.preview.*（用户自定义封面图，若存在）
    不会影响 Civitai 同步的元数据（.info.json）或元数据封面（.preview.*）。

    参数:
        name: LoRA文件名（必需）
    """
    lora_name = request.query.get('name', '').strip()

    # 验证LoRA名称并返回完整路径
    is_valid, error_msg, lora_path = validate_lora_name(lora_name)
    if not is_valid:
        status = 400 if "Missing" in error_msg else 404 if "not found" in error_msg else 403
        return web.json_response({"error": error_msg}, status=status)

    try:
        deleted_files = []

        # 1. 删除自定义数据 JSON
        custom_data_path = get_custom_data_path(lora_path)
        if os.path.exists(custom_data_path):
            try:
                os.remove(custom_data_path)
                deleted_files.append(os.path.basename(custom_data_path))
            except Exception as e:
                print(f"[Naiba] Warning: Failed to delete custom data json: {e}")

        # 2. 删除所有可能的自定义封面 .custom.preview.*
        lora_dir = os.path.dirname(lora_path)
        lora_basename = os.path.splitext(os.path.basename(lora_path))[0]
        custom_preview_prefix = lora_basename + ".custom.preview."
        try:
            for f in os.listdir(lora_dir):
                if f.startswith(custom_preview_prefix):
                    candidate = os.path.join(lora_dir, f)
                    if os.path.isfile(candidate):
                        try:
                            os.remove(candidate)
                            deleted_files.append(f)
                        except Exception as e:
                            print(f"[Naiba] Warning: Failed to delete {candidate}: {e}")
        except OSError as e:
            print(f"[Naiba] Warning: Could not list directory {lora_dir}: {e}")

        # 清除该LoRA的图片缓存，确保前端能加载最新预览图（回退到元数据封面/无图）
        cache_key = f"lora_preview:{lora_name}"
        image_cache.delete(cache_key)

        return web.json_response({
            "success": True,
            "deleted": len(deleted_files) > 0,
            "deleted_files": deleted_files
        })

    except Exception as e:
        print(f"Error deleting custom data: {e}")
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.get('/naiba/lora/civitai-by-hash')
async def civitai_by_hash_handler(request):
    """按sha256查询Civitai模型"""
    client = None
    try:
        file_hash = request.query.get("hash", "").strip()
        if not file_hash:
            return web.json_response({"error": "hash参数不能为空"}, status=400)
        
        # 安全检查：只允许十六进制字符
        if not all(c in '0123456789abcdefABCDEF' for c in file_hash):
            return web.json_response({"error": "hash格式无效，只允许十六进制字符"}, status=400)
        
        from .civitai_utils import CivitaiClient, build_civitai_version_info
        client = CivitaiClient()
        data, error = await client.query_by_hash(file_hash)
        
        if error:
            if "Model not found" in str(error):
                return web.json_response({
                    "found": False,
                    "hash": file_hash,
                    "error": "Model not found"
                })
            return web.json_response({
                "found": False,
                "hash": file_hash,
                "error": error
            })
        
        # 提取关键信息
        info = build_civitai_version_info(data)
        
        return web.json_response({
            "found": True,
            "hash": file_hash,
            "info": info
        })
        
    except Exception as e:
        print(f"Error in civitai_by_hash: {e}")
        return web.json_response({"error": str(e)}, status=500)
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


@PromptServer.instance.routes.get('/naiba/lora/civitai-search')
async def civitai_search_handler(request):
    """搜索Civitai模型"""
    client = None
    try:
        query = request.query.get("query", "").strip()
        page = int(request.query.get("page", "1"))
        limit = int(request.query.get("limit", "20"))
        model_type = request.query.get("types", "").strip() or None
        
        if not query:
            return web.json_response({"error": "query参数不能为空"}, status=400)
        
        # 限制参数范围
        page = max(1, page)
        limit = max(1, min(100, limit))
        
        from .civitai_utils import CivitaiClient, build_civitai_version_info
        client = CivitaiClient()
        data, error = await client.search_models(query, page, limit, model_type)
        
        if error:
            return web.json_response({"error": error}, status=500)
        
        # 处理搜索结果
        items = []
        if data and "items" in data:
            for item in data["items"]:
                model_info = {
                    "model_id": item.get("id"),
                    "model_name": item.get("name", "Unknown"),
                    "model_type": item.get("type", "Unknown"),
                    "nsfw_level": item.get("nsfwLevel", 0),
                    "stats": item.get("stats", {}),
                    "creator": item.get("creator", {}),
                    "tags": item.get("tags", []),
                    "versions": []
                }
                
                # 处理每个版本
                for version in item.get("modelVersions", []):
                    version_info = build_civitai_version_info(version)
                    model_info["versions"].append(version_info)
                
                items.append(model_info)
        
        return web.json_response({
            "items": items,
            "metadata": data.get("metadata", {}) if data else {}
        })
        
    except Exception as e:
        print(f"Error in civitai_search: {e}")
        return web.json_response({"error": str(e)}, status=500)
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


@PromptServer.instance.routes.get('/naiba/lora/resolve-sha256')
async def resolve_sha256_handler(request):
    """解析lora的sha256，支持自动回退"""
    try:
        lora_name = request.query.get("name", "").strip()
        if not lora_name:
            return web.json_response({"error": "name参数不能为空", "sha256": None, "source": "none"}, status=400)
        
        # 安全检查：防止路径遍历
        if ".." in lora_name or os.path.isabs(lora_name):
            return web.json_response({"error": "无效的lora名称"}, status=400)
        
        sha256 = None
        source = "none"
        
        # 1. 尝试从.civitai.info.json缓存读取
        try:
            from .civitai_utils import get_metadata_path
            import folder_paths
            
            # 获取lora文件夹路径
            lora_folders = folder_paths.get_folder_paths("loras")
            for lora_dir in lora_folders:
                lora_path = os.path.join(lora_dir, lora_name)
                if not os.path.splitext(lora_path)[1]:
                    # 尝试常见扩展名
                    for ext in [".safetensors", ".pt", ".ckpt"]:
                        if os.path.isfile(lora_path + ext):
                            lora_path = lora_path + ext
                            break
                
                if os.path.isfile(lora_path):
                    metadata_path = get_metadata_path(lora_path)
                    if os.path.isfile(metadata_path):
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                        if metadata.get("hash"):
                            sha256 = metadata["hash"]
                            source = "cache"
                            break
        except Exception as e:
            print(f"[Naiba] Warning: Failed to read cache for {lora_name}: {e}")
        
        # 2. 如果缓存没有，尝试计算本地文件
        if not sha256:
            try:
                from .civitai_utils import CivitaiClient
                import folder_paths
                
                lora_folders = folder_paths.get_folder_paths("loras")
                for lora_dir in lora_folders:
                    lora_path = os.path.join(lora_dir, lora_name)
                    if not os.path.splitext(lora_path)[1]:
                        for ext in [".safetensors", ".pt", ".ckpt"]:
                            if os.path.isfile(lora_path + ext):
                                lora_path = lora_path + ext
                                break
                    
                    if os.path.isfile(lora_path):
                        sha256 = await CivitaiClient.calculate_sha256(lora_path)
                        if sha256:
                            source = "calculated"
                        break
            except Exception as e:
                print(f"[Naiba] Warning: Failed to calculate sha256 for {lora_name}: {e}")
        
        return web.json_response({
            "sha256": sha256,
            "source": source
        })
        
    except Exception as e:
        print(f"Error in resolve_sha256: {e}")
        return web.json_response({"error": str(e)}, status=500)
