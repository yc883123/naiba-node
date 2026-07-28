"""LoRA 预设路径匹配逻辑，不读取模型文件内容。"""

import re


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_lora_name(name):
    return str(name or "").replace("\\", "/").lstrip("/")


def normalize_sha256(value):
    sha = str(value or "").strip().lower()
    return sha if _SHA256_RE.fullmatch(sha) else None


def classify_preset_paths(items, candidate_index, candidate_state):
    """按缓存反查结果分类路径；candidate_state 只能做轻量文件元信息检查。"""
    relocations = []
    ambiguous = []
    stale_cache = []
    local_candidates = {}
    summary = {
        "total": len(items),
        "same": 0,
        "relocations": 0,
        "ambiguous": 0,
        "missing": 0,
        "stale_cache": 0,
        "no_sha256": 0,
    }

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            summary["no_sha256"] += 1
            continue

        original_name = item.get("name", "") or ""
        original_norm = normalize_lora_name(original_name)
        sha = normalize_sha256(item.get("sha256"))
        if not sha:
            summary["no_sha256"] += 1
            continue

        cached_names = []
        seen_names = set()
        for cached_name in candidate_index.get(sha, []):
            normalized = normalize_lora_name(cached_name)
            key = normalized.casefold()
            if normalized and key not in seen_names:
                seen_names.add(key)
                cached_names.append(normalized)

        current_names = []
        for cached_name in cached_names:
            state = candidate_state(cached_name)
            if state == "current":
                current_names.append(cached_name)

        if not current_names:
            if cached_names:
                summary["stale_cache"] += 1
                stale_cache.append({
                    "preset_index": index,
                    "name": original_name,
                    "sha256": sha,
                    "enabled": item.get("enabled", True),
                    "cached_names": cached_names,
                })
            else:
                summary["missing"] += 1
            continue

        local_candidates[index] = list(current_names)
        original_match = next(
            (name for name in current_names if name.casefold() == original_norm.casefold()),
            None,
        )
        if original_match is not None:
            summary["same"] += 1
            local_candidates[index] = [original_match]
            continue

        if len(current_names) == 1:
            local_name = current_names[0]
            summary["relocations"] += 1
            relocations.append({
                "preset_index": index,
                "original_name": original_name,
                "local_name": local_name,
                "sha256": sha,
                "enabled": item.get("enabled", True),
            })
            continue

        summary["ambiguous"] += 1
        ambiguous.append({
            "preset_index": index,
            "original_name": original_name,
            "sha256": sha,
            "enabled": item.get("enabled", True),
            "candidates": current_names,
        })

    return {
        "relocations": relocations,
        "ambiguous": ambiguous,
        "stale_cache": stale_cache,
        "path_summary": summary,
        "local_candidates": local_candidates,
    }


def resolve_preset_paths(items, candidate_index, candidate_state, path_exists):
    """按当前有效的唯一 SHA256 候选重定位预设，不采用失效历史路径。"""
    if not isinstance(items, list):
        return items

    report = classify_preset_paths(items, candidate_index, candidate_state)
    replacements = {
        item["preset_index"]: item["local_name"]
        for item in report["relocations"]
    }
    resolved = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            resolved.append(item)
            continue

        original_name = item.get("name", "") or ""
        normalized_name = normalize_lora_name(original_name)
        if index in replacements:
            new_name = replacements[index]
        elif normalized_name and path_exists(normalized_name):
            new_name = normalized_name
        elif original_name and path_exists(original_name):
            new_name = original_name
        else:
            new_name = original_name

        new_item = dict(item)
        new_item["name"] = new_name
        resolved.append(new_item)
    return resolved
