"""
Preset Sha256 Matcher 节点
包含两个独立 ComfyUI 节点：

1. PresetSha256Aligner（预设对齐）
   输入含 sha256 的预设 JSON（数组），扫描本地 lora 目录建立 sha256→文件路径映射，
   输出在本地找不到对应模型的 sha256 列表（JSON 数组字符串；预设中完全无 sha256 时返回空字符串）。

2. CivitaiSha256InfoReader（C 站按哈希读取）
   输入上一个节点的 sha256 列表（数组串或单个哈希），按哈希并发查询 Civitai，
   下载预览图并转为 IMAGE tensor，输出与 CivitaiInfoReader 同构的 10 路信息，
   并额外输出第 11 路 not_found_sha256（C 站查不到的哈希列表）。

所有核心逻辑（sha256 扫描、异步查询、图片 tensor 加载、多模型合并）均在本文件自行实现，
仅复用项目内工具模块 civitai_utils（CivitaiClient / NSFW_LEVELS），不导入任何节点类。

防封措施：持久化磁盘缓存（正向 30 天 / 负向 404 结果 3 天）+ 进程内内存缓存 +
预览图磁盘缓存 + 并发上限 5 + query_by_hash 自带 429 指数退避。
"""

import os
import json
import time
import asyncio
import hashlib
import threading
import folder_paths
from typing import Optional, Dict, List, Tuple, Any

from .civitai_utils import CivitaiClient, NSFW_LEVELS

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("[NaibaSha256Matcher] Warning: torch not available")

try:
    from PIL import Image
    import numpy as np
    HAS_IMAGE_DEPS = HAS_TORCH
except ImportError:
    HAS_IMAGE_DEPS = False
    print("[NaibaSha256Matcher] Warning: PIL/numpy not available, image output disabled")


# ===================== 常量与缓存 =====================
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PREVIEW_DIR = os.path.join(_THIS_DIR, ".sha256_previews")          # 预览图磁盘缓存
_CACHE_PATH = os.path.join(_THIS_DIR, ".sha256_query_cache.json")  # 查询结果磁盘缓存
os.makedirs(_PREVIEW_DIR, exist_ok=True)

_POSITIVE_TTL = 30 * 24 * 3600   # 查到的模型缓存 30 天
_NEGATIVE_TTL = 3 * 24 * 3600    # 404 等负向结果缓存 3 天（避免重复打扰 C 站）
_CONCURRENCY = 5

_DISK_CACHE_LOCK = threading.Lock()
_QUERY_CACHE: Dict[str, Dict] = {}                                # 进程内内存缓存 sha -> record
_SHA256_CACHE: Dict[str, Tuple[float, int, str]] = {}             # 本地 lora 扫描缓存 realpath -> (mtime, size, sha256)

_SUPPORTED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


# ===================== 通用工具 =====================
def load_image_as_tensor(image_path, target_size=None):
    """加载图片并转换为 ComfyUI IMAGE tensor (BHWC, float32, 0-1)。本文件内重实现，不导入其他节点。"""
    if not HAS_IMAGE_DEPS:
        if target_size:
            return torch.zeros((1, target_size[1], target_size[0], 3), dtype=torch.float32)
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
    try:
        img = Image.open(image_path).convert("RGB")
        if target_size:
            img = img.resize(target_size, Image.Resampling.LANCZOS)
        arr = np.array(img).astype(np.float32) / 255.0
        return torch.from_numpy(arr)[None,]
    except Exception as e:
        print(f"[NaibaSha256Matcher] image load failed: {e}")
        if target_size:
            return torch.zeros((1, target_size[1], target_size[0], 3), dtype=torch.float32)
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)


def run_async(coro):
    """在 ComfyUI 同步节点体内安全运行协程。

    ComfyUI 在异步上下文中执行节点 FUNC（已有 running loop），
    此时不能直接 asyncio.run / run_until_complete，需在独立线程起新 loop 执行。
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures
        result = None
        exc = None

        def _run():
            nonlocal result, exc
            new_loop = asyncio.new_event_loop()
            try:
                result = new_loop.run_until_complete(coro)
            except Exception as e:  # noqa: BLE001
                exc = e
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(_run).result()
        if exc is not None:
            raise exc
        return result

    if loop is None:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


def _load_disk_cache() -> Dict[str, Dict]:
    try:
        if os.path.exists(_CACHE_PATH):
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:  # noqa: BLE001
        print(f"[NaibaSha256Matcher] load disk cache error: {e}")
    return {}


def _save_disk_cache(cache: Dict[str, Dict]):
    try:
        with _DISK_CACHE_LOCK:
            with open(_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        print(f"[NaibaSha256Matcher] save disk cache error: {e}")


def _cache_expired(entry: Dict, now: float) -> bool:
    ttl = _POSITIVE_TTL if entry.get("found") else _NEGATIVE_TTL
    return (now - entry.get("ts", 0)) > ttl


def _compute_sha256(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:  # noqa: BLE001
        print(f"[NaibaSha256Matcher] sha256 error {os.path.basename(path)}: {e}")
        return None


def _build_local_sha_map() -> Dict[str, str]:
    """遍历 lora 目录，建立 sha256(小写) -> 文件真实路径 映射，仅对变更文件重算。"""
    sha_to_path: Dict[str, str] = {}
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
                cached = _SHA256_CACHE.get(key)
                if cached is not None:
                    mtime, size, sha = cached
                    try:
                        st = os.stat(p)
                        if st.st_mtime == mtime and st.st_size == size and sha:
                            sha_to_path.setdefault(sha, p)
                            continue
                    except OSError:
                        pass
                sha = _compute_sha256(p)
                try:
                    st = os.stat(p)
                    _SHA256_CACHE[key] = (st.st_mtime, st.st_size, sha)
                except OSError:
                    pass
                if sha:
                    sha_to_path.setdefault(sha, p)
    return sha_to_path


# ===================== 节点一：预设对齐 =====================
class PresetSha256Aligner:
    """对比预设中的 sha256 与本地 lora 目录，输出缺失模型的 sha256 列表。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "preset_json": ("STRING", {
                    "multiline": True,
                    "tooltip": "含 sha256 的预设 JSON（数组，每项含 sha256 字段）。"
                               "可来自保存后的预设文件；预设中完全无 sha256 时输出空字符串。",
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("missing_sha256", "status", "missing_count")
    FUNCTION = "align"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "预设对齐节点 - 扫描本地 lora 目录，对比预设中记录的 sha256，找出本地缺失的模型。\n"
        "输入：含 sha256 的预设 JSON 数组（保存预设时由预设路由写入 sha256）。\n"
        "输出：缺失模型的 sha256 列表（JSON 数组字符串）；若预设中完全没有 sha256 字段则返回空字符串。"
    )
    SEARCH_ALIASES = ["naiba", "sha256", "预设对齐", "缺失模型", "missing lora", "对齐"]

    def align(self, preset_json: str):
        # 解析预设 JSON
        presets = None
        if preset_json and preset_json.strip():
            try:
                parsed = json.loads(preset_json)
                if isinstance(parsed, list):
                    presets = parsed
                elif isinstance(parsed, dict):
                    presets = [parsed]
            except (json.JSONDecodeError, TypeError):
                pass

        if not presets:
            return ("", "预设为空或不是有效的 JSON 数组", 0)

        # 提取所有 sha256（小写比对），保留 lora 名称
        entries: List[Dict[str, str]] = []
        for item in presets:
            if isinstance(item, dict):
                s = item.get("sha256")
                if isinstance(s, str) and s.strip():
                    s = s.strip().lower()
                    name = item.get("name", "") or ""
                    entries.append({"name": name, "sha256": s})

        if not entries:
            return ("", "预设中无 sha256 记录", 0)

        local_map = _build_local_sha_map()
        missing = [e for e in entries if e["sha256"] not in local_map]

        status = (
            f"扫描本地 lora 目录，共 {len(local_map)} 个模型；"
            f"预设含 {len(entries)} 个 sha256，缺失 {len(missing)} 个"
        )

        if missing:
            # 保持顺序并去重
            seen = set()
            uniq = []
            for e in missing:
                if e["sha256"] not in seen:
                    seen.add(e["sha256"])
                    uniq.append(e)
            return (json.dumps(uniq, ensure_ascii=False), status, len(uniq))

        return ("", status, 0)


# ===================== 节点二：C 站按哈希读取 =====================
class CivitaiSha256InfoReader:
    """按 sha256 到 Civitai 查询模型信息，输出与 CivitaiInfoReader 同构的 10 路 + not_found。"""

    # 空值默认值
    EMPTY_IMAGE = None  # 延迟创建
    EMPTY_MODEL_INFO = "无数据"
    EMPTY_TRIGGER = "无触发词"
    EMPTY_RATING = "无评分数据"
    EMPTY_TAGS = "无标签"
    EMPTY_URL = ""
    EMPTY_JSON = "{}"
    EMPTY_CUSTOM_PROMPT = ""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sha256_list": ("STRING", {
                    "multiline": True,
                    "tooltip": "sha256 列表，支持格式："
                               "① PresetSha256Aligner 的 missing_sha256 输出（推荐，含 lora 名）"
                               "② 纯 JSON 数组 [\"abc\",\"def\"] 或单个哈希"
                               "③ 每行 'lora名|sha256' 文本",
                }),
            },
            "optional": {
                "api_key": ("STRING", {"multiline": False, "default": "", "tooltip": "Civitai API 密钥（可选）"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "STRING", "INT", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("preview_image", "model_info", "trigger_words", "rating_info", "model_tags",
                    "nsfw_level", "preview_url", "civitai_url", "raw_json", "custom_prompt", "not_found_sha256")
    FUNCTION = "read_by_hash"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "C 站按哈希读取节点 - 输入 sha256 列表，按哈希查询 Civitai 模型版本信息。\n"
        "输出前 10 路与 CivitaiInfoReader 完全一致（预览图/模型信息/触发词/评分/标签/NSFW/链接/原始 JSON/自定义提示词），"
        "第 11 路 not_found_sha256 列出在 C 站查不到的哈希。\n"
        "带持久化磁盘缓存与并发限制，避免频繁请求触发封禁。"
    )
    SEARCH_ALIASES = ["naiba", "civitai", "sha256", "哈希查询", "模型信息", "触发词", "模型信息"]

    # ---------- 解析 ----------
    @staticmethod
    def _split_name_sha(text: str):
        """从单条输入解析 (名称, sha256)。
        支持 'lora名|sha256' 文本；无 '|' 时视为纯 sha256，名称为空。"""
        text = (text or "").strip()
        if "|" in text:
            name, sha = text.split("|", 1)
            return name.strip(), sha.strip().lower()
        return "", text.lower()

    @staticmethod
    def _parse_hashes(raw: str):
        """解析 sha256 列表输入，返回 (shas, name_map)。
        支持格式：
          - 纯 JSON 数组 ["abc","def"] 或单条 JSON 字符串
          - JSON 数组对象 [{"name":..., "sha256":...}, ...]   （推荐，带名字）
          - 每行 'lora名|sha256' 文本
        name_map 为 sha(小写) -> lora名（查不到则为空字符串）。"""
        if not raw or not raw.strip():
            return [], {}
        raw = raw.strip()
        shas: List[str] = []
        name_map: Dict[str, str] = {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for x in parsed:
                    if isinstance(x, dict):
                        s = x.get("sha256")
                        if isinstance(s, str) and s.strip():
                            s = s.strip().lower()
                            shas.append(s)
                            n = x.get("name", "")
                            if isinstance(n, str) and n:
                                name_map[s] = n
                    elif isinstance(x, str) and x.strip():
                        n, s = CivitaiSha256InfoReader._split_name_sha(x)
                        if s:
                            shas.append(s)
                            if n:
                                name_map[s] = n
            elif isinstance(parsed, str) and parsed.strip():
                n, s = CivitaiSha256InfoReader._split_name_sha(parsed)
                if s:
                    shas.append(s)
                    if n:
                        name_map[s] = n
        except (json.JSONDecodeError, TypeError):
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                n, s = CivitaiSha256InfoReader._split_name_sha(line)
                if s:
                    shas.append(s)
                    if n:
                        name_map[s] = n

        seen = set()
        uniq = []
        for s in shas:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        return uniq, name_map

    # ---------- 主入口 ----------
    def read_by_hash(self, sha256_list: str, api_key: str = ""):
        if CivitaiSha256InfoReader.EMPTY_IMAGE is None:
            if HAS_TORCH:
                CivitaiSha256InfoReader.EMPTY_IMAGE = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            else:
                CivitaiSha256InfoReader.EMPTY_IMAGE = None

        hashes, name_map = self._parse_hashes(sha256_list)
        if not hashes:
            return self._empty_output()

        max_nsfw = NSFW_LEVELS["Blocked"]
        try:
            records = run_async(self._gather(hashes, (api_key or "").strip() or None, max_nsfw))
        except Exception as e:  # noqa: BLE001
            print(f"[NaibaSha256Matcher] query failed: {e}")
            records = {
                s: {
                    "sha": s, "version_data": None, "error": str(e),
                    "found": False, "preview_path": None, "preview_url": None,
                }
                for s in hashes
            }

        return self._build_outputs(records, hashes, name_map)

    # ---------- 异步查询 + 下载 ----------
    async def _gather(self, hashes, api_key, max_nsfw):
        now = time.time()
        cache = _load_disk_cache()

        # 合并进程内内存缓存
        for s in hashes:
            if s in _QUERY_CACHE:
                rec = _QUERY_CACHE[s]
                cache.setdefault(s, {
                    "found": rec["found"],
                    "data": rec.get("version_data"),
                    "error": rec.get("error"),
                    "ts": now,
                })

        client = CivitaiClient(api_key=api_key)
        sem = asyncio.Semaphore(_CONCURRENCY)
        records: Dict[str, Dict] = {}

        try:
            async def query_one(sha):
                entry = cache.get(sha)
                if entry and not _cache_expired(entry, now):
                    rec = {
                        "sha": sha,
                        "version_data": entry["data"] if entry["found"] else None,
                        "error": entry.get("error"),
                        "found": bool(entry["found"]),
                        "preview_path": None,
                        "preview_url": None,
                    }
                    records[sha] = rec
                    _QUERY_CACHE[sha] = rec
                    return

                async with sem:
                    data, err = await client.query_by_hash(sha)
                found = data is not None
                rec = {
                    "sha": sha,
                    "version_data": data,
                    "error": err,
                    "found": found,
                    "preview_path": None,
                    "preview_url": None,
                }
                records[sha] = rec
                _QUERY_CACHE[sha] = rec
                cache[sha] = {"found": found, "data": data, "error": err, "ts": now}

            await asyncio.gather(*[query_one(s) for s in hashes])

            async def download_one(sha):
                rec = records[sha]
                if not rec["found"] or not rec["version_data"]:
                    return
                images = rec["version_data"].get("images", []) or []
                sel = CivitaiClient.select_preview_image(images, max_nsfw)
                if not sel:
                    return
                url = sel.get("url")
                if not url:
                    return
                rec["preview_url"] = url
                ext = CivitaiClient.get_preview_extension(url)
                path = os.path.join(_PREVIEW_DIR, f"{sha}{ext}")
                if os.path.exists(path):
                    rec["preview_path"] = path
                    return
                async with sem:
                    ok = await client.download_image(url, path)
                if ok:
                    rec["preview_path"] = path

            await asyncio.gather(*[download_one(s) for s in hashes])
        finally:
            await client.close()
            _save_disk_cache(cache)

        return records

    # ---------- 组装输出 ----------
    def _build_outputs(self, records, hashes, name_map=None):
        found_items = []  # (idx, rec, version_data)
        not_found = []
        for idx, sha in enumerate(hashes, start=1):
            rec = records.get(sha)
            if rec and rec["found"] and rec.get("version_data"):
                found_items.append((idx, rec, rec["version_data"]))
            else:
                not_found.append(sha)

        is_multi = len(hashes) > 1

        # 1) 预览图：统一 resize 到首张有效图尺寸，缺失项用占位图
        raw_paths = []
        for sha in hashes:
            rec = records.get(sha)
            if rec and rec.get("preview_path") and os.path.exists(rec["preview_path"]):
                raw_paths.append(rec["preview_path"])
            else:
                raw_paths.append(None)

        target_size = (512, 512)
        for p in raw_paths:
            if p and os.path.exists(p):
                try:
                    with Image.open(p) as im:
                        target_size = im.size
                        break
                except Exception:  # noqa: BLE001
                    pass

        tensors = []
        for p in raw_paths:
            if p and os.path.exists(p) and os.path.splitext(p)[1].lower() in _SUPPORTED_IMAGE_EXT:
                tensors.append(load_image_as_tensor(p, target_size))
            else:
                tensors.append(self._blank(target_size))

        if tensors:
            preview_batch = torch.cat(tensors, dim=0)
        else:
            preview_batch = (CivitaiSha256InfoReader.EMPTY_IMAGE
                             if CivitaiSha256InfoReader.EMPTY_IMAGE is not None
                             else torch.zeros((1, 64, 64, 3)))

        # 2) 文本字段合并
        all_model_info = []
        all_triggers = []
        all_rating = []
        all_tags = []
        max_nsfw_level = 0
        all_preview_urls = []
        all_civitai_urls = []
        all_raw = []

        for (idx, rec, vd) in found_items:
            single = self._format_single(vd, idx, is_multi, rec.get("preview_url"))
            all_model_info.append(single["info"])
            all_triggers.extend(single["triggers"])
            all_rating.append(single["rating"])
            all_tags.extend(single["tags"])
            if single["nsfw"] > max_nsfw_level:
                max_nsfw_level = single["nsfw"]
            if single["preview_url"]:
                all_preview_urls.append(f"[{idx}] {single['preview_url']}" if is_multi else single["preview_url"])
            if single["civitai_url"]:
                all_civitai_urls.append(f"[{idx}] {single['civitai_url']}" if is_multi else single["civitai_url"])
            all_raw.append(vd)

        model_info = "\n\n".join(all_model_info) if all_model_info else self.EMPTY_MODEL_INFO

        unique_triggers = list(dict.fromkeys(all_triggers))
        trigger_str = ", ".join(unique_triggers) if unique_triggers else self.EMPTY_TRIGGER

        rating_info = "\n".join(all_rating) if all_rating else self.EMPTY_RATING

        unique_tags = list(dict.fromkeys(all_tags))
        tags_str = ", ".join(unique_tags) if unique_tags else self.EMPTY_TAGS

        preview_url = "\n".join(all_preview_urls) if all_preview_urls else self.EMPTY_URL
        civitai_url = "\n".join(all_civitai_urls) if all_civitai_urls else self.EMPTY_URL

        raw_json = ("[" + ",\n".join(
            json.dumps(v, ensure_ascii=False, indent=2) for v in all_raw
        ) + "]") if all_raw else self.EMPTY_JSON

        # 反查本地 lora 目录，补全缺失项的名称（名称未知时）
        if name_map is None:
            name_map = {}
        if not_found and any(s not in name_map for s in not_found):
            local_map = _build_local_sha_map()  # sha(小写) -> 文件路径
            for s in not_found:
                if s not in name_map:
                    p = local_map.get(s)
                    if p:
                        name_map[s] = os.path.basename(p)

        not_found_items = [{"name": name_map.get(s, ""), "sha256": s} for s in not_found]
        not_found_str = json.dumps(not_found_items, ensure_ascii=False) if not_found_items else ""

        return (preview_batch, model_info, trigger_str, rating_info, tags_str,
                max_nsfw_level, preview_url, civitai_url, raw_json,
                self.EMPTY_CUSTOM_PROMPT, not_found_str)

    @staticmethod
    def _format_single(vd: Dict, idx: int, is_multi: bool, preview_url: Optional[str]) -> Dict:
        """从 model version 对象提取单模型展示字段（参照 sync_lora_from_civitai 的字段映射）。"""
        model = vd.get("model", {}) or {}
        model_name = model.get("name") or vd.get("name") or "未知"
        version_name = vd.get("name") or ""
        base_model = vd.get("baseModel") or "未知"
        model_type = model.get("type") or "未知"
        description = vd.get("description")
        if description in (None, "null"):
            description = ""

        parts = []
        if is_multi:
            parts.append(f"[{idx}] {model_name}")
        else:
            parts.append(f"模型名称: {model_name}")
        if version_name:
            parts.append(f"版本: {version_name}")
        parts.append(f"基础模型: {base_model}")
        parts.append(f"类型: {model_type}")
        if description:
            clean = CivitaiSha256InfoReader._strip_html(description)
            if clean:
                parts.append(f"描述: {clean}")
        info = "\n".join(parts)

        tw = vd.get("trainedWords") or []
        triggers = [str(w) for w in tw if w]

        rating = vd.get("rating", 0) or 0
        rating_count = vd.get("ratingCount", 0) or 0
        download_count = vd.get("downloadCount", 0) or 0
        rparts = []
        if rating:
            rparts.append(f"评分: {rating:.1f} ({rating_count}次评价)")
        else:
            rparts.append("评分: 暂无")
        rparts.append(f"下载量: {download_count}")
        rating_str = (f"[{idx}] {model_name}: " if is_multi else "") + ", ".join(rparts)

        tags = model.get("tags") or []
        tag_list = [str(t) for t in tags if t]

        nsfw = vd.get("nsfwLevel", 0) or 0

        model_id = vd.get("modelId")
        civitai_url = f"https://civitai.com/models/{model_id}" if model_id else ""

        return {
            "info": info,
            "triggers": triggers,
            "rating": rating_str,
            "tags": tag_list,
            "nsfw": nsfw,
            "preview_url": preview_url,
            "civitai_url": civitai_url,
        }

    @staticmethod
    def _strip_html(html_str):
        """简单的 HTML 标签清理。"""
        import re
        if not html_str:
            return ""
        clean = re.sub(r'<[^>]+>', '', html_str)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if len(clean) > 500:
            clean = clean[:500] + "..."
        return clean

    @staticmethod
    def _blank(size):
        return torch.zeros((1, size[1], size[0], 3), dtype=torch.float32)

    def _empty_output(self):
        img = (CivitaiSha256InfoReader.EMPTY_IMAGE
               if CivitaiSha256InfoReader.EMPTY_IMAGE is not None
               else (torch.zeros((1, 64, 64, 3)) if HAS_TORCH else None))
        return (img, self.EMPTY_MODEL_INFO, self.EMPTY_TRIGGER, self.EMPTY_RATING,
                self.EMPTY_TAGS, 0, self.EMPTY_URL, self.EMPTY_URL,
                self.EMPTY_JSON, self.EMPTY_CUSTOM_PROMPT, "")


# 节点映射
NODE_CLASS_MAPPINGS = {
    "PresetSha256Aligner": PresetSha256Aligner,
    "CivitaiSha256InfoReader": CivitaiSha256InfoReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PresetSha256Aligner": "Preset Sha256 Aligner (预设对齐)",
    "CivitaiSha256InfoReader": "Civitai Sha256 Info Reader (哈希读取)",
}
