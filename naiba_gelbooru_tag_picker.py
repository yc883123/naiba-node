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
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch
import folder_paths

# 仅在 ComfyUI 环境下导入（避免纯语法/单测时缺失）
try:
    from PIL import Image
except Exception:
    Image = None

# 后端令牌桶：兜底限流，避免瞬时高并发把 Gelbooru 打爆
try:
    import aiohttp
    from aiohttp import web
    from server import PromptServer
except Exception:  # pragma: no cover
    aiohttp = None
    web = None
    PromptServer = None

BASE = "https://gelbooru.com"
# 原版可用 UA：Gelbooru 会封含 "ComfyUI" 的 UA，故用自定义标识
UA = {"User-Agent": "naiba-gelbooru-picker/1.0 (+naiba-node)"}
REFERER = {"Referer": "https://gelbooru.com/"}

# Gelbooru 分类约定（与 Danbooru 数字 ID 一致）：0=general, 1=artist, 3=copyright, 4=character
CATEGORY_ID = {"artist": 1, "character": 4, "copyright": 3, "tag": 0}
CATEGORY_NAME_BY_ID = {0: "tag", 1: "artist", 3: "copyright", 4: "character"}

# autocomplete2 行内 category 字段（字符串）-> 数字 ID
_AUTOCOMPLETE_CAT = {"tag": 0, "metadata": 0, "artist": 1, "copyright": 3, "character": 4}

# 无 query 时各分类的默认种子词（用于匿名默认列表）
_FALLBACK_TERMS = {
    0: ["1girl", "solo", "long_hair", "blue_eyes", "blush", "smile", "absurdres", "highres"],
    1: ["wlop", "hiten", "kantoku", "ask", "as109", "ciloranko", "redjuice", "tony"],
    3: ["genshin", "naruto", "pokemon", "fate", "azur_lane", "touhou", "blue_archive", "kantai"],
    4: ["hatsune", "miku", "saber", "rem", "lumine", "raiden", "asuna", "frieren"],
}

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

def _is_gelbooru(url):
    try:
        host = urllib.parse.urlparse(url).hostname or ""
        return host == "gelbooru.com" or host.endswith(".gelbooru.com")
    except Exception:
        return False

def _fetch_url(url, timeout=15, retries=3, backoff=1.0):
    """带后端限流的网络 GET，返回字节或 None。
    对 403/429/5xx 做指数退避重试。"""
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
            print(f"[naiba_gelbooru] fetch failed: {url} -> HTTP {e.code} {e.reason}")
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            print(f"[naiba_gelbooru] fetch failed: {url} -> {e}")
            return None
    return None

def _fetch_url_gb(url, timeout=15, retries=3, backoff=1.0):
    """Gelbooru 图片/HTML 专用 GET：加 Referer 头 + SSRF 白名单（仅 gelbooru.com）。"""
    if not _is_gelbooru(url):
        print(f"[naiba_gelbooru] SSRF blocked: {url}")
        return None
    for attempt in range(retries + 1):
        if not _bucket_allow():
            time.sleep(0.25)
        try:
            headers = dict(UA)
            headers.update(REFERER)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if attempt < retries and e.code in (403, 429, 500, 502, 503):
                time.sleep(backoff * (2 ** attempt))
                continue
            print(f"[naiba_gelbooru] fetch(gb) failed: {url} -> HTTP {e.code} {e.reason}")
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            print(f"[naiba_gelbooru] fetch(gb) failed: {url} -> {e}")
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
                oldest = min(self._store.items(), key=lambda kv: kv[1][1])
                self._store.pop(oldest[0], None)

_IMAGE_CACHE = ImageCache(max_size=100, ttl=3600)

# ----------------------------- L2 磁盘缓存 -----------------------------
MAX_CACHE_HARD_MB = 51200  # 硬性最大限制 50GB

class DiskCache:
    def __init__(self, base_dir, max_size_mb=500, enabled=True):
        self.dir = base_dir
        self.max_bytes = min(int(max_size_mb), MAX_CACHE_HARD_MB) * 1024 * 1024
        self.enabled = bool(enabled)
        self.lock = threading.Lock()
        if self.enabled:
            try:
                os.makedirs(self.dir, exist_ok=True)
            except Exception:
                self.enabled = False  # 目录不可写则降级，绝不中断主流程

    def _path(self, key, ext=".img"):
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return os.path.join(self.dir, h + ext)

    def get(self, key):
        if not self.enabled:
            return None
        p = self._path(key, ".img")
        if not os.path.exists(p):
            return None
        try:
            with open(p, "rb") as f:
                data = f.read()
            if not data or detect_image_mime(data) == "application/octet-stream":
                return None
            os.utime(p, None)
            return data
        except Exception:
            return None

    def set(self, key, data):
        if not self.enabled or not data:
            return
        p = self._path(key, ".img")
        tmp = p + ".tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, p)
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass
            return
        self._prune()

    def get_json(self, key):
        if not self.enabled:
            return None
        p = self._path(key, ".json")
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
            os.utime(p, None)
            return obj
        except Exception:
            return None

    def set_json(self, key, obj):
        if not self.enabled or obj is None:
            return
        p = self._path(key, ".json")
        tmp = p + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            os.replace(tmp, p)
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass
            return
        self._prune()

    def size_mb(self):
        if not self.enabled or not os.path.exists(self.dir):
            return 0.0
        total = 0
        try:
            for fn in os.listdir(self.dir):
                if fn.endswith(".img") or fn.endswith(".json"):
                    total += os.path.getsize(os.path.join(self.dir, fn))
        except Exception:
            pass
        return total / (1024 * 1024)

    def _prune(self):
        with self.lock:
            try:
                entries = []
                total_bytes = 0
                for fn in os.listdir(self.dir):
                    if not (fn.endswith(".img") or fn.endswith(".json")):
                        continue
                    fp = os.path.join(self.dir, fn)
                    try:
                        st = os.stat(fp)
                        entries.append((st.st_atime, fp, st.st_size))
                        total_bytes += st.st_size
                    except Exception:
                        pass
                if total_bytes > self.max_bytes:
                    entries.sort()
                    for _, fp, sz in entries:
                        if total_bytes <= self.max_bytes:
                            break
                        try:
                            os.remove(fp)
                            total_bytes -= sz
                        except Exception:
                            pass
            except Exception:
                pass

_DISK_CACHE = None

def configure_disk_cache(enabled, max_size_mb):
    global _DISK_CACHE
    enabled = bool(enabled)
    max_size_mb = max(100, min(int(max_size_mb), 20000, MAX_CACHE_HARD_MB))
    if _DISK_CACHE is None:
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview_cache_gelbooru")
        _DISK_CACHE = DiskCache(cache_dir, max_size_mb, enabled)
    else:
        _DISK_CACHE.enabled = enabled
        _DISK_CACHE.max_bytes = max_size_mb * 1024 * 1024

def fetch_image_bytes(url):
    """L1(内存) -> L2(磁盘) -> 网络 三级查找（Gelbooru 图片走带 Referer/白名单的 fetch）。"""
    cached = _IMAGE_CACHE.get(url)
    if cached is not None:
        return cached
    if _DISK_CACHE is not None:
        disk = _DISK_CACHE.get(url)
        if disk:
            _IMAGE_CACHE.set(url, disk)
            return disk
    data = _fetch_url_gb(url) if _is_gelbooru(url) else _fetch_url(url)
    if data:
        _IMAGE_CACHE.set(url, data)
        if _DISK_CACHE is not None:
            _DISK_CACHE.set(url, data)
    return data

# ----------------------------- 凭据解析 -----------------------------
def _load_auth_file():
    root = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(root, "data", "gelbooru_auth.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "api_key": str(data.get("api_key") or "").strip(),
        "user_id": str(data.get("user_id") or "").strip(),
    }

def _resolve_auth(api_key, user_id):
    """认证优先级：显式参数(节点控件) > 环境变量 > data/gelbooru_auth.json。"""
    api_key = (api_key or "").strip()
    user_id = (user_id or "").strip()
    if api_key and user_id:
        return api_key, user_id
    env_key = (os.environ.get("GELBOORU_API_KEY") or "").strip()
    env_uid = (os.environ.get("GELBOORU_USER_ID") or "").strip()
    if not api_key and env_key:
        api_key = env_key
    if not user_id and env_uid:
        user_id = env_uid
    if api_key and user_id:
        return api_key, user_id
    data = _load_auth_file()
    if not api_key:
        api_key = data.get("api_key") or None
    if not user_id:
        user_id = data.get("user_id") or None
    return api_key, user_id

# ----------------------------- Gelbooru 搜索 -----------------------------
def _normalize_url(url):
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return BASE + u
    return u

def _extract_records(data, key):
    """兼容 Gelbooru DAPI 常见 JSON 形态：{tag:[...]} / {tag:{...}} / [...] 。"""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    direct = data.get(key)
    if isinstance(direct, list):
        return [x for x in direct if isinstance(x, dict)]
    if isinstance(direct, dict):
        return [direct]
    plural = data.get(key + "s")
    if isinstance(plural, list):
        return [x for x in plural if isinstance(x, dict)]
    if isinstance(plural, dict):
        inner = plural.get(key)
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
        if isinstance(inner, dict):
            return [inner]
    if key == "tag" and ("name" in data or "count" in data):
        return [data]
    if key == "post" and ("file_url" in data or "preview_url" in data):
        return [data]
    return []

def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default

def _filter_autocomplete(rows, cat_id):
    out = []
    seen = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        raw_cat = r.get("category")
        if isinstance(raw_cat, int):
            row_cat = raw_cat
        else:
            row_cat = _AUTOCOMPLETE_CAT.get(str(raw_cat or "").lower(), 0)
        if cat_id is not None and row_cat != cat_id:
            continue
        name = (r.get("value") or r.get("label") or "").strip().replace(" ", "_")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({
            "name": name,
            "category": row_cat,
            "post_count": _safe_int(r.get("post_count"), 0),
        })
    return out

def _autocomplete_search(query, limit, cat_id):
    q = (query or "").strip()
    if not q:
        return None
    params = {
        "page": "autocomplete2",
        "term": q,
        "type": "tag_query",
        "limit": max(1, min(int(limit or 20), 50)),
    }
    url = BASE + "/index.php?" + urllib.parse.urlencode(params)
    raw = _fetch_url(url)
    if not raw:
        return None
    try:
        rows = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(rows, list):
        return []
    return _filter_autocomplete(rows, cat_id)

def _fallback_search(cat_id, limit):
    rows = []
    seen = set()
    for term in _FALLBACK_TERMS.get(cat_id, []):
        sub = _autocomplete_search(term, min(50, max(10, limit)), cat_id)
        if not sub:
            continue
        for r in sub:
            key = (r["name"], r["category"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    rows.sort(key=lambda x: (-int(x.get("post_count") or 0), x.get("name") or ""))
    return rows

def _rows_to_items(rows, category):
    items = []
    for r in (rows or []):
        name = r.get("name")
        if not name:
            continue
        row_cat = r.get("category", CATEGORY_ID.get(category, 0))
        cname = CATEGORY_NAME_BY_ID.get(row_cat, category)
        items.append({
            "id": None,
            "tag": name,
            "post_count": r.get("post_count", 0),
            "category": cname,
            "preview_url": "",
            "source_url": f"{BASE}/index.php?page=post&s=list&tags={urllib.parse.quote(name)}",
        })
    return items

def _parse_dapi_tags(raw, cat_id, category):
    try:
        arr = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    rows = _extract_records(arr, "tag")
    items = []
    for it in rows:
        name = (it.get("name") or it.get("tag") or "").strip()
        if not name:
            continue
        cid = _safe_int(it.get("type", it.get("category", cat_id)), cat_id)
        cname = CATEGORY_NAME_BY_ID.get(cid, category)
        items.append({
            "id": it.get("id"),
            "tag": name,
            "post_count": _safe_int(it.get("count", it.get("post_count")), 0),
            "category": cname,
            "preview_url": "",
            "source_url": f"{BASE}/index.php?page=post&s=list&tags={urllib.parse.quote(name)}",
        })
    return items

def search_tags(query, category="", limit=100, page=1, api_key=None, user_id=None):
    api_key, user_id = _resolve_auth(api_key, user_id)
    auth = bool(api_key and user_id)
    cache_key = f"{category}|{query}|{page}|{limit}|{'a' if auth else 'n'}"
    cat_id = CATEGORY_ID.get(category, 0)

    items = None
    if auth:
        params = {
            "page": "dapi",
            "s": "tag",
            "q": "index",
            "json": 1,
            "limit": limit,
            "pid": max(0, page - 1),
            "orderby": "count",
            "order": "desc",
            "type": cat_id,
            "api_key": api_key,
            "user_id": user_id,
        }
        url = BASE + "/index.php?" + urllib.parse.urlencode(params)
        raw = _fetch_url(url)
        if raw:
            items = _parse_dapi_tags(raw, cat_id, category)
    else:
        rows = _autocomplete_search(query, limit, cat_id)
        if rows is None:
            # 无 query 时走种子兜底
            if not (query or "").strip():
                rows = _fallback_search(cat_id, limit)
            else:
                rows = None
        if rows is not None:
            items = _rows_to_items(rows, category)
            # 匿名 autocomplete 仅返回单页（最多 50 条），翻页 >1 视为无更多
            if page > 1:
                items = []

    if items is None:
        if _DISK_CACHE is not None:
            cached = _DISK_CACHE.get_json(cache_key)
            if cached is not None:
                cached["cached"] = True
                return cached
        return {"items": [], "total": 0, "cached": False}

    result = {"items": items, "total": len(items), "cached": False}
    if _DISK_CACHE is not None:
        _DISK_CACHE.set_json(cache_key, {"items": items, "total": len(items)})
    return result

# ----------------------------- 扭蛋取样 -----------------------------
def get_random_tags_from_category(category, n, blacklist=None, api_key=None, user_id=None):
    """从 Gelbooru 随机页聚集候选池（最多 2 页），过滤黑名单、去重，sample(min(n, 可用))。
    匿名时走种子池 best-effort，候选较少属正常。"""
    if n <= 0:
        return []
    bl = set(blacklist or [])
    api_key, user_id = _resolve_auth(api_key, user_id)
    pool = []
    seen = set()
    try:
        if api_key and user_id:
            for _ in range(2):
                pg = random.randint(1, 20)
                res = search_tags("", category, limit=100, page=pg, api_key=api_key, user_id=user_id)
                for it in (res.get("items") or []):
                    nm = it.get("tag")
                    if nm and nm not in seen:
                        seen.add(nm)
                        pool.append(nm)
        else:
            cat_id = CATEGORY_ID.get(category, 0)
            for r in _fallback_search(cat_id, 50):
                nm = r.get("name")
                if nm and nm not in seen:
                    seen.add(nm)
                    pool.append(nm)
    except Exception as e:
        print(f"[naiba_gelbooru] gacha pool error: {e}")
    filtered = [t for t in pool if t not in bl]
    if not filtered:
        return []
    if len(filtered) <= n:
        return list(filtered)
    return random.sample(filtered, n)

def get_completely_random_tags(total, blacklist=None, api_key=None, user_id=None):
    """完全随机：每个分类先聚一次候选池（先过滤黑名单），再按组抽样保证 trio 完整。"""
    if total <= 0:
        return []
    bl = set(blacklist or [])
    cats = ["artist", "character", "copyright"]
    pools = {}
    for c in cats:
        pool = []
        seen = set()
        try:
            if api_key and user_id:
                for _ in range(3):
                    res = search_tags("", c, limit=100, page=random.randint(1, 20), api_key=api_key, user_id=user_id)
                    for it in (res.get("items") or []):
                        nm = it.get("tag")
                        if nm and nm not in seen:
                            seen.add(nm)
                            pool.append(nm)
            else:
                cat_id = CATEGORY_ID.get(c, 0)
                for r in _fallback_search(cat_id, 50):
                    nm = r.get("name")
                    if nm and nm not in seen:
                        seen.add(nm)
                        pool.append(nm)
        except Exception as e:
            print(f"[naiba_gelbooru] gacha pool error({c}): {e}")
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

# ----------------------------- 预览图 -----------------------------
_PREVIEW_URL_CACHE = {}

def _fetch_preview_html(name):
    tag = (name or "").strip()
    if not tag:
        return ""
    params = {"page": "post", "s": "list", "tags": tag}
    url = BASE + "/index.php?" + urllib.parse.urlencode(params)
    html = _fetch_url_gb(url, timeout=15)
    if not html:
        return ""
    try:
        text = html.decode("utf-8", errors="replace")
    except Exception:
        return ""
    m = re.search(r"https?://[^\"']+?(?:thumbnail|samples|images)[^\"']+?\.(?:jpg|jpeg|png|webp)", text)
    return _normalize_url(m.group(0)) if m else ""

def get_random_post_image_url(tag, api_key=None, user_id=None):
    key = "tag:" + tag
    cached = _PREVIEW_URL_CACHE.get(key)
    if cached:
        return cached
    api_key, user_id = _resolve_auth(api_key, user_id)
    if api_key and user_id:
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": 1,
            "limit": 20,
            "pid": random.randint(0, 5),
            "tags": tag,
            "api_key": api_key,
            "user_id": user_id,
        }
        url = BASE + "/index.php?" + urllib.parse.urlencode(params)
        raw = _fetch_url(url)
        if raw:
            try:
                rows = _extract_records(json.loads(raw.decode("utf-8")), "post")
            except Exception:
                rows = []
            if rows:
                it = random.choice(rows)
                preview = _normalize_url(str(it.get("preview_url") or it.get("sample_url") or it.get("file_url") or ""))
                if preview:
                    _PREVIEW_URL_CACHE[key] = preview
                    return preview
    preview = _fetch_preview_html(tag)
    if preview:
        _PREVIEW_URL_CACHE[key] = preview
    return preview

def build_preview_proxy(tag, api_key=None, user_id=None):
    real = get_random_post_image_url(tag, api_key, user_id)
    if not real:
        return None
    data = fetch_image_bytes(real)
    if not data:
        return None
    mime = detect_image_mime(data)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"

# ----------------------------- 节点 -----------------------------
class NaibaGelbooruTagPicker:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
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
            "optional": {
                # —— Gelbooru 认证（最方便：节点上直接粘贴）——
                # 留空 = 匿名模式（autocomplete2 搜名 + HTML 预览 + 当前页扭蛋）；
                # 填了 = 启用分类/Post数/全库随机扭蛋（DAPI）。
                "gelbooru_api_key": ("STRING", {"default": "", "multiline": False, "tooltip": "Gelbooru API Key（可选）。留空则匿名；填写后启用分类/全库扭蛋。也可设环境变量 GELBOORU_API_KEY 或 data/gelbooru_auth.json"}),
                "gelbooru_user_id": ("STRING", {"default": "", "multiline": False, "tooltip": "Gelbooru User ID（可选）。留空则匿名；填写后启用分类/全库扭蛋。也可设环境变量 GELBOORU_USER_ID 或 data/gelbooru_auth.json"}),
                # —— 缓存控制（由前端设置分页管理，节点上隐藏）——
                "cache_enabled": ("BOOLEAN", {"default": True}),
                "cache_max_mb": ("INT", {"default": 500, "min": 100, "max": 20000, "step": 100}),
                "blacklist_data": ("STRING", {"multiline": True, "default": "{}"}),
                "favorites_data": ("STRING", {"multiline": True, "default": "{}"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("ARTIST_NAMES", "CHARACTER_NAMES", "IP_NAMES", "TAG_NAMES", "MERGED_TAGS", "RANDOM_TAGS", "PREVIEW_IMAGES")
    OUTPUT_NODE = True
    FUNCTION = "execute"
    CATEGORY = "naiba-node"

    def execute(self, selection_data, max_images, preview_size, artist_at, gacha_mode, gacha_data,
                gelbooru_api_key="", gelbooru_user_id="",
                cache_enabled=True, cache_max_mb=500,
                blacklist_data="{}", favorites_data="{}",
                prompt=None, extra_pnginfo=None):
        configure_disk_cache(cache_enabled, cache_max_mb)

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
        tag_items = [it for it in selected if _norm_cat(it.get("category")) == "tag"]

        artist_names_list = [
            (("@" + t) if artist_at else t)
            for t in (it.get("tag", "") for it in artist_items)
            if t
        ]
        character_names_list = [it.get("tag", "") for it in character_items if it.get("tag")]
        ip_names_list = [it.get("tag", "") for it in ip_items if it.get("tag")]
        tag_names_list = [it.get("tag", "") for it in tag_items if it.get("tag")]

        artist_names = ", ".join(artist_names_list)
        character_names = ", ".join(character_names_list)
        ip_names = ", ".join(ip_names_list)
        tag_names = ", ".join(tag_names_list)
        merged_tags = ", ".join(artist_names_list + character_names_list + ip_names_list + tag_names_list)

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

        seen = set()
        preview_tag_names = []
        for it in selected:
            name = it.get("tag") if isinstance(it, dict) else it
            if name and name not in seen:
                seen.add(name)
                preview_tag_names.append(name)

        preview_tensors = []
        if preview_tag_names:
            if len(preview_tag_names) > max_images:
                preview_tag_names = preview_tag_names[:max_images]
            ak = gelbooru_api_key if gelbooru_api_key else None
            uid = gelbooru_user_id if gelbooru_user_id else None
            for name in preview_tag_names:
                try:
                    preview_tensors.append(_load_preview_tensor_by_name(name, preview_size, ak, uid))
                except Exception as e:
                    print(f"[naiba_gelbooru] preview fail {name}: {e}")

        if preview_tensors:
            previews = torch.cat(preview_tensors, dim=0)
        else:
            previews = torch.zeros((1, preview_size, preview_size, 3), dtype=torch.float32)

        return (artist_names, character_names, ip_names, tag_names, merged_tags, random_tags, previews)

def _format_gacha_tags(gt, artist_at: bool) -> list:
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

def _load_preview_tensor_by_name(name, size, api_key=None, user_id=None):
    real = get_random_post_image_url(name, api_key, user_id)
    if real:
        data = fetch_image_bytes(real)
        if data:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img = img.resize((size, size))
            arr = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(arr)[None,]
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

def _consume_cache_params(request):
    cache_on = request.query.get("cache", "1") not in ("0", "false", "False", "0")
    try:
        max_size_mb = int(request.query.get("max", "500"))
    except Exception:
        max_size_mb = 500
    configure_disk_cache(cache_on, max_size_mb)

def _cred_params(request):
    ak = (request.query.get("api_key") or "").strip()
    uid = (request.query.get("user_id") or "").strip()
    return (ak or None), (uid or None)

def register_routes():
    if PromptServer is None or web is None:
        return

    @PromptServer.instance.routes.get("/naiba/gelbooru/search")
    async def gelbooru_search(request):
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
        category = {"artist": "artist", "character": "character", "copyright": "copyright", "tag": "tag"}.get(cat, "tag")
        _consume_cache_params(request)
        ak, uid = _cred_params(request)
        res = await _run_in_exec(search_tags, q, category, limit, page, ak, uid)
        return web.json_response(res)

    @PromptServer.instance.routes.get("/naiba/gelbooru/preview")
    async def gelbooru_preview(request):
        tag = request.query.get("tag", "")
        try:
            size = int(request.query.get("size", "220"))
        except Exception:
            size = 220
        _consume_cache_params(request)
        ak, uid = _cred_params(request)
        if not tag:
            return web.json_response({"preview_url": None, "source_url": None})
        data = await _run_in_exec(build_preview_proxy, tag, ak, uid)
        source_url = f"{BASE}/index.php?page=post&s=list&tags={urllib.parse.quote(tag)}"
        return web.json_response({"preview_url": data, "source_url": source_url})

    @PromptServer.instance.routes.get("/naiba/gelbooru/image")
    async def gelbooru_image(request):
        u = request.query.get("u", "")
        if not u:
            return web.Response(status=400, text="missing u")
        # SSRF 白名单在 _fetch_url_gb 内强制仅 gelbooru.com
        data = await _run_in_exec(_fetch_url_gb, u)
        if not data:
            return web.Response(status=502, text="fetch failed")
        mime = detect_image_mime(data)
        return web.Response(body=data, content_type=mime)

    @PromptServer.instance.routes.get("/naiba/gelbooru/gacha_partial")
    async def gelbooru_gacha_partial(request):
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
        ak, uid = _cred_params(request)
        out, shortfall = await _run_in_exec(_gacha_partial_job, a, c, i, blacklist, ak, uid)
        return web.json_response({"tags": out, "shortfall": shortfall})

    @PromptServer.instance.routes.get("/naiba/gelbooru/gacha_random")
    async def gelbooru_gacha_random(request):
        try:
            total = int(request.query.get("total", "9"))
        except Exception:
            total = 9
        blacklist = _parse_json_list(request.query.get("blacklist", "[]"))
        ak, uid = _cred_params(request)
        tags = await _run_in_exec(get_completely_random_tags, total, blacklist, ak, uid)
        return web.json_response({"tags": tags})

    @PromptServer.instance.routes.get("/naiba/gelbooru/status")
    async def gelbooru_status(request):
        """G 站连接状态探测路由（匿名 autocomplete2 即可探测可达性）"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(BASE + "/index.php?page=autocomplete2&term=a&type=tag_query&limit=1", ssl=False) as resp:
                    if resp.status == 200:
                        return web.json_response({"online": True})
                    else:
                        return web.json_response({"online": False})
        except Exception:
            return web.json_response({"online": False})

    @PromptServer.instance.routes.get("/naiba/gelbooru/preload")
    async def gelbooru_preload(request):
        global _PRELOAD_TASK
        action = request.query.get("action", "status")
        _consume_cache_params(request)
        ak, uid = _cred_params(request)
        if action == "start":
            if _PRELOAD_TASK is None or _PRELOAD_TASK.done():
                _PRELOAD_STATUS["running"] = True
                _PRELOAD_STATUS["api_key"] = ak
                _PRELOAD_STATUS["user_id"] = uid
                _PRELOAD_TASK = asyncio.get_event_loop().run_in_executor(None, _preload_worker)
                return web.json_response({"started": True, **_PRELOAD_STATUS})
            else:
                return web.json_response({"started": False, "message": "已在运行", **_PRELOAD_STATUS})
        elif action == "stop":
            _PRELOAD_STATUS["running"] = False
            return web.json_response({"stopped": True, **_PRELOAD_STATUS})
        else:
            return web.json_response(_PRELOAD_STATUS)

    @PromptServer.instance.routes.get("/naiba/gelbooru/cache_status")
    async def gelbooru_cache_status(request):
        _consume_cache_params(request)
        if _DISK_CACHE is None:
            return web.json_response({"enabled": False, "cached_mb": 0, "max_mb": 0, "count": 0})
        cached_mb = _DISK_CACHE.size_mb()
        max_mb = _DISK_CACHE.max_bytes / (1024 * 1024)
        count = 0
        try:
            if _DISK_CACHE.enabled and os.path.exists(_DISK_CACHE.dir):
                count = len([f for f in os.listdir(_DISK_CACHE.dir) if f.endswith(".img") or f.endswith(".json")])
        except Exception:
            pass
        return web.json_response({
            "enabled": True,
            "cached_mb": round(cached_mb, 1),
            "max_mb": round(max_mb, 0),
            "count": count,
            "usage_pct": round(cached_mb / max_mb * 100, 1) if max_mb > 0 else 0,
        })

    @PromptServer.instance.routes.get("/naiba/gelbooru/cache_clear")
    async def gelbooru_cache_clear(request):
        _consume_cache_params(request)
        if _DISK_CACHE is None:
            return web.json_response({"cleared": True, "message": "缓存未启用"})
        try:
            import shutil
            cache_dir = _DISK_CACHE.dir
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
            return web.json_response({"cleared": True, "message": "缓存已清理"})
        except Exception as e:
            return web.json_response({"cleared": False, "message": f"清理失败: {e}"})

    @PromptServer.instance.routes.get("/naiba/gelbooru/hello")
    async def gelbooru_hello(request):
        return web.json_response({"ok": True})

# ----------------------------- 后台预加载 -----------------------------
_PRELOAD_TASK = None
_PRELOAD_STATUS = {"running": False, "progress": 0, "total": 0, "cached_mb": 0, "max_mb": 0, "message": "", "api_key": None, "user_id": None}

def _check_cache_budget():
    if _DISK_CACHE is None:
        return 0, 0, False
    cached = _DISK_CACHE.size_mb()
    max_mb = _DISK_CACHE.max_bytes / (1024 * 1024)
    return cached, max_mb, cached < max_mb * 0.95

def _preload_worker():
    global _PRELOAD_STATUS
    cats = ["artist", "character", "copyright", "tag"]
    max_pages_per_cat = 200
    preview_per_page = 10
    ak = _PRELOAD_STATUS.get("api_key")
    uid = _PRELOAD_STATUS.get("user_id")
    _PRELOAD_STATUS = {"running": True, "progress": 0, "total": 0,
                       "cached_mb": 0, "max_mb": 0, "message": "开始预加载...",
                       "api_key": ak, "user_id": uid}
    try:
        cycle = 0
        while True:
            cycle += 1
            for cat in cats:
                for page in range(1, max_pages_per_cat + 1):
                    if not _PRELOAD_STATUS["running"]:
                        _PRELOAD_STATUS["message"] = "已停止"
                        return
                    cached, max_mb, has_budget = _check_cache_budget()
                    _PRELOAD_STATUS["cached_mb"] = round(cached, 1)
                    _PRELOAD_STATUS["max_mb"] = round(max_mb, 1)
                    _PRELOAD_STATUS["total"] = round(max_mb, 0)
                    _PRELOAD_STATUS["progress"] = round(cached, 0)
                    if not has_budget:
                        _PRELOAD_STATUS["message"] = f"缓存已满 ({cached:.1f}/{max_mb:.1f} MB)"
                        _PRELOAD_STATUS["running"] = False
                        return
                    _PRELOAD_STATUS["message"] = f"[轮{cycle}] {cat} 第{page}页... ({cached:.1f}/{max_mb:.1f} MB)"
                    res = search_tags("", cat, page=page, limit=50, api_key=ak, user_id=uid)
                    items = res.get("items") or []
                    for it in items[:preview_per_page]:
                        if not _PRELOAD_STATUS["running"]:
                            _PRELOAD_STATUS["message"] = "已停止"
                            return
                        cached2, _, has_budget2 = _check_cache_budget()
                        if not has_budget2:
                            _PRELOAD_STATUS["cached_mb"] = round(cached2, 1)
                            _PRELOAD_STATUS["message"] = f"缓存已满 ({cached2:.1f}/{max_mb:.1f} MB)"
                            _PRELOAD_STATUS["running"] = False
                            return
                        tag = it.get("tag")
                        if not tag:
                            continue
                        _PRELOAD_STATUS["message"] = f"[轮{cycle}] 缓存预览: {tag} ({cached2:.1f}/{max_mb:.1f} MB)"
                        try:
                            build_preview_proxy(tag, ak, uid)
                        except Exception:
                            pass
                        time.sleep(0.15)
                    time.sleep(0.3)
            cached, max_mb, has_budget = _check_cache_budget()
            _PRELOAD_STATUS["cached_mb"] = round(cached, 1)
            _PRELOAD_STATUS["max_mb"] = round(max_mb, 1)
            if not has_budget:
                _PRELOAD_STATUS["message"] = f"缓存已满 ({cached:.1f}/{max_mb:.1f} MB)"
                _PRELOAD_STATUS["running"] = False
                return
            _PRELOAD_STATUS["message"] = f"第{cycle}轮完成，继续下一轮... ({cached:.1f}/{max_mb:.1f} MB)"
            time.sleep(1)
    except Exception as e:
        _PRELOAD_STATUS["message"] = f"预加载出错: {e}"
        _PRELOAD_STATUS["running"] = False

def _gacha_partial_job(a, c, i, blacklist, api_key=None, user_id=None):
    cats = [("artist", a), ("character", c), ("copyright", i)]
    out = []
    shortfall = {}
    for cname, cnt in cats:
        tags = get_random_tags_from_category(cname, cnt, blacklist, api_key, user_id)
        actual = len(tags)
        for t in tags:
            out.append({"tag": t, "category": cname})
        if cnt > 0 and actual < cnt:
            shortfall[cname] = {"requested": cnt, "actual": actual, "reason": "blacklist_or_insufficient"}
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
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), fn, *args)

# ----------------------------- 注册 -----------------------------
try:
    register_routes()
except Exception as e:
    print(f"[naiba_gelbooru] register_routes error: {e}")

NODE_CLASS_MAPPINGS = {
    "NaibaGelbooruTagPicker": NaibaGelbooruTagPicker,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaGelbooruTagPicker": "Naiba Gelbooru Tag Picker 🎯",
}
