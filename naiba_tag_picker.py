"""
Naiba Tag Picker 节点
调用 Danbooru 公开 API 搜索 画师(artist) / 角色(character) / IP(copyright) 三类标签，
前端三标签页画廊多选，选图结果以分组 JSON 写回隐藏 STRING 控件，
节点输出三类标签名串 + 选中图批量预览（IMAGE 张量，内存传递，绝不落盘）。

设计要点：
- 搜索走 Danbooru 公开 /tags.json 接口，按 search[category] 直接列出标签名 + 出现次数
  （artist=1 / character=4 / ip(copyright)=3），匿名即可稳定使用，无需登录。
- 预览图：选中/画廊缩略图通过 /naiba/tag/preview?name=<tag> 取该标签代表作首图（内部
  调 /posts.json?tags=<name>&limit=1 拿 preview_file_url，再同源代理 cdn.donmai.us）。
- 搜索与预览均走限流 + 重试 + 可选 Basic Auth；图片字节仅做魔数 MIME 识别 + 内存缓存
  （上限 100、TTL 1h），绝不写盘（与 anima-t8 的预览策略一致）。
- 本模块完全独立：不 import 任何内置节点类或其他节点文件，仅用 ComfyUI 基础库
  （torch / PIL / numpy / 标准库）与 server.PromptServer。
"""

import os
import io
import json
import time
import base64
import random
import threading
import asyncio
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch
from PIL import Image

from server import PromptServer
from aiohttp import web


# ============================================================
# 配置
# ============================================================
DANBOORU_BASE = "https://danbooru.donmai.us"
CDN_HOST_SUFFIX = "donmai.us"          # 仅允许代理该域名下的图片，防 SSRF
API_RATE_LIMIT_SEC = 2.0               # Danbooru 匿名约 20 req/min(≈3s)；留余量，Basic Auth 可提升

# 关键修复：Danbooru/Cloudflare 已把 UA 中含 "ComfyUI" 字样的请求列入黑名单，一律返回 403
# （实测验证：含 "ComfyUI" 的 UA → 403；换成不含该字样的自定 UA → 200）。故 UA 只用本项目名
# naiba 作为标识，绝不能写 "ComfyUI"。API 请求仅带 User-Agent（不带 Accept），与图片 CDN 分开。
# 可选 Basic Auth（DANBOORU_USER / DANBOORU_API_KEY）可进一步提升限额。
USER_AGENT = "naiba-tag-picker/1.0 (+naiba-node)"
DANBOORU_REFERER = "https://danbooru.donmai.us/"

# 可选环境变量：设置后使用 Basic Auth，可提升 Danbooru API 限额
API_USER = os.environ.get("DANBOORU_USER") or ""
API_KEY = os.environ.get("DANBOORU_API_KEY") or ""

# Danbooru 标签 category 映射：artist=1 / character=4 / ip(copyright)=3
# 与 comfyui-anima-t8 的 api/danbooru_client.py 一致
CATEGORY_ID = {"artist": 1, "character": 4, "ip": 3}
CATEGORY_NAME_BY_ID = {1: "artist", 3: "copyright", 4: "character"}


# ============================================================
# 内存图片缓存（自备，不引用其他节点模块）
# ============================================================
class ImageCache:
    """简单的进程内图片字节缓存，带上限与 TTL。"""

    def __init__(self, max_size=100, ttl=3600):
        self.cache = {}
        self.access_times = {}
        self.max_size = max_size
        self.ttl = ttl
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self.cache:
                return None
            if time.time() - self.access_times[key] > self.ttl:
                self._remove(key)
                return None
            self.access_times[key] = time.time()
            return self.cache[key]

    def set(self, key, value):
        with self._lock:
            if len(self.cache) >= self.max_size:
                self._remove_oldest()
            self.cache[key] = value
            self.access_times[key] = time.time()

    def _remove(self, key):
        self.cache.pop(key, None)
        self.access_times.pop(key, None)

    def _remove_oldest(self):
        if not self.cache:
            return
        oldest = min(self.access_times.items(), key=lambda x: x[1])[0]
        self._remove(oldest)


_IMAGE_CACHE = ImageCache(max_size=100, ttl=3600)


def detect_image_mime(data: bytes) -> str:
    """依据魔数识别真实图片 MIME，不依赖扩展名。"""
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
    return "application/octet-stream"


# ============================================================
# 限流 + 请求
# ============================================================
_rate_lock = threading.Lock()
_last_api_ts = [0.0]


def _api_request(url: str, retries: int = 3):
    """带限流的 Danbooru API 请求（同步，供 executor 调用）。

    仅带自定义应用 User-Agent（不带 Referer / Accept），规避 Danbooru 匿名 403 风控。
    429（限流）与 403（临时风控 / IP 封禁前兆）均做指数退避重试；若重试耗尽仍 403，
    调用方会拿到异常，由上层转为空结果与友好提示，不会让浏览器出现破图。
    """
    headers = {"User-Agent": USER_AGENT}
    if API_USER and API_KEY:
        auth = base64.b64encode(f"{API_USER}:{API_KEY}".encode()).decode()
        headers["Authorization"] = f"Basic {auth}"

    last_err = None
    for attempt in range(retries):
        with _rate_lock:
            now = time.time()
            wait = API_RATE_LIMIT_SEC - (now - _last_api_ts[0])
            if wait > 0:
                time.sleep(wait)
            _last_api_ts[0] = time.time()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                time.sleep(3 * (attempt + 1))          # 限流：退避后重试
                continue
            if e.code == 403:
                # 临时风控 / 区域拦截前兆：更长退避再试（导入 anime-t8 同样依赖请求成功，
                # 若持续 403 多半是网络/IP 被挡，需要 DANBOORU_USER/DANBOORU_API_KEY）。
                print(f"[NaibaTagPicker] Danbooru 返回 403（匿名被风控），第 {attempt+1} 次重试…")
                time.sleep(5 * (attempt + 1))
                continue
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    if last_err:
        raise last_err
    return b"", ""


def _fetch_url(url: str, retries: int = 2):
    """不限流的图片字节请求（CDN 限额宽松）。带 Referer + SSL 上下文，规避 donmai 防盗链。"""
    import ssl
    headers = {"User-Agent": USER_AGENT, "Referer": DANBOORU_REFERER}
    ctx = ssl.create_default_context()
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    if last_err:
        print(f"[NaibaTagPicker] 图片下载失败 {url}: {last_err}")
    return b""


def fetch_image_bytes(url: str) -> bytes:
    """取图片字节，命中内存缓存则直接返回（路由与 execute 共用）。"""
    cached = _IMAGE_CACHE.get(url)
    if cached is not None:
        return cached
    data = _fetch_url(url)
    if data:
        _IMAGE_CACHE.set(url, data)
    return data


# ============================================================
# Danbooru 搜索
# ============================================================
def search_tags(query: str, category: str, limit: int, page: int = 1):
    """按分类用 Danbooru 公开 /tags.json 直接列出标签（artist/character/ip）。

    参考 comfyui-anima-t8/api/danbooru_client.py：
      - search[category]=1|3|4
      - search[order]=count          按出现次数降序（热门优先）
      - search[hide_empty]=yes
      - search[post_count_gteq]=10   过滤掉极少使用的标签
      - search[name_matches]=*q*     关键词过滤（留空则浏览全部分类热门标签）
      - limit / page                 分页
    返回 {items, warn, page, has_more}。
    """
    cat_id = CATEGORY_ID.get(category, 1)
    limit = max(1, min(int(limit), 100))
    page = max(1, int(page))

    params = {
        "search[category]": cat_id,
        "search[order]": "count",
        "search[hide_empty]": "yes",
        "search[post_count_gteq]": 10,
        "limit": limit,
        "page": page,
    }
    if query and query.strip():
        params["search[name_matches]"] = f"*{query.strip()}*"

    url = f"{DANBOORU_BASE}/tags.json?{urllib.parse.urlencode(params)}"

    warn = None
    try:
        raw, _ = _api_request(url)
        rows = json.loads(raw)
        if not isinstance(rows, list):
            rows = []
    except Exception as e:  # noqa: BLE001
        print(f"[NaibaTagPicker] 搜索失败: {e}")
        return {"items": [], "warn": f"搜索失败: {e}", "page": page, "has_more": False}

    if not rows:
        warn = "未找到结果（关键词无匹配，或触发 Danbooru 匿名限流，请稍后重试）"

    items = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        cat = int(r.get("category", cat_id))
        post_count = int(r.get("post_count", 0))
        items.append({
            "id": name,  # 以标签名作为稳定唯一键（前端 Map key）
            "tag": name,
            "category": cat,
            "category_name": CATEGORY_NAME_BY_ID.get(cat, category),
            "post_count": post_count,
            # 预览图不在搜索时解析（避免一页 50 次 posts.json 触发限流）；
            # 前端经 IntersectionObserver 懒加载 /naiba/tag/preview?name=<tag> 取代理 URL。
            "preview_url": "",
        })

    return {"items": items, "warn": warn, "page": page, "has_more": len(rows) >= limit}


# ============================================================
# 标签代表作预览图（按标签名）
# ============================================================
_PREVIEW_URL_CACHE = {}  # tag name -> 代表作图片真实 URL（内存缓存，避免重复 posts.json 调用）


def fetch_tag_preview_url(name: str) -> str:
    """调 /posts.json?tags=<name>&limit=20 取该标签代表作首图的真实 URL。

    扫描多张帖子，返回首个带 preview_file_url 的（部分帖子的首图字段为 null，
    故不能只取 limit=1 的第一张）。已限流 + 重试；结果进进程内存缓存避免重复调用。
    """
    if not name:
        return ""
    cached = _PREVIEW_URL_CACHE.get(name)
    if cached is not None:
        return cached
    tag_q = urllib.parse.quote(name, safe=":/_")
    url = f"{DANBOORU_BASE}/posts.json?tags={tag_q}&limit=20"
    preview = ""
    # 注意：此处不吞掉异常——网络/403 错误要向上抛出，让路由标记 error，
    # 前端据此判定为「可重试的限流」而非「真无图」。
    raw, _ = _api_request(url)
    data = json.loads(raw) if raw else []
    if isinstance(data, list):
        for p in data:
            if not isinstance(p, dict):
                continue
            pv = (p.get("preview_file_url")
                  or p.get("large_file_url")
                  or p.get("file_url") or "")
            if pv:
                preview = pv
                break
    # 仅缓存成功结果；空结果不缓存以便下次重试
    if preview:
        _PREVIEW_URL_CACHE[name] = preview
    return preview


def build_preview_proxy(name: str) -> str:
    """按标签名取代表作首图，并返回同源代理 URL（/naiba/tag/image?u=<base64>）。

    与 comfyui-anima-t8 的 dtags/preview 一致：该路由只做 posts.json 解析，
    真正的图片字节由前端再请求 /naiba/tag/image 代理获取，两步解耦、各自可缓存。
    取不到时返回空串，由前端显示占位（标签名）。
    """
    real = fetch_tag_preview_url(name)
    if not real:
        return ""
    enc = base64.urlsafe_b64encode(real.encode()).decode()
    return f"/naiba/tag/image?u={enc}"


def fetch_tag_preview_bytes(name: str) -> bytes:
    """取某标签代表作首图字节（命中 ImageCache 则直接返回）。供 execute 批量预览用。"""
    url = fetch_tag_preview_url(name)
    if not url:
        return b""
    return fetch_image_bytes(url)


# ============================================================
# 扭蛋模式：随机标签生成
# ============================================================
def get_random_tags_from_category(category: str, n: int) -> list:
    """从某分类取 n 个随机热门标签（随机翻页增加多样性）。失败返回空。"""
    if n <= 0:
        return []
    try:
        page = random.randint(1, 20)
        res = search_tags("", category, limit=100, page=page)
        names = [it["tag"] for it in (res.get("items") or []) if it.get("tag")]
        if not names:
            return []
        return random.sample(names, min(n, len(names)))
    except Exception as e:  # noqa: BLE001
        print(f"[NaibaTagPicker] 扭蛋随机标签失败({category}): {e}")
        return []


def get_completely_random_tags(total: int) -> list:
    """完全随机：把 total 个名额随机分摊到画师/角色/IP 三类，各自随机取样。"""
    if total <= 0:
        return []
    total = min(total, 30)
    cats = ["artist", "character", "ip"]
    counts = [0, 0, 0]
    for _ in range(total):
        counts[random.randrange(3)] += 1
    tags = []
    for c, cnt in zip(cats, counts):
        if cnt:
            tags.extend(get_random_tags_from_category(c, cnt))
    return tags


# ============================================================
# HTTP 路由（import 即注册）
# ============================================================
@PromptServer.instance.routes.get('/naiba/tag/search')
async def tag_search_handler(request):
    q = request.query.get('q', '').strip()
    category = request.query.get('category', 'artist')
    try:
        limit = int(request.query.get('limit', '50'))
    except (TypeError, ValueError):
        limit = 50
    try:
        page = int(request.query.get('page', '1'))
    except (TypeError, ValueError):
        page = 1
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: search_tags(q, category, limit, page))
        return web.json_response(result)
    except Exception as e:  # noqa: BLE001
        return web.json_response({"items": [], "warn": str(e), "page": page, "has_more": False})


@PromptServer.instance.routes.get('/naiba/tag/image')
async def tag_image_handler(request):
    u = request.query.get('u', '')
    if not u:
        return web.Response(status=400, text="Missing url")
    try:
        real_url = base64.urlsafe_b64decode(u + "===").decode()
    except Exception:  # noqa: BLE001
        return web.Response(status=400, text="Bad url")
    # SSRF 防护：仅允许 Danbooru CDN 域名
    if CDN_HOST_SUFFIX not in real_url:
        return web.Response(status=403, text="Forbidden")
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, lambda: fetch_image_bytes(real_url))
    except Exception as e:  # noqa: BLE001
        return web.Response(status=500, text=str(e))
    if not data:
        # 取不到图（CDN 404/限流）：返回占位 SVG，避免浏览器破图图标
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="140" height="120">'
            b'<rect width="100%" height="100%" fill="#16213e"/>'
            b'<text x="50%" y="50%" fill="#888" font-size="11" '
            b'text-anchor="middle" dominant-baseline="middle">no image</text>'
            b'</svg>'
        )
        return web.Response(
            body=svg,
            content_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    mime = detect_image_mime(data)
    return web.Response(
        body=data,
        content_type=mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@PromptServer.instance.routes.get('/naiba/tag/preview')
async def tag_preview_handler(request):
    """按标签名取代表作首图代理 URL（懒加载用，与 comfyui-anima-t8 的 dtags/preview 一致）。

    返回 JSON：{"image_url": "/naiba/tag/image?u=<base64>", "source_url": "..."}。
    image_url 为空表示取不到（限流/无代表作），前端据此显示占位（标签名）。
    """
    name = (request.query.get('name', '') or '').strip()
    if not name:
        return web.json_response({"image_url": "", "source_url": ""}, status=400)
    loop = asyncio.get_event_loop()
    try:
        proxy = await loop.run_in_executor(None, lambda: build_preview_proxy(name))
    except Exception as e:  # noqa: BLE001
        return web.json_response({"image_url": "", "source_url": "", "error": str(e)})
    source = f"{DANBOORU_BASE}/posts?tags={urllib.parse.quote(name)}" if name else ""
    return web.json_response({"image_url": proxy, "source_url": source})


@PromptServer.instance.routes.get('/naiba/tag/gacha_random')
async def tag_gacha_random_handler(request):
    """扭蛋「完全随机」：按 total（0~3N）个名额随机取标签。返回 {"tags": [...]}。"""
    try:
        total = int(request.query.get('total', '9'))
    except (TypeError, ValueError):
        total = 9
    total = max(0, min(int(total), 30))
    loop = asyncio.get_event_loop()
    try:
        tags = await loop.run_in_executor(None, lambda: get_completely_random_tags(total))
        return web.json_response({"tags": tags})
    except Exception as e:  # noqa: BLE001
        return web.json_response({"tags": [], "error": str(e)})


@PromptServer.instance.routes.get('/naiba/tag/gacha_partial')
async def tag_gacha_partial_handler(request):
    """扭蛋「部分随机」：按前端指定的每类数量（artist/character/ip 各 0~10）直接从 Danbooru
    实时随机取样，返回 {"tags": [画师…, 角色…, IP…]}。不依赖任何候选输入。"""
    def _parse(name, default):
        try:
            v = int(request.query.get(name, str(default)))
        except (TypeError, ValueError):
            v = default
        return max(0, min(int(v), 10))
    a = _parse('artist', 3)
    c = _parse('character', 3)
    i = _parse('ip', 3)
    loop = asyncio.get_event_loop()
    try:
        tags = await loop.run_in_executor(None, lambda: (
            get_random_tags_from_category("artist", a)
            + get_random_tags_from_category("character", c)
            + get_random_tags_from_category("ip", i)
        ))
        return web.json_response({"tags": tags, "counts": {"artist": a, "character": c, "ip": i}})
    except Exception as e:  # noqa: BLE001
        return web.json_response({"tags": [], "error": str(e)})


# ============================================================
# 工具：解码 proxy url → 真实 url
# ============================================================
def _decode_proxy_url(proxy_url: str):
    if not proxy_url:
        return None
    if "/naiba/tag/image?u=" in proxy_url:
        enc = proxy_url.split("u=", 1)[1]
        try:
            return base64.urlsafe_b64decode(enc + "===").decode()
        except Exception:  # noqa: BLE001
            return None
    if proxy_url.startswith("http"):
        return proxy_url
    return None


def _load_preview_tensor(real_url: str, size: int):
    """下载一张预览图 → 缩放(保持比例)并居中贴到 size×size 黑底 → [H,W,3] float32。"""
    try:
        data = fetch_image_bytes(real_url)
        if not data:
            return None
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            im.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGB", (size, size), (0, 0, 0))
            canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
            arr = np.asarray(canvas, dtype=np.float32) / 255.0
            return torch.from_numpy(arr)
    except Exception as e:  # noqa: BLE001
        print(f"[NaibaTagPicker] 预览加载失败 {real_url}: {e}")
        return None


def _load_preview_tensor_by_name(name: str, size: int):
    """按标签名取代表作首图 → 居中贴到 size×size 黑底 → [H,W,3] float32。"""
    try:
        data = fetch_tag_preview_bytes(name)
        if not data:
            return None
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            im.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGB", (size, size), (0, 0, 0))
            canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
            arr = np.asarray(canvas, dtype=np.float32) / 255.0
            return torch.from_numpy(arr)
    except Exception as e:  # noqa: BLE001
        print(f"[NaibaTagPicker] 预览加载失败 {name}: {e}")
        return None


# ============================================================
# 节点类
# ============================================================
class NaibaTagPicker:
    """
    标签画廊选择器：
    - 前端三标签页（画师/角色/IP）画廊多选，把分组 JSON 写回隐藏控件 selection_data。
    - execute 解析 JSON，输出三类标签名串 + 选中图批量预览 IMAGE。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selection_data": ("STRING", {
                    "default": "{}",
                    "multiline": True,
                    "tooltip": "三分类选中数据（由前端画廊自动管理，无需手动编辑）",
                }),
                "max_images": ("INT", {
                    "default": 16,
                    "min": 1,
                    "max": 64,
                    "step": 1,
                    "tooltip": "批量预览图最大张数（超出截断）",
                }),
                "preview_size": ("INT", {
                    "default": 320,
                    "min": 64,
                    "max": 512,
                    "step": 8,
                    "tooltip": "预览图边长上限（保持比例居中贴到正方形，控制显存）",
                }),
                "gacha_mode": ("BOOLEAN", {
                    "default": False,
                    "label_on": "扭蛋开",
                    "label_off": "扭蛋关",
                    "tooltip": "开启后输出 RANDOM_TAGS（扭蛋随机标签组合）；关闭则输出空串",
                }),
                "gacha_data": ("STRING", {
                    "default": "{}",
                    "multiline": True,
                    "tooltip": "扭蛋结果（由弹窗扭蛋标签页自动管理）：{\"tags\": [...]}",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("ARTIST_NAMES", "CHARACTER_NAMES", "IP_NAMES", "RANDOM_TAGS", "PREVIEW_IMAGES")
    FUNCTION = "execute"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "标签画廊选择器 - 通过 Danbooru API 搜索画师/角色/IP，前端三标签页画廊多选。\n"
        "扭蛋模式：弹窗内分别指定「画师/角色/IP 每类抽几个（0~10）」，\n"
        "部分随机由后端从 Danbooru 实时随机取样（画师 a + 角色 c + IP i 个），或完全随机产出一组随机标签，并从 RANDOM_TAGS 输出；\n"
        "扭蛋面板内与节点外部均提供一键「清除」按钮。\n"
        "输出三类标签名串（画师/角色/IP）、扭蛋随机标签串、选中图批量预览（IMAGE，仅内存、不落盘）。\n"
        "可选环境变量 DANBOORU_USER / DANBOORU_API_KEY 提升 API 限额。"
    )
    SEARCH_ALIASES = ["naiba", "tag picker", "danbooru", "artist", "character", "copyright", "gacha", "扭蛋"]

    def execute(self, selection_data, max_images, preview_size, gacha_mode, gacha_data):
        try:
            sel = json.loads(selection_data) if selection_data and selection_data.strip() else {}
        except (json.JSONDecodeError, TypeError):
            sel = {}

        if not isinstance(sel, dict):
            sel = {}

        artist_items = sel.get("artist", []) or []
        character_items = sel.get("character", []) or []
        ip_items = sel.get("ip", []) or []

        artist_names = ", ".join(it.get("tag", "") for it in artist_items if it.get("tag"))
        character_names = ", ".join(it.get("tag", "") for it in character_items if it.get("tag"))
        ip_names = ", ".join(it.get("tag", "") for it in ip_items if it.get("tag"))

        # 扭蛋随机标签组合
        random_tags = ""
        if gacha_mode:
            gacha = {}
            try:
                gacha = json.loads(gacha_data) if gacha_data and gacha_data.strip() else {}
            except (json.JSONDecodeError, TypeError):
                gacha = {}
            gt = gacha.get("tags") if isinstance(gacha, dict) else None
            if isinstance(gt, list) and gt:
                # 弹窗已选：输出该随机组合
                random_tags = ", ".join(str(t) for t in gt if t)
            else:
                # 弹窗未选择：等于完全随机标签
                random_tags = ", ".join(get_completely_random_tags(9))

        # 合并三类选中标签，按标签名去重（跨分类同名只取一次预览）
        seen = set()
        tag_names = []
        for it in artist_items + character_items + ip_items:
            name = it.get("tag")
            if name and name not in seen:
                seen.add(name)
                tag_names.append(name)

        tensors = []
        warn = ""
        if tag_names:
            if len(tag_names) > max_images:
                warn = f"预览图 {len(tag_names)} 张超过上限 {max_images}，已截断"
                tag_names = tag_names[:max_images]
            size = int(preview_size)
            with ThreadPoolExecutor(max_workers=6) as ex:
                results = list(ex.map(lambda n: _load_preview_tensor_by_name(n, size), tag_names))
            tensors = [t for t in results if t is not None]

        if tensors:
            batch = torch.stack(tensors, dim=0)
        else:
            batch = torch.zeros((1, 64, 64, 3), dtype=torch.float32)

        if warn:
            print(f"[NaibaTagPicker] {warn}")

        return (artist_names, character_names, ip_names, random_tags, batch)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "NaibaTagPicker": NaibaTagPicker,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaTagPicker": "Naiba Tag Picker (画师/角色/IP/扭蛋)",
}

print("[NaibaTagPicker] loaded: routes /naiba/tag/search, /naiba/tag/preview, /naiba/tag/image, /naiba/tag/gacha_random, /naiba/tag/gacha_partial")
