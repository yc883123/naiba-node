"""
Multi LoRA Loader 预设管理 API 路由
提供预设的增删改查功能，支持服务端预设存储
"""

import os
import json
import glob
import time
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

# 预设存储目录
PRESETS_DIR = os.path.join(os.path.dirname(__file__), "presets")
PRESETS_EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), "presets.example")
os.makedirs(PRESETS_DIR, exist_ok=True)

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
        
        file_path = os.path.join(PRESETS_DIR, f"{name}.json")
        
        # 保存预设
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return web.json_response({"success": True})
    except Exception as e:
        print(f"Error saving preset: {e}")
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
        return web.json_response({"success": True})
    except Exception as e:
        print(f"Error renaming preset: {e}")
        return web.json_response({"error": str(e)}, status=500)


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
        
        # MIME 类型映射
        mime_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
            '.gif': 'image/gif',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.svg': 'image/svg+xml',
            '.avif': 'image/avif',
            '.heic': 'image/heic',
            '.heif': 'image/heif',
            '.ico': 'image/x-icon',
            '.apng': 'image/apng',
        }
        
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
        
        # 查找同名的图片文件
        for ext in image_extensions:
            preview_path = os.path.join(lora_dir, lora_basename + ext)
            if os.path.exists(preview_path):
                # 读取并返回图片
                with open(preview_path, 'rb') as f:
                    image_data = f.read()
                
                # 根据扩展名设置 Content-Type
                content_type = mime_type_map.get(ext, 'image/png')
                
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
        
        # 也查找 .preview 后缀的文件
        for ext in image_extensions:
            preview_path = os.path.join(lora_dir, lora_basename + '.preview' + ext)
            if os.path.exists(preview_path):
                with open(preview_path, 'rb') as f:
                    image_data = f.read()
                
                content_type = mime_type_map.get(ext, 'image/png')
                
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
        
        # 根据扩展名设置 Content-Type
        ext = os.path.splitext(custom_image_path)[1].lower()
        mime_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
        }
        content_type = mime_type_map.get(ext, 'image/webp')
        
        return web.Response(
            body=image_data,
            content_type=content_type,
            headers={'Cache-Control': 'max-age=3600'}
        )
        
    except Exception as e:
        print(f"Error getting favorite image: {e}")
        return web.Response(status=500, text=str(e))


print("✅ Naiba Routes loaded: /naiba/presets/*, /naiba/lora/preview, /naiba/lora/civitai-sync, /naiba/lora/batch-sync, /naiba/lora/metadata, /naiba/cache/*, /naiba/lora/favorites/*, /naiba/lora/detail, /naiba/lora/custom-data/*")


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
        
        # 获取自定义数据
        custom_data = load_custom_data(lora_path)
        
        return web.json_response({
            "success": True,
            "metadata": metadata,
            "local_preview": local_preview,
            "custom_data": custom_data,
            "has_cached_metadata": metadata is not None,
            "has_local_preview": local_preview is not None,
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
        
        # 保存自定义数据
        if save_custom_data(lora_path, custom_data):
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
        
        # 根据扩展名设置 Content-Type
        ext = os.path.splitext(custom_image_path)[1].lower()
        mime_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
        }
        content_type = mime_type_map.get(ext, 'image/webp')
        
        return web.Response(
            body=image_data,
            content_type=content_type,
            headers={'Cache-Control': 'max-age=3600'}
        )
        
    except Exception as e:
        print(f"Error getting custom image: {e}")
        return web.Response(status=500, text=str(e))
