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


# ============================================================
# SHA256 计算（保存预设时自动写入，导入时用于匹配改名文件）
# ============================================================
# name -> sha256 hex 缓存，避免重复扫描本地 LoRA（I/O 密集）
_SHA256_CACHE = {}


def compute_lora_sha256(lora_name):
    """计算指定 LoRA 文件的 SHA256（分块读取），失败返回 None"""
    try:
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            return None
        h = hashlib.sha256()
        with open(lora_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        print(f"[Naiba] SHA256 计算失败 {lora_name}: {e}")
        return None


async def compute_lora_sha256_async(lora_name):
    """非阻塞计算 SHA256（worker 线程执行，避免阻塞事件循环）"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, compute_lora_sha256, lora_name)


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
        name = body.get('name', '').strip()
        data = body.get('data', [])
        
        # 验证名称
        is_valid, error_msg = validate_preset_name(name)
        if not is_valid:
            return web.json_response({"error": error_msg}, status=400)
        
        # 验证数据格式
        if not isinstance(data, list):
            return web.json_response({"error": "数据格式错误，需要是数组"}, status=400)
        
        # 为每个 LoRA 条目计算并写入 SHA256（非阻塞，避免卡住事件循环）
        for entry in data:
            if isinstance(entry, dict) and entry.get("name"):
                try:
                    sha = await compute_lora_sha256_async(entry["name"])
                    if sha:
                        entry["sha256"] = sha
                except Exception:
                    pass
        
        file_path = os.path.join(PRESETS_DIR, f"{name}.json")
        
        # 保存预设
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return web.json_response({"success": True})
    except Exception as e:
        print(f"Error saving preset: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# API 路由：解析/校验预设（导入时按 sha256 定位改名文件，非破坏性）
# ============================================================
async def _sha256_of_path_async(path):
    """非阻塞计算指定文件路径的 SHA256（worker 线程执行）"""
    loop = asyncio.get_event_loop()

    def _hash():
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    try:
        return await loop.run_in_executor(None, _hash)
    except Exception:
        return None


@PromptServer.instance.routes.post('/naiba/presets/resolve')
async def resolve_preset_handler(request):
    """导入预设时按 sha256 定位改名文件。

    非破坏性：绝不丢弃任何条目。
    - 含 sha256 且本地存在同哈希文件 -> 将 name 改为本地真实相对路径（支持改名匹配）
    - 含 sha256 但本地无匹配 / 不含 sha256 -> 保留原始 name（缺失项由前端以 (missing) 显示）
    旧预设（保存时尚未写入 sha256）不含 sha256，会原样返回，可正常导入。
    """
    try:
        body = await request.json()
        data = body.get('data', [])
        if not isinstance(data, list):
            return web.json_response({"error": "数据格式错误，需要是数组"}, status=400)

        # 仅当存在带 sha256 的条目时才扫描本地 LoRA（I/O 密集），否则直接原样返回
        has_sha = any(isinstance(e, dict) and e.get("sha256") for e in data)
        local_sha_map = {}
        if has_sha:
            lora_dirs = folder_paths.get_folder_paths("loras")
            for lora_dir in lora_dirs:
                if not os.path.isdir(lora_dir):
                    continue
                for root, _dirs, files in os.walk(lora_dir):
                    for f in files:
                        if not f.lower().endswith(('.safetensors', '.pt', '.ckpt', '.pth')):
                            continue
                        p = os.path.join(root, f)
                        key = os.path.realpath(p)
                        if key in _SHA256_CACHE:
                            sha = _SHA256_CACHE[key]
                        else:
                            sha = await _sha256_of_path_async(p)
                            if sha:
                                _SHA256_CACHE[key] = sha
                        if sha:
                            local_sha_map.setdefault(sha, p)

        resolved = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            new_entry = dict(entry)
            sha = new_entry.get("sha256")
            if sha and sha in local_sha_map:
                # 改名为本地真实相对路径（相对首个 lora 目录）
                rel = os.path.relpath(local_sha_map[sha], lora_dirs[0]) if lora_dirs else local_sha_map[sha]
                new_entry["name"] = rel
            # 无 sha256 或本地无匹配：保留原始 name（缺失项由前端以 (missing) 显示）
            resolved.append(new_entry)

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
        image_extensions = [
            '.png', '.jpg', '.jpeg', '.webp', '.bmp',  # 常见格式
            '.gif', '.tiff', '.tif', '.svg',  # 额外格式
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
        )
        
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


print("✅ Naiba Routes loaded: /naiba/presets/*, /naiba/presets/resolve, /naiba/presets/upload-image, /naiba/presets/image, /naiba/lora/preview, /naiba/lora/metadata/preview, /naiba/lora/civitai-sync, /naiba/lora/batch-sync, /naiba/lora/metadata, /naiba/cache/*, /naiba/lora/favorites/*, /naiba/lora/detail, /naiba/lora/custom-data/*")


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
