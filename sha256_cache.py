"""
全局 SHA256 缓存模块（naiba-test 独立实现）

用于持久化本地 LoRA 文件的 SHA256 值，供以下场景复用：
- 批量同步（lora data preview）时为每个 LoRA 计算并缓存 SHA256；
- 预设导出时按名称补全 sha256；
- 上传他人预设做本地匹配（用第一步缓存的 sha256 直接匹配，无需重复计算）。

缓存文件：本模块所在目录下的 naiba_sha256_cache.json
结构：
{
    "version": 1,
    "entries": {
        "<相对LoRA名>": {"sha256": "<hex>", "size": <int>, "mtime": <float>}
    }
}

对外主要接口：
    load_cache() -> dict                     # 返回 {name: sha256}
    get_all() -> dict                        # 同 load_cache
    count() -> int                           # 缓存条目数
    get(name) -> str|None                    # 取单个 sha256
    update_entry(name, sha256, path=None)    # 增量写入单条
    build_sha_index() -> dict                # {sha256_lower: name}
    needs_update(name, path) -> bool         # 文件是否变化（size/mtime）
"""

import os
import json
import threading

# 缓存文件路径（置于节点目录，随项目走）
_CACHE_PATH = os.path.join(os.path.dirname(__file__), "naiba_sha256_cache.json")
_CACHE_VERSION = 1

# 进程内锁 + 内存缓存，避免频繁读盘与并发写冲突
_LOCK = threading.RLock()
_MEM = None  # type: dict | None


def _norm(name):
    """统一 LoRA 名分隔符为正斜杠，兼容 Windows 反斜杠与 folder_paths 风格。"""
    if not name:
        return name
    return str(name).replace("\\", "/")


def _migrate_legacy(loaded):
    """
    把旧/未知结构的缓存尝试迁移为新结构，返回 entries dict；无法识别返回 None。
    兼容以下形态：
      - 新结构 {"version":N, "entries": {name: {sha256,size,mtime}}}
      - 旧结构A {"sha256_map": {name: "sha256"}}
      - 旧结构B 顶层扁平 {name: "sha256"}（无任何已知顶层键时，值为字符串即视为哈希）
    """
    if not isinstance(loaded, dict):
        return None
    known_keys = {"version", "entries", "sha256_map", "updated_at", "created_at", "meta"}

    # 新结构 / 含 entries 的结构
    entries = loaded.get("entries")
    if isinstance(entries, dict):
        out = {}
        for k, v in entries.items():
            sha = (v.get("sha256") or v.get("hash")) if isinstance(v, dict) else v
            if sha:
                entry = {"sha256": str(sha).lower()}
                if isinstance(v, dict):
                    if v.get("size") is not None:
                        entry["size"] = v["size"]
                    if v.get("mtime") is not None:
                        entry["mtime"] = v["mtime"]
                out[_norm(k)] = entry
        return out

    # 旧结构A：独立的 sha256_map
    sha_map = loaded.get("sha256_map")
    if isinstance(sha_map, dict):
        return {_norm(k): {"sha256": str(v).lower()} for k, v in sha_map.items() if v}

    # 旧结构B：顶层扁平 {name: "sha256"}（无任何已知顶层键）
    if loaded and all(k not in loaded for k in known_keys):
        out = {}
        for k, v in loaded.items():
            if isinstance(v, str) and v:
                out[_norm(k)] = {"sha256": v.lower()}
        return out or None

    return None


def _backup_corrupt():
    """缓存不可用时，备份原文件到 .bak，避免数据彻底丢失（不覆盖已有更新的备份）。"""
    try:
        import shutil
        if os.path.exists(_CACHE_PATH):
            bak = _CACHE_PATH + ".bak"
            if (not os.path.exists(bak)) or os.path.getmtime(_CACHE_PATH) > os.path.getmtime(bak):
                shutil.copy2(_CACHE_PATH, bak)
    except Exception:  # noqa: BLE001
        pass


def _load_raw():
    """
    从磁盘加载完整缓存结构（含 meta）。
    - 新结构直接采用并规整；
    - 旧结构尝试迁移并落盘固化；
    - JSON 损坏或完全无法识别则备份原文件后重置为空（绝不崩溃、绝不静默覆盖有效数据）。
    """
    global _MEM
    if _MEM is not None:
        return _MEM
    data = {"version": _CACHE_VERSION, "entries": {}}
    try:
        if os.path.exists(_CACHE_PATH):
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            migrated = _migrate_legacy(loaded)
            if migrated is not None:
                data = {"version": _CACHE_VERSION, "entries": migrated}
                # 迁移后固化新格式，后续读取不再走迁移分支
                try:
                    _save_raw(data)
                except Exception:  # noqa: BLE001
                    pass
            else:
                # 完全无法识别的结构：备份原文件，重置为空（保留原文件可恢复）
                print("[Naiba-SHA256Cache] 缓存格式无法识别，已备份为 .bak 并重置")
                _backup_corrupt()
    except json.JSONDecodeError as e:
        print(f"[Naiba-SHA256Cache] 缓存 JSON 解析失败，已备份为 .bak 并重置: {e}")
        _backup_corrupt()
    except Exception as e:  # noqa: BLE001
        print(f"[Naiba-SHA256Cache] 读取缓存失败，使用空缓存: {e}")

    _MEM = data
    return _MEM


def _save_raw(data):
    """把完整缓存结构写回磁盘（原子写）。"""
    try:
        tmp_path = _CACHE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, _CACHE_PATH)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[Naiba-SHA256Cache] 写入缓存失败: {e}")
        return False


def load_cache():
    """返回 {相对LoRA名: sha256}（仅暴露 sha256，隐藏内部 meta）。"""
    with _LOCK:
        raw = _load_raw()
        return {
            name: (info.get("sha256") if isinstance(info, dict) else info)
            for name, info in raw.get("entries", {}).items()
            if (info.get("sha256") if isinstance(info, dict) else info)
        }


def get_all():
    """load_cache 的别名。"""
    return load_cache()


def count():
    """缓存中已有 sha256 的条目数。"""
    return len(load_cache())


def get(name):
    """取单个 LoRA 的 sha256，不存在返回 None。"""
    name = _norm(name)
    with _LOCK:
        raw = _load_raw()
        info = raw.get("entries", {}).get(name)
        if isinstance(info, dict):
            return info.get("sha256")
        return info or None


def _file_meta(path):
    """返回 (size, mtime)，失败返回 (None, None)。"""
    try:
        st = os.stat(path)
        return st.st_size, st.st_mtime
    except Exception:  # noqa: BLE001
        return None, None


def needs_update(name, path):
    """
    判断某 LoRA 是否需要重新计算 sha256：
    - 缓存中无该条目 -> True
    - 文件 size/mtime 与缓存记录不一致 -> True
    - 一致 -> False
    """
    name = _norm(name)
    with _LOCK:
        raw = _load_raw()
        info = raw.get("entries", {}).get(name)
        if not isinstance(info, dict) or not info.get("sha256"):
            return True
        size, mtime = _file_meta(path)
        if size is None:
            return True
        # mtime 用近似比较，规避浮点/文件系统精度差异
        if info.get("size") != size:
            return True
        cached_mtime = info.get("mtime")
        if cached_mtime is None:
            return True
        return abs(float(cached_mtime) - float(mtime)) > 1.0


def update_entry(name, sha256, path=None):
    """
    增量写入单条 sha256 并持久化。

    Args:
        name: 相对 LoRA 名（folder_paths.get_filename_list 的键）
        sha256: 十六进制 sha256（内部统一转小写）
        path: LoRA 文件完整路径（可选，用于记录 size/mtime 做变化检测）
    """
    if not name or not sha256:
        return False
    name = _norm(name)
    with _LOCK:
        raw = _load_raw()
        entry = {"sha256": str(sha256).lower()}
        if path:
            size, mtime = _file_meta(path)
            if size is not None:
                entry["size"] = size
                entry["mtime"] = mtime
        raw.setdefault("entries", {})[name] = entry
        return _save_raw(raw)


def update_many(items):
    """
    批量写入并一次性持久化（性能更好）。

    Args:
        items: 可迭代的 (name, sha256, path|None) 三元组
    """
    with _LOCK:
        raw = _load_raw()
        entries = raw.setdefault("entries", {})
        changed = False
        for name, sha256, path in items:
            if not name or not sha256:
                continue
            name = _norm(name)
            entry = {"sha256": str(sha256).lower()}
            if path:
                size, mtime = _file_meta(path)
                if size is not None:
                    entry["size"] = size
                    entry["mtime"] = mtime
            entries[name] = entry
            changed = True
        if changed:
            return _save_raw(raw)
        return True


def build_sha_index():
    """返回 {sha256_lower: 相对LoRA名}，供按哈希反查本地文件名。"""
    with _LOCK:
        result = {}
        for name, sha in load_cache().items():
            if sha:
                result[str(sha).lower()] = name
        return result


def remove_entry(name):
    """删除单条缓存（LoRA 被删除时可调用），持久化。"""
    name = _norm(name)
    with _LOCK:
        raw = _load_raw()
        if name in raw.get("entries", {}):
            del raw["entries"][name]
            return _save_raw(raw)
        return True
