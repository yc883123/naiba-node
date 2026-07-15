"""
Preset Folder Reader 节点
直接从 presets/ 文件夹读取预设 JSON 文件，输出 naiba 预设格式（含文件 sha256）。

与 Power LoRA Config Reader 的区别：
- 不依赖画布连线，直接读磁盘上的预设文件，链路最简单、最稳定。
- 预设保存时已由后端写入 sha256；若某条目缺 sha256，则按文件名现场计算（带缓存）。

输出格式与 Power LoRA Config Reader 一致，可直接接入
Preset Sha256 Aligner / Civitai Sha256 Info Reader。
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
        print(f"[PresetFolderReader] sha256 error {os.path.basename(path)}: {e}")
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
        print(f"[PresetFolderReader] 列出预设失败: {e}")
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


class PresetFolderReader:
    """
    读取 presets/ 文件夹中的预设 JSON，输出 naiba 预设格式（含 sha256）。

    用法：
    1. preset_name 下拉选择 presets/ 中的预设（点节点上的"刷新预设列表"可重新扫描）
    2. preset_json 输出口输出含 name/strength_model/strength_clip/enabled/sha256 的 JSON
    3. lora_names 输出口输出启用的 LoRA 文件名列表
    4. status 输出口输出读取状态
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

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("preset_json", "lora_names", "status")
    FUNCTION = "read_preset"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "直接从 presets/ 文件夹读取预设文件，输出 naiba 预设格式（含文件 sha256）。\n"
        "不依赖画布连线，比从画布读取 LoRA 加载器更稳定。\n"
        "preset_json 每项含 name/strength_model/strength_clip/enabled/sha256，"
        "可直接接入 Preset Sha256 Aligner 或 Civitai Sha256 Info Reader。"
    )
    SEARCH_ALIASES = [
        "naiba", "preset folder", "preset reader", "预设读取",
        "预设文件夹", "读预设", "preset file"
    ]

    def read_preset(self, preset_name, skip_disabled=False):
        """读取选中预设并转换为预设格式（含 sha256）"""

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
        missing = []
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
                    missing.append(name)
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
        status = (
            f"从 [{preset_name}] 读取到 {total} 个 LoRA"
            f"（{enabled_count} 个启用，{total - enabled_count} 个禁用）"
        )
        if missing:
            status += f"；{len(missing)} 个本地未找到（sha256 为空）"

        return (preset_json, lora_names, status)

    def _empty_output(self, status):
        return ("[]", "[]", status)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "PresetFolderReader": PresetFolderReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PresetFolderReader": "Preset Folder Reader",
}
