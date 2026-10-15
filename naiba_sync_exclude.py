"""
同步排除名单（naiba_sync_excluded.json）

记录「云端根本没有数据、永远无法同步成功」的本地 LoRA：
- 不计入「未同步」统计（前端未同步列表/徽章）
- 批量同步的两种模式（同步未同步的 / 同步全部）都跳过，避免每次全量重试注定失败的条目
- 单个 LoRA 的手动同步不受限制（用户明确点击时允许重试）

支持目录条目：以 "/" 结尾的条目（如 "anima/edit/"）表示排除整个目录，
该目录（含各级子目录）下的所有 LoRA 都按排除处理。文件条目精确匹配。

独立于 sha256 缓存：排除的是「同步」语义，与本地哈希缓存无关。
"""

import json
import os
import threading

_LIST_PATH = os.path.join(os.path.dirname(__file__), "naiba_sync_excluded.json")
_LOCK = threading.RLock()
_MEM = None  # type: list | None


def _norm(name):
    """统一 LoRA 名分隔符为正斜杠，兼容 Windows 反斜杠与 folder_paths 风格。

    同时去掉前导斜杠（前端目录树会传 "/anima/edit" 这类带根斜杠的形态）
    与尾部斜杠（目录条目由 add_excluded 统一补 "/"，避免 "dir//" 这类双斜杠条目）。
    """
    if not name:
        return name
    return str(name).replace("\\", "/").strip("/")


def _is_dir_entry(name):
    """目录条目：以 / 结尾（add_excluded 保证存储形态恒为 "dir/"）。"""
    return bool(name) and str(name).endswith("/")


def _dir_entry_prefix(entry):
    """目录条目的匹配前缀："dir/" 形态（无前导斜杠、有尾斜杠）。"""
    return _norm(entry) if _norm(entry).endswith("/") else f"{_norm(entry)}/"


def _load():
    global _MEM
    if _MEM is not None:
        return _MEM
    data = []
    try:
        if os.path.exists(_LIST_PATH):
            with open(_LIST_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            raw_items = []
            if isinstance(loaded, list):
                raw_items = loaded
            elif isinstance(loaded, dict) and isinstance(loaded.get("excluded"), list):
                raw_items = loaded["excluded"]
            # 目录语义以原始输入的尾斜杠判定：_norm 会 strip("/")，先判后规整并补回
            for n in raw_items:
                if not n:
                    continue
                normalized = _norm(n)
                if str(n).replace("\\", "/").endswith("/") and normalized and not normalized.endswith("/"):
                    normalized = f"{normalized}/"
                data.append(normalized)
    except json.JSONDecodeError as e:
        print(f"[Naiba-SyncExclude] 名单 JSON 解析失败，使用空名单: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"[Naiba-SyncExclude] 读取名单失败，使用空名单: {e}")
    _MEM = data
    return _MEM


def _save(names):
    """原子写盘。"""
    global _MEM
    try:
        tmp_path = _LIST_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(names, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, _LIST_PATH)
        _MEM = names
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[Naiba-SyncExclude] 写入名单失败: {e}")
        return False


def get_excluded():
    """返回排除名单（正斜杠规整后的列表副本）。"""
    with _LOCK:
        return list(_load())


def is_excluded(name):
    """判断某 LoRA 是否被排除（大小写/分隔符不敏感）。

    文件条目精确匹配；目录条目（"/" 结尾）按前缀匹配，覆盖各级子目录。
    """
    if not name:
        return False
    target = _norm(name).casefold()
    with _LOCK:
        for entry in _load():
            entry_norm = _norm(entry).casefold()
            if _is_dir_entry(entry):
                if target.startswith(_dir_entry_prefix(entry).casefold()):
                    return True
            elif entry_norm == target:
                return True
    return False


def add_excluded(names):
    """把 LoRA 或目录加入排除名单（去重、规整），返回最终名单。

    目录条目自动补尾部 "/"（调用方可传 "dir"、"/dir"、"dir/" 任意形态）。
    """
    if isinstance(names, str):
        names = [names]
    with _LOCK:
        current = _load()
        seen = {_norm(n).casefold() for n in current}
        changed = False
        for n in names or []:
            if not n:
                continue
            normalized = _norm(n)
            # 目录语义（原始输入以 / 结尾）统一规整成 "dir/" 存储
            if str(n).replace("\\", "/").endswith("/") and not normalized.endswith("/"):
                normalized = f"{normalized}/"
            key = normalized.casefold()
            if key not in seen:
                seen.add(key)
                current.append(normalized)
                changed = True
        if changed:
            _save(current)
        return get_excluded()


def remove_excluded(names):
    """把 LoRA 或目录从排除名单移除（大小写/分隔符不敏感），返回最终名单。

    移除目录条目只删除该目录条目本身，不展开删除其下的文件条目。
    """
    if isinstance(names, str):
        names = [names]
    drop = {_norm(n).casefold() for n in names or [] if n}
    if not drop:
        return get_excluded()
    with _LOCK:
        current = _load()
        kept = [n for n in current if _norm(n).casefold() not in drop]
        if len(kept) != len(current):
            _save(kept)
        return get_excluded()
