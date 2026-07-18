import os
import sys
import json
import time
import random
import base64
import threading
import hashlib
import asyncio
import urllib.request
import urllib.parse
import urllib.error
import io
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch
import folder_paths

# 仅在 ComfyUI 环境下导入（避免纯语法/单测时缺失）
try:
    from PIL import Image
except Exception:
    Image = None

# 后端令牌桶：兜底限流，避免瞬时高并发把 Danbooru 打爆
try:
    import aiohttp
    from aiohttp import web
    from server import PromptServer
except Exception:  # pragma: no cover
    aiohttp = None
    web = None
    PromptServer = None

BASE = "https://danbooru.donmai.us"
# 原版可用 UA：Danbooru/Cloudflare 会封含 "ComfyUI" 的 UA，故用自定义标识
UA = {"User-Agent": "naiba-tag-picker/1.0 (+naiba-node)"}

# Danbooru category 字段为数字 ID；分类字符串 <-> 数字 ID <-> 显示名 互转
CATEGORY_ID = {"artist": 1, "character": 4, "copyright": 3, "tag": 0}
CATEGORY_NAME_BY_ID = {0: "tag", 1: "artist", 3: "copyright", 4: "character"}

# ----------------------------- 后端令牌桶 -----------------------------
_bucket_lock = threading.Lock()
_bucket_tokens = 5.0
_BUCKET_MAX = 5.0
_BUCKET_REFILL = 5.0  # 每秒补充 5 个

def _bucket_allow():
    global _bucket_tokens
    now = time.time()
    with _bucket_lock:
        elapsed = now - getattr(_bucket_allow, "_t", now)
        _bucket_allow._t = now
        _bucket_tokens = min(_BUCKET_MAX, _bucket_tokens + elapsed * _BUCKET_REFILL)
        if _bucket_tokens >= 1.0:
            _bucket_tokens -= 1.0
            return True
        return False

def _fetch_url(url, timeout=15, retries=3, backoff=1.0):
    """带后端限流的网络 GET，返回字节或 None。
    对 403/429/5xx 做指数退避重试（还原原版 _api_request 的稳健性）。"""
    for attempt in range(retries + 1):
        if not _bucket_allow():
            time.sleep(0.25)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if attempt < retries and e.code in (403, 429, 500, 502, 503):
                time.sleep(backoff * (2 ** attempt))
                continue
            print(f"[naiba_tag_picker] fetch failed: {url} -> HTTP {e.code} {e.reason}")
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            print(f"[naiba_tag_picker] fetch failed: {url} -> {e}")
            return None
    return None

# ----------------------------- 图片 MIME 识别 -----------------------------
def detect_image_mime(data):
    if not data:
        return "application/octet-stream"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF89a", b"GIF87a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"

# ----------------------------- L1 内存缓存 -----------------------------
class ImageCache:
    def __init__(self, max_size=100, ttl=3600):
        self.max_size = max_size
        self.ttl = ttl
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            data, ts = item
            if time.time() - ts > self.ttl:
                self._store.pop(key, None)
                return None
            return data

    def set(self, key, data):
        if not data:
            return
        with self._lock:
            self._store[key] = (data, time.time())
            if len(self._store) > self.max_size:
                # 简单淘汰最旧
                oldest = min(self._store.items(), key=lambda kv: kv[1][1])
                self._store.pop(oldest[0], None)

_IMAGE_CACHE = ImageCache(max_size=100, ttl=3600)

# ----------------------------- L2 磁盘缓存 -----------------------------
# 与扭蛋逻辑完全解耦；插件全局目录，多节点实例共享；按 URL sha1 命名。
class DiskCache:
    def __init__(self, base_dir, max_items=300, enabled=True):
        self.dir = base_dir
        self.max_items = max(10, min(int(max_items), 5000))
        self.enabled = bool(enabled)
        self.lock = threading.Lock()
        if self.enabled:
            try:
                os.makedirs(self.dir, exist_ok=True)
            except Exception:
                self.enabled = False  # 目录不可写则降级，绝不中断主流程

    def _path(self, key):
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return os.path.join(self.dir, h + ".img")

    def get(self, key):
        if not self.enabled:
            return None
        p = self._path(key)
        if not os.path.exists(p):
            return None
        try:
            with open(p, "rb") as f:
                data = f.read()
            if not data or detect_image_mime(data) == "application/octet-stream":
                return None
            # 命中更新 atime，实现真正 LRU（按访问时间裁剪）
            os.utime(p, None)
            return data
        except Exception:
            return None

    def set(self, key, data):
        if not self.enabled or not data:
            return
        p = self._path(key)
        tmp = p + ".tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, p)  # 原子重命名，避免并发半文件
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass
            return
        self._prune()

    def _prune(self):
        with self.lock:
            try:
                entries = []
                for fn in os.listdir(self.dir):
                    if not fn.endswith(".img"):
                        continue
                    fp = os.path.join(self.dir, fn)
                    try:
                        st = os.stat(fp)
                        entries.append((st.st_atime, fp))
                    except Exception:
                        pass
                if len(entries) > self.max_items:
                    entries.sort()
                    excess = len(entries) - self.max_items
                    for _, fp in entries[:excess]:
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
            except Exception:
                pass

# 全局磁盘缓存单例；由 execute() / 预览路由按需 configure
_DISK_CACHE = None

def configure_disk_cache(enabled, max_items):
    global _DISK_CACHE
    enabled = bool(enabled)
    max_items = max(10, min(int(max_items), 5000))
    if _DISK_CACHE is None:
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview_cache")
        _DISK_CACHE = DiskCache(cache_dir, max_items, enabled)
    else:
        _DISK_CACHE.enabled = enabled
        _DISK_CACHE.max_items = max_items

def fetch_image_bytes(url):
    """L1(内存) -> L2(磁盘) -> 网络 三级查找。"""
    cached = _IMAGE_CACHE.get(url)
    if cached is not None:
        return cached
    if _DISK_CACHE is not None:
        disk = _DISK_CACHE.get(url)
        if disk:
            _IMAGE_CACHE.set(url, disk)
            return disk
    data = _fetch_url(url)
    if data:
        _IMAGE_CACHE.set(url, data)
        if _DISK_CACHE is not None:
            _DISK_CACHE.set(url, data)
    return data

# ----------------------------- Danbooru 搜索 -----------------------------
def search_tags(query, category="", limit=100, page=1):
    """
    category: "tag"/"artist"/"character"/"copyright"(ip) 或空。
    返回 {"items":[{"id","tag","post_count","category","preview_url","source_url"}], "total":int}
    注意：
      - Danbooru 标签字段名为 name（非 tag），且匿名禁用 random 排序 -> 走 search[order]=count。
      - category 请求用数字 ID（1/3/4），更稳；返回时再映射回显示名字符串。
    """
    cat_id = CATEGORY_ID.get(category, 0)
    params = {
        "limit": limit,
        "page": page,
        "search[order]": "count",
        "search[hide_empty]": "yes",
        "search[post_count_gteq]": "10",
    }
    if query:
        params["search[name_matches]"] = query + ("*" if not query.endswith("*") else "")
    if cat_id:
        params["search[category]"] = cat_id
    url = BASE + "/tags.json?" + urllib.parse.urlencode(params)
    raw = _fetch_url(url)
    if not raw:
        return {"items": [], "total": 0}
    try:
        arr = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"items": [], "total": 0}
    if not isinstance(arr, list):
        return {"items": [], "total": 0}
    items = []
    for it in arr:
        tag = it.get("name") or it.get("tag")
        if not tag:
            continue
        cid = it.get("category", cat_id)
        cname = CATEGORY_NAME_BY_ID.get(cid, category)
        items.append({
            "id": it.get("id"),
            "tag": tag,
            "post_count": it.get("post_count", 0),
            "category": cname,
            "preview_url": "",
            "source_url": f"{BASE}/posts?tags={urllib.parse.quote(tag)}",
        })
    return {"items": items, "total": len(items)}

# ----------------------------- 扭蛋取样（先过滤后采样，无重试死循环） -----------------------------
def get_random_tags_from_category(category, n, blacklist=None):
    """从 Danbooru 随机页聚集候选池（最多 2 页），一次性过滤黑名单、去重，sample(min(n, 可用))。"""
    if n <= 0:
        return []
    bl = set(blacklist or [])
    pool = []
    seen = set()
    try:
        for _ in range(2):
            pg = random.randint(1, 20)
            res = search_tags("", category, limit=100, page=pg)
            for it in (res.get("items") or []):
                nm = it.get("tag")
                if nm and nm not in seen:
                    seen.add(nm)
                    pool.append(nm)
    except Exception as e:
        print(f"[naiba_tag_picker] gacha pool error: {e}")
    filtered = [t for t in pool if t not in bl]
    if not filtered:
        return []
    if len(filtered) <= n:
        return list(filtered)
    return random.sample(filtered, n)

def get_completely_random_tags(total, blacklist=None):
    """完全随机：每个分类先聚一次候选池（先过滤黑名单），再按组抽样保证 trio 完整。"""
    if total <= 0:
        return []
    bl = set(blacklist or [])
    cats = ["artist", "character", "copyright"]
    pools = {}
    for c in cats:
        pool = []
        seen = set()
        for _ in range(3):
            res = search_tags("", c, limit=100, page=random.randint(1, 20))
            for it in (res.get("items") or []):
                nm = it.get("tag")
                if nm and nm not in seen:
                    seen.add(nm)
                    pool.append(nm)
        pools[c] = [t for t in pool if t not in bl]
    out = []
    used = set()
    for _ in range(total):
        trio = []
        ok = True
        for c in cats:
            avail = [t for t in pools[c] if t not in used]
            if not avail:
                ok = False
                break
            pick = random.choice(avail)
            used.add(pick)
            trio.append({"tag": pick, "category": c})
        if ok:
            out.extend(trio)
    return out

# 预生成预览图代理用的随机 post 图
_PREVIEW_URL_CACHE = {}

def get_random_post_image_url(tag):
    key = "tag:" + tag
    cached = _PREVIEW_URL_CACHE.get(key)
    if cached:
        return cached
    # 不加 random=true（匿名会 403）；改为多取几条后客户端随机选一条，保证多样性
    url = f"{BASE}/posts.json?tags={urllib.parse.quote(tag)}&limit=20"
    raw = _fetch_url(url)
    if not raw:
        return None
    try:
        arr = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not arr:
        return None
    it = random.choice(arr)
    preview = it.get("preview_file_url") or it.get("media_asset", {}).get("preview_file_url")
    if preview and not preview.startswith("http"):
        preview = BASE + preview
    if preview:
        _PREVIEW_URL_CACHE[key] = preview
    return preview

def build_preview_proxy(tag):
    real = get_random_post_image_url(tag)
    if not real:
        return None
    data = fetch_image_bytes(real)
    if not data:
        return None
    mime = detect_image_mime(data)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"

# ----------------------------- 节点 -----------------------------
class NaibaTagPicker:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # —— 计划前（原版）外部 UI：仅 6 个控件 ——
                "selection_data": ("STRING", {"multiline": True, "default": "{}", "label": "已选标签(JSON，隐藏)"}),
                "max_images": ("INT", {"default": 16, "min": 1, "max": 64, "step": 1, "tooltip": "批量预览图最大张数（超出截断）"}),
                "preview_size": ("INT", {"default": 320, "min": 64, "max": 512, "step": 8, "tooltip": "预览图边长上限（保持比例居中贴到正方形，控制显存）"}),
                "artist_at": ("BOOLEAN", {
                    "default": False,
                    "label_on": "画师加 @",
                    "label_off": "画师不加 @",
                    "tooltip": "开启后画师标签输出为 @画师名；关闭则原样输出画师名",
                }),
                "gacha_mode": ("BOOLEAN", {
                    "default": False,
                    "label_on": "扭蛋开",
                    "label_off": "扭蛋关",
                    "tooltip": "开启后输出扭蛋随机标签组合；关闭则输出空串",
                }),
                "gacha_data": ("STRING", {"multiline": True, "default": "{}", "label": "扭蛋结果(JSON，隐藏)"}),
            },
            "hidden": {
                # —— v2 增强功能：控件不显示在节点上，改由前端弹窗管理 ——
                "cache_enabled": ("BOOLEAN", {"default": True}),
                "cache_max_items": ("INT", {"default": 300, "min": 10, "max": 5000, "step": 10}),
                "sync_external_random": ("BOOLEAN", {"default": False}),
                "blacklist_data": ("STRING", {"multiline": True, "default": "{}"}),
                "favorites_data": ("STRING", {"multiline": True, "default": "{}"}),
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("ARTIST_NAMES", "CHARACTER_NAMES", "IP_NAMES", "MERGED_TAGS", "RANDOM_TAGS", "PREVIEW_IMAGES")
    FUNCTION = "execute"
    CATEGORY = "naiba-node"

    def execute(self, selection_data, max_images, preview_size, artist_at, gacha_mode, gacha_data,
                cache_enabled, cache_max_items, sync_external_random, blacklist_data, favorites_data,
                prompt=None, extra_pnginfo=None):
        # 配置磁盘缓存（仅当开启且目录可写时生效；否则降级内存）
        configure_disk_cache(cache_enabled, cache_max_items)

        # 已选标签：兼容 v2（selected 列表）与原版（artist/character/ip 分组）两种结构
        try:
            sel = json.loads(selection_data) if isinstance(selection_data, str) else selection_data
            if not isinstance(sel, dict):
                sel = {}
        except Exception:
            sel = {}
        selected = []
        if isinstance(sel, dict):
            if "selected" in sel:
                selected = sel.get("selected") or []
            else:
                for cat in ("artist", "character", "ip"):
                    for it in (sel.get(cat) or []):
                        if isinstance(it, dict) and it.get("tag"):
                            selected.append({"tag": it["tag"], "category": cat})
        if not isinstance(selected, list):
            selected = []

        def _norm_cat(c):
            c = c or "tag"
            return "ip" if c in ("copyright", "ip") else c

        artist_items = [it for it in selected if _norm_cat(it.get("category")) == "artist"]
        character_items = [it for it in selected if _norm_cat(it.get("category")) == "character"]
        ip_items = [it for it in selected if _norm_cat(it.get("category")) == "ip"]

        # 画师按 artist_at 开关加 @ 前缀
        artist_names_list = [
            (("@" + t) if artist_at else t)
            for t in (it.get("tag", "") for it in artist_items)
            if t
        ]
        character_names_list = [it.get("tag", "") for it in character_items if it.get("tag")]
        ip_names_list = [it.get("tag", "") for it in ip_items if it.get("tag")]

        artist_names = ", ".join(artist_names_list)
        character_names = ", ".join(character_names_list)
        ip_names = ", ".join(ip_names_list)
        merged_tags = ", ".join(artist_names_list + character_names_list + ip_names_list)

        # 扭蛋随机标签组合（gacha_mode 开启时输出；画师按 artist_at 加 @）
        random_tags = ""
        if gacha_mode:
            gacha = {}
            try:
                gacha = json.loads(gacha_data) if gacha_data and str(gacha_data).strip() else {}
            except (json.JSONDecodeError, TypeError):
                gacha = {}
            gt = gacha.get("tags") if isinstance(gacha, dict) else None
            if isinstance(gt, list) and gt:
                random_tags = ", ".join(_format_gacha_tags(gt, artist_at))

        # 批量预览：所有选中标签名去重（预览图不带 @）
        seen = set()
        tag_names = []
        for it in selected:
            name = it.get("tag") if isinstance(it, dict) else it
            if name and name not in seen:
                seen.add(name)
                tag_names.append(name)

        preview_tensors = []
        if tag_names:
            if len(tag_names) > max_images:
                tag_names = tag_names[:max_images]
            for name in tag_names:
                try:
                    preview_tensors.append(_load_preview_tensor_by_name(name, preview_size))
                except Exception as e:
                    print(f"[naiba_tag_picker] preview fail {name}: {e}")

        if preview_tensors:
            previews = torch.cat(preview_tensors, dim=0)
        else:
            previews = torch.zeros((1, preview_size, preview_size, 3), dtype=torch.float32)

        return (artist_names, character_names, ip_names, merged_tags, random_tags, previews)

def _format_gacha_tags(gt, artist_at: bool) -> list:
    """把扭蛋标签（兼容 [str] 旧格式 与 [{"tag","category"}] 新格式）转为输出名列表。
    开启 artist_at 时，分类为 artist 的标签加 @ 前缀。"""
    parts = []
    if not isinstance(gt, list):
        return parts
    for t in gt:
        if isinstance(t, str):
            name, cat = t, "tag"
        elif isinstance(t, dict):
            name = t.get("tag", "")
            cat = t.get("category", "tag")
        else:
            continue
        if not name:
            continue
        if artist_at and cat == "artist":
            name = "@" + name
        parts.append(name)
    return parts


def _load_preview_tensor_by_name(name, size):
    real = get_random_post_image_url(name)
    if real:
        data = fetch_image_bytes(real)
        if data:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img = img.resize((size, size))
            arr = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(arr)[None,]
    # 失败兜底：纯色块
    arr = np.zeros((size, size, 3), dtype=np.float32)
    return torch.from_numpy(arr)[None,]

# ----------------------------- 路由注册 -----------------------------
def _parse_json_list(raw):
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(v, list):
            return [str(x) for x in v if x]
    except Exception:
        pass
    return []

def register_routes():
    if PromptServer is None or web is None:
        return

    @PromptServer.instance.routes.get("/naiba/tag/search")
    async def tag_search(request):
        q = request.query.get("q", "")
        cat = request.query.get("cat", "tag")
        try:
            limit = int(request.query.get("limit", "100"))
        except Exception:
            limit = 100
        try:
            page = int(request.query.get("page", "1"))
        except Exception:
            page = 1
        category = {"artist": "artist", "character": "character", "ip": "copyright", "tag": "tag"}.get(cat, "tag")
        res = await _run_in_exec(search_tags, q, category, limit, page)
        return web.json_response(res)

    @PromptServer.instance.routes.get("/naiba/tag/preview")
    async def tag_preview(request):
        tag = request.query.get("tag", "")
        try:
            size = int(request.query.get("size", "220"))
        except Exception:
            size = 220
        _consume_cache_params(request)
        if not tag:
            return web.json_response({"preview_url": None, "source_url": None})
        # 在后台线程构造 base64 预览
        data = await _run_in_exec(build_preview_proxy, tag)
        source_url = f"{BASE}/posts?tags={urllib.parse.quote(tag)}"
        return web.json_response({"preview_url": data, "source_url": source_url})

    @PromptServer.instance.routes.get("/naiba/tag/image")
    async def tag_image(request):
        u = request.query.get("u", "")
        _consume_cache_params(request)
        if not u:
            return web.Response(status=400, text="missing u")
        data = await _run_in_exec(fetch_image_bytes, u)
        if not data:
            return web.Response(status=502, text="fetch failed")
        mime = detect_image_mime(data)
        return web.Response(body=data, content_type=mime)

    @PromptServer.instance.routes.get("/naiba/tag/gacha_partial")
    async def gacha_partial(request):
        try:
            a = int(request.query.get("artist", "0"))
        except Exception:
            a = 0
        try:
            c = int(request.query.get("character", "0"))
        except Exception:
            c = 0
        try:
            i = int(request.query.get("ip", "0"))
        except Exception:
            i = 0
        blacklist = _parse_json_list(request.query.get("blacklist", "[]"))
        out, shortfall = await _run_in_exec(_gacha_partial_job, a, c, i, blacklist)
        return web.json_response({"tags": out, "shortfall": shortfall})

    @PromptServer.instance.routes.get("/naiba/tag/gacha_random")
    async def gacha_random(request):
        try:
            total = int(request.query.get("total", "9"))
        except Exception:
            total = 9
        blacklist = _parse_json_list(request.query.get("blacklist", "[]"))
        tags = await _run_in_exec(get_completely_random_tags, total, blacklist)
        return web.json_response({"tags": tags})

    @PromptServer.instance.routes.get("/naiba/tag/hello")
    async def tag_hello(request):
        return web.json_response({"ok": True})

def _consume_cache_params(request):
    cache_on = request.query.get("cache", "1") not in ("0", "false", "False", "0")
    try:
        max_items = int(request.query.get("max", "300"))
    except Exception:
        max_items = 300
    configure_disk_cache(cache_on, max_items)

def _gacha_partial_job(a, c, i, blacklist):
    cats = [("artist", a), ("character", c), ("copyright", i)]
    out = []
    shortfall = {}
    for cname, cnt in cats:
        tags = get_random_tags_from_category(cname, cnt, blacklist)
        actual = len(tags)
        for t in tags:
            out.append({"tag": t, "category": cname})
        if cnt > 0 and actual < cnt:
            reason = "blacklist_or_insufficient"
            shortfall[cname] = {"requested": cnt, "actual": actual, "reason": reason}
    return out, shortfall

_EXECUTOR = None
_EXECUTOR_LOCK = threading.Lock()
def _get_executor():
    global _EXECUTOR
    if _EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _EXECUTOR is None:
                _EXECUTOR = ThreadPoolExecutor(max_workers=4)
    return _EXECUTOR

async def _run_in_exec(fn, *args):
    """在后台线程执行阻塞 IO，返回结果（路由处理器在事件循环内 await）。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), fn, *args)

# ----------------------------- 注册 -----------------------------
try:
    register_routes()
except Exception as e:
    print(f"[naiba_tag_picker] register_routes error: {e}")

NODE_CLASS_MAPPINGS = {
    "NaibaTagPicker": NaibaTagPicker,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaTagPicker": "Naiba Tag Picker 🎯",
}
