"""
Preset Folder Aligner 节点（合并节点）
将「读取预设文件」与「预设对齐（本地缺失模型扫描）」合并到单次执行，输出 6 路：

  preset_json / lora_names / read_status   —— 来自读取预设
  missing_sha256 / align_status / missing_count —— 来自对齐扫描

所有核心逻辑（预设读取、sha256 解析、本地 sha256 映射扫描）均在本文件内自行实现，
符合项目「节点逻辑必须在本文件完成」的约束：不导入任何节点类，仅复用 ComfyUI 基础库
（folder_paths / hashlib / json / os）与本文件内复制的模块级工具函数。
"""

import os
import json
import hashlib
import folder_paths


# 预设存储目录（与 Multi LoRA Loader 共享）
PRESETS_DIR = os.path.join(os.path.dirname(__file__), "presets")
os.makedirs(PRESETS_DIR, exist_ok=True)

# 进程内 sha256 缓存：真实路径 -> (mtime, size, sha256)，仅文件变更时重算
_SHA256_CACHE: dict = {}


def _compute_sha256(path: str) -> "str | None":
    """读取文件计算 sha256（分块，避免一次性读入大文件）。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:  # noqa: BLE001
        print(f"[PresetFolderAligner] sha256 error {os.path.basename(path)}: {e}")
        return None


def resolve_lora_sha256(name: str) -> str:
    """根据 lora 文件名在本地 loras 目录解析路径并计算 sha256；找不到返回空串。"""
    if not name:
        return ""
    name = name.lstrip("/")
    try:
        path = folder_paths.get_full_path("loras", name)
    except Exception:  # noqa: BLE001
        path = None
    if not path or not os.path.isfile(path):
        return ""
    key = os.path.realpath(path)
    cached = _SHA256_CACHE.get(key)
    if cached is not None:
        mtime, size, sha = cached
        try:
            st = os.stat(path)
            if st.st_mtime == mtime and st.st_size == size and sha:
                return sha
        except OSError:
            pass
    sha = _compute_sha256(path)
    try:
        st = os.stat(path)
        _SHA256_CACHE[key] = (st.st_mtime, st.st_size, sha)
    except OSError:
        pass
    return sha or ""


def list_preset_files() -> "list[str]":
    """列出 presets/ 目录下的预设文件名（不含 .json 后缀），按名称排序。"""
    try:
        return sorted(f[:-5] for f in os.listdir(PRESETS_DIR) if f.endswith(".json"))
    except Exception as e:  # noqa: BLE001
        print(f"[PresetFolderAligner] 列出预设失败: {e}")
        return []


def _safe_preset_path(preset_name: str):
    """校验预设名安全性，返回合法的文件路径；非法返回 None。"""
    if not preset_name:
        return None
    name = preset_name.strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    if not name.endswith(".json"):
        name = name + ".json"
    file_path = os.path.realpath(os.path.join(PRESETS_DIR, name))
    presets_real = os.path.realpath(PRESETS_DIR)
    if not file_path.startswith(presets_real + os.sep) and file_path != presets_real:
        return None
    return file_path


def _build_local_sha_map() -> "dict[str, str]":
    """遍历 lora 目录，建立 sha256(小写) -> 文件真实路径 映射，仅对变更文件重算。"""
    sha_to_path: "dict[str, str]" = {}
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


class PresetFolderAligner:
    """
    读预设 + 对齐合并节点。

    用法：
    1. preset_name 下拉选择 presets/ 中的预设（点节点上的「刷新预设列表」可重新扫描）
    2. skip_disabled 为 True 时，输出的预设 JSON / 列表仅包含启用项
    3. 一次执行同时输出读取结果与本地缺失模型扫描结果
    """

    @classmethod
    def INPUT_TYPES(cls):
        files = list_preset_files()
        if not files:
            files = ["(无预设文件)"]
        return {
            "required": {
                "preset_name": (files, {
                    "tooltip": "选择 presets 文件夹中的预设；点节点上的『刷新预设列表』按钮可重新扫描"
                }),
            },
            "optional": {
                "skip_disabled": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "为 True 时，输出的预设 JSON / 列表仅包含启用项",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("preset_json", "lora_names", "read_status", "missing_sha256", "align_status", "missing_count")
    FUNCTION = "read_and_align"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "读预设 + 对齐合并节点：直接从 presets/ 文件夹读取预设文件并扫描本地缺失模型，一次执行输出 6 路。\n"
        "preset_json 每项含 name/strength_model/strength_clip/enabled/sha256，"
        "lora_names 为启用项列表（受 skip_disabled 影响）。\n"
        "missing_sha256 列出本地 lora 目录中找不到对应模型的 sha256；align_status 给出扫描统计。"
    )
    SEARCH_ALIASES = [
        "naiba", "preset folder aligner", "预设对齐", "读预设",
        "预设文件夹", "缺失模型", "preset align"
    ]

    def read_and_align(self, preset_name, skip_disabled=False):
        """读取预设并扫描本地缺失模型，返回 6 路输出。"""

        # ---------- 阶段一：读取预设 ----------
        if not preset_name or preset_name == "(无预设文件)":
            return self._empty_output("未选择预设或 presets 文件夹为空")

        file_path = _safe_preset_path(preset_name)
        if file_path is None:
            return self._empty_output(f"非法的预设名: {preset_name}")
        if not os.path.isfile(file_path):
            return self._empty_output(f"预设文件不存在: {preset_name}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001
            return self._empty_output(f"读取预设失败 {preset_name}: {e}")

        if not isinstance(data, list):
            return self._empty_output(f"预设格式错误（应为数组）: {preset_name}")

        preset_configs = []
        read_missing = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            if not name:
                continue
            sha = item.get("sha256") or ""
            if not sha:
                sha = resolve_lora_sha256(name)
                if not sha:
                    read_missing.append(name)
            cfg = {
                "name": name,
                "strength_model": float(item.get("strength_model", 1.0)),
                "strength_clip": float(item.get("strength_clip", 1.0)),
                "enabled": bool(item.get("enabled", True)),
                "sha256": sha,
            }
            if skip_disabled and not cfg["enabled"]:
                continue
            preset_configs.append(cfg)

        if not preset_configs:
            return self._empty_output(f"预设中未找到有效 LoRA 条目: {preset_name}")

        preset_json = json.dumps(preset_configs, ensure_ascii=False, indent=2)
        enabled_configs = [c for c in preset_configs if c["enabled"]]
        lora_names = json.dumps(
            [c["name"] for c in enabled_configs],
            ensure_ascii=False,
        )

        total = len(preset_configs)
        enabled_count = len(enabled_configs)
        read_status = (
            f"从 [{preset_name}] 读取到 {total} 个 LoRA"
            f"（{enabled_count} 个启用，{total - enabled_count} 个禁用）"
        )
        if read_missing:
            read_status += f"；{len(read_missing)} 个本地未找到（sha256 为空）"

        # ---------- 阶段二：对齐（本地缺失模型扫描） ----------
        entries = []
        for c in preset_configs:
            s = c.get("sha256")
            if isinstance(s, str) and s.strip():
                entries.append({"name": c.get("name", ""), "sha256": s.strip().lower()})

        if not entries:
            align_status = "预设中无 sha256 记录，跳过对齐扫描"
            return (preset_json, lora_names, read_status, "", align_status, 0)

        local_map = _build_local_sha_map()
        missing = [e for e in entries if e["sha256"] not in local_map]

        align_status = (
            f"扫描本地 lora 目录，共 {len(local_map)} 个模型；"
            f"预设含 {len(entries)} 个 sha256，缺失 {len(missing)} 个"
        )

        missing_sha256 = ""
        if missing:
            # 保持顺序并去重
            seen = set()
            uniq = []
            for e in missing:
                if e["sha256"] not in seen:
                    seen.add(e["sha256"])
                    uniq.append(e)
            missing_sha256 = json.dumps(uniq, ensure_ascii=False)

        return (preset_json, lora_names, read_status, missing_sha256, align_status, len(missing))

    def _empty_output(self, status):
        return ("[]", "[]", status, "", status, 0)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "PresetFolderAligner": PresetFolderAligner,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PresetFolderAligner": "Preset Folder Aligner (读预设+对齐)",
}
