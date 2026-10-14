"""
同步排除名单（naiba_sync_excluded.json）

记录「云端根本没有数据、永远无法同步成功」的本地 LoRA：
- 不计入「未同步」统计（前端未同步列表/徽章）
- 批量同步的两种模式（同步未同步的 / 同步全部）都跳过，避免每次全量重试注定失败的条目
- 单个 LoRA 的手动同步不受限制（用户明确点击时允许重试）

独立于 sha256 缓存：排除的是「同步」语义，与本地哈希缓存无关。
"""

import json
import os
import threading

_LIST_PATH = os.path.join(os.path.dirname(__file__), "naiba_sync_excluded.json")
_LOCK = threading.RLock()
_MEM = None  # type: list | None


def _norm(name):
    """统一 LoRA 名分隔符为正斜杠，兼容 Windows 反斜杠与 folder_paths 风格。"""
    if not name:
        return name
    return str(name).replace("\\", "/")


def _load():
    global _MEM
    if _MEM is not None:
        return _MEM
    data = []
    try:
        if os.path.exists(_LIST_PATH):
            with open(_LIST_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                data = [_norm(n) for n in loaded if n]
            elif isinstance(loaded, dict) and isinstance(loaded.get("excluded"), list):
                data = [_norm(n) for n in loaded["excluded"] if n]
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
    """判断某 LoRA 是否在排除名单（大小写/分隔符不敏感）。"""
    if not name:
        return False
    target = _norm(name).casefold()
    return any(_norm(n).casefold() == target for n in _load())


def add_excluded(names):
    """把 LoRA 加入排除名单（去重、规整），返回最终名单。"""
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
            key = normalized.casefold()
            if key not in seen:
                seen.add(key)
                current.append(normalized)
                changed = True
        if changed:
            _save(current)
        return get_excluded()


def remove_excluded(names):
    """把 LoRA 从排除名单移除（大小写/分隔符不敏感），返回最终名单。"""
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
