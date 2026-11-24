"""LoRA 预设分类元数据。

分类与预设 JSON 解耦，统一存放在 <presets_dir>/.meta/categories.json：
- categories: 分类名列表（保持创建顺序）
- assignments: {预设名: [分类名, ...]}，一个预设可属于多个分类；
  未出现在 assignments 中的预设即「未分类」，因此「未分类」不是真实分类。

文件读写均为同步小文件操作，损坏时备份后按空分类继续，避免静默覆盖。
"""

import json
import os
import time

META_DIRNAME = ".meta"
STORE_FILENAME = "categories.json"
STORE_VERSION = 1
UNCATEGORIZED_LABEL = "未分类"
MAX_CATEGORY_NAME_LENGTH = 32


def _store_path(presets_dir):
    return os.path.join(presets_dir, META_DIRNAME, STORE_FILENAME)


def _empty_store():
    return {"version": STORE_VERSION, "categories": [], "assignments": {}}


def normalize_category_name(value):
    """折叠空白并校验分类名；无效时返回 None。"""
    text = " ".join(str(value or "").split())
    if not text or len(text) > MAX_CATEGORY_NAME_LENGTH:
        return None
    if text == UNCATEGORIZED_LABEL:
        return None
    return text


def _sanitize_store(raw):
    store = _empty_store()
    if not isinstance(raw, dict):
        return store

    categories = []
    seen = set()
    for item in raw.get("categories", []) or []:
        name = normalize_category_name(item)
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        categories.append(name)
    store["categories"] = categories

    valid = {name.casefold(): name for name in categories}
    assignments = {}
    raw_assignments = raw.get("assignments", {})
    if isinstance(raw_assignments, dict):
        for preset_name, values in raw_assignments.items():
            if not isinstance(preset_name, str) or not preset_name.strip():
                continue
            if not isinstance(values, list):
                continue
            normalized = []
            for value in values:
                name = normalize_category_name(value)
                canonical = valid.get(name.casefold()) if name else None
                if canonical and canonical not in normalized:
                    normalized.append(canonical)
            if normalized:
                assignments[preset_name] = normalized
    store["assignments"] = assignments
    return store


def load_store(presets_dir):
    """读取分类元数据；文件不存在返回空结构，损坏时备份并返回空结构。"""
    path = _store_path(presets_dir)
    if not os.path.exists(path):
        return _empty_store()
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        print(
            f"[Naiba] 读取预设分类失败 {path}: {type(e).__name__}: {e}"
        )
        backup_path = f"{path}.corrupt-{int(time.time())}"
        try:
            os.replace(path, backup_path)
            print(f"[Naiba] 已备份损坏的分类元数据到 {backup_path}，本次按空分类处理")
        except OSError as backup_error:
            print(f"[Naiba] 备份损坏的分类元数据失败 {path}: {backup_error}")
        return _empty_store()
    return _sanitize_store(raw)


def save_store(presets_dir, store):
    """原子写入分类元数据（同目录临时文件 + os.replace）。"""
    meta_dir = os.path.join(presets_dir, META_DIRNAME)
    os.makedirs(meta_dir, exist_ok=True)
    path = _store_path(presets_dir)
    temp_path = f"{path}.tmp-{os.getpid()}-{time.time_ns()}"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, path)


def _require_category(store, name):
    target = normalize_category_name(name)
    if not target:
        raise ValueError(
            "分类名称无效（不能为空、超过 32 字符或使用保留名「未分类」）"
        )
    for category in store["categories"]:
        if category.casefold() == target.casefold():
            return category
    raise ValueError(f"分类不存在: {target}")


def create_category(presets_dir, name):
    store = load_store(presets_dir)
    category = normalize_category_name(name)
    if not category:
        raise ValueError(
            "分类名称无效（不能为空、超过 32 字符或使用保留名「未分类」）"
        )
    if any(c.casefold() == category.casefold() for c in store["categories"]):
        raise ValueError(f"分类已存在: {category}")
    store["categories"].append(category)
    save_store(presets_dir, store)
    return store


def rename_category(presets_dir, old_name, new_name):
    store = load_store(presets_dir)
    old_category = _require_category(store, old_name)
    new_category = normalize_category_name(new_name)
    if not new_category:
        raise ValueError(
            "分类名称无效（不能为空、超过 32 字符或使用保留名「未分类」）"
        )
    for category in store["categories"]:
        if category.casefold() == new_category.casefold() and category != old_category:
            raise ValueError(f"分类已存在: {new_category}")

    index = store["categories"].index(old_category)
    store["categories"][index] = new_category
    for preset_name, categories in store["assignments"].items():
        store["assignments"][preset_name] = [
            new_category if item == old_category else item for item in categories
        ]
    save_store(presets_dir, store)
    return store


def delete_category(presets_dir, name):
    """删除分类：仅从各预设的分类列表中移除该项，预设仍保留其它分类；
    分类列表因此变空的预设不作存储，自动归为「未分类」。"""
    store = load_store(presets_dir)
    category = _require_category(store, name)
    store["categories"].remove(category)

    remaining = {}
    for preset_name, categories in store["assignments"].items():
        kept = [item for item in categories if item != category]
        if kept:
            remaining[preset_name] = kept
    store["assignments"] = remaining
    save_store(presets_dir, store)
    return store


def set_preset_categories(presets_dir, preset_name, categories):
    """覆盖某个预设的分类集合；未知分类与保留名会被忽略。

    返回最终生效的分类列表；空列表表示归入「未分类」。
    """
    store = load_store(presets_dir)
    valid = {item.casefold(): item for item in store["categories"]}
    normalized = []
    dropped = []
    for value in categories or []:
        name = normalize_category_name(value)
        canonical = valid.get(name.casefold()) if name else None
        if canonical:
            if canonical not in normalized:
                normalized.append(canonical)
        else:
            dropped.append(str(value))
    if dropped:
        print(
            f"[Naiba] 预设「{preset_name}」包含未知/非法分类已忽略: {dropped}"
        )

    if normalized:
        store["assignments"][preset_name] = normalized
    else:
        store["assignments"].pop(preset_name, None)
    save_store(presets_dir, store)
    return normalized


def remove_preset(presets_dir, preset_name):
    """删除预设时同步清理其分类分配；返回是否有变更。"""
    store = load_store(presets_dir)
    if preset_name not in store["assignments"]:
        return False
    del store["assignments"][preset_name]
    save_store(presets_dir, store)
    return True


def rename_preset(presets_dir, old_name, new_name):
    """重命名预设时迁移其分类分配；返回是否有变更。"""
    store = load_store(presets_dir)
    if old_name not in store["assignments"] or old_name == new_name:
        return False
    moved = store["assignments"].pop(old_name)
    existing = store["assignments"].get(new_name, [])
    store["assignments"][new_name] = existing + [
        category for category in moved if category not in existing
    ]
    save_store(presets_dir, store)
    return True


def get_preset_categories(store, preset_name):
    return list(store.get("assignments", {}).get(preset_name, []))