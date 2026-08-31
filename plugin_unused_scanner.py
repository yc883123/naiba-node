#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
未使用插件扫描工具 —— 核心逻辑（被 CLI 与 GUI 共用）

功能：
  读取 ComfyUI 启动器生成的 node_mapping_cache.json（节点类型 -> 插件名 映射），
  递归扫描用户自定义目录下的工作流 JSON，提取实际被用到的节点类型，
  反推出哪些 custom_nodes 插件在所有工作流里「零命中」，生成「可删除插件清单」报告。

特点：
  - 仅标准库，无第三方运行时依赖（GUI 版用 tkinter，亦为标准库）。
  - 缓存优先；缺失时 AST 静态兜底（不执行任何 import，不加载插件）。
  - 兼容 UI 格式(nodes[].type) 与 API 格式(class_type)。
  - 三态分类：未使用(可删) / 已使用 / 无法确定(纯 JS 扩展等)。
  - 全程只输出报告，绝不删除、重命名任何插件。
"""

import ast
import json
import os
import re
from datetime import datetime
from pathlib import Path

# 本机安装路径兜底默认值（仅当无法从文件位置推导时使用）
KNOWN_COMFY_PATH = r"D:\comfyuibyte\ComfyUI_portable_TE_v260619\ComfyUI"


def detect_comfy_path() -> str:
    """尝试从脚本位置推导 ComfyUI 根目录（naiba-test -> custom_nodes -> ComfyUI）。"""
    try:
        here = Path(__file__).resolve()
        candidate = here.parents[2]
        if (candidate / "custom_nodes").is_dir():
            return str(candidate)
    except Exception:
        pass
    return KNOWN_COMFY_PATH


def normalize_path(p: str) -> str:
    """与 save_node_mapping.py 完全一致的路径归一化逻辑。"""
    return os.path.normpath(p).replace("\\", "/")


def load_node_mapping_from_cache(comfy_path: str, cache_path: str):
    """从 node_mapping_cache.json 读取 (节点名->插件名, 插件目录名列表)。

    返回 (mappings, plugin_list) 或 (None, None) 表示缓存不可用。
    """
    if not os.path.isfile(cache_path):
        print(f"[缓存] 未找到缓存文件：{cache_path}")
        return None, None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception as e:
        print(f"[缓存] 读取失败：{e}")
        return None, None

    paths_data = cache.get("paths", {})
    key = normalize_path(comfy_path)
    entry = paths_data.get(key)
    if entry is None:
        # 当前安装路径不在缓存中：不使用其它安装的数据（插件名可能不同，会误判），直接 AST 兜底
        print(f"[缓存] 未找到当前安装路径键：{key}，将启用 AST 兜底。")
        return None, None

    mappings = entry.get("mappings") or {}
    plugin_list = entry.get("plugin_list") or []
    if not mappings:
        print("[缓存] 当前条目 mappings 为空，将启用 AST 兜底。")
        return None, None
    print(f"[缓存] 成功读取映射：{len(mappings)} 个节点，{len(plugin_list)} 个插件目录。")
    return mappings, plugin_list


def extract_node_names_from_file(path: str) -> set:
    """用 AST 静态解析单个 .py 文件中 NODE_CLASS_MAPPINGS 的键名（best-effort，不执行导入）。"""
    names = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
        tree = ast.parse(src)
    except Exception:
        return names

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                # 形式一：NODE_CLASS_MAPPINGS = {"A": ..., "B": ...}
                if isinstance(target, ast.Name) and target.id == "NODE_CLASS_MAPPINGS":
                    if isinstance(node.value, ast.Dict):
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                names.add(k.value)
                # 形式二：NODE_CLASS_MAPPINGS["X"] = SomeClass
                elif isinstance(target, ast.Subscript):
                    if isinstance(target.value, ast.Name) and target.value.id == "NODE_CLASS_MAPPINGS":
                        sl = target.slice
                        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                            names.add(sl.value)
    return names


def build_mapping_by_ast(comfy_path: str):
    """缓存不可用时的兜底：静态扫描 custom_nodes 下每个插件的 .py，建立 节点名->插件 映射。"""
    custom_nodes = os.path.join(comfy_path, "custom_nodes")
    if not os.path.isdir(custom_nodes):
        print(f"[AST] custom_nodes 目录不存在：{custom_nodes}")
        return {}, []

    mappings = {}
    plugin_list = []
    for item in sorted(os.listdir(custom_nodes)):
        item_path = os.path.join(custom_nodes, item)
        if not os.path.isdir(item_path):
            continue
        if item.startswith(".") or item == "__pycache__" or item.endswith(".disabled"):
            continue
        plugin_list.append(item)
        # 递归扫描插件目录内所有 .py（跳过 __pycache__）
        for root, dirs, files in os.walk(item_path):
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            for fn in files:
                if fn.endswith(".py"):
                    for name in extract_node_names_from_file(os.path.join(root, fn)):
                        mappings[name] = item
    print(f"[AST] 兜底扫描完成：{len(mappings)} 个节点，{len(plugin_list)} 个插件目录。")
    return mappings, plugin_list


def load_node_mapping(comfy_path: str, cache_path: str):
    """优先缓存，缺失则 AST 兜底。返回 (mappings, plugin_list)。"""
    mappings, plugin_list = load_node_mapping_from_cache(comfy_path, cache_path)
    if mappings is None:
        mappings, plugin_list = build_mapping_by_ast(comfy_path)
    return mappings, plugin_list


def collect_used_node_types(workflow_dirs: list) -> tuple:
    """递归扫描工作流目录，收集被引用的节点类型集合。

    返回 (used_set, stats_dict)。stats 含扫描文件数、异常数等。
    """
    used = set()
    stats = {"scanned": 0, "skipped": 0, "errors": 0}

    json_files = []
    for d in workflow_dirs:
        if not os.path.isdir(d):
            print(f"[工作流] 目录不存在，已跳过：{d}")
            continue
        for root, dirs, files in os.walk(d):
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            for fn in files:
                if fn.lower().endswith(".json"):
                    json_files.append(os.path.join(root, fn))

    print(f"[工作流] 共发现 {len(json_files)} 个 JSON 文件，开始扫描...")

    type_re = re.compile(r'"type"\s*:\s*"([^"]+)"')
    class_re = re.compile(r'"class_type"\s*:\s*"([^"]+)"')

    for fp in json_files:
        stats["scanned"] += 1
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            # 快速文本提取（避免对大文件做完整 json 解析失败时报错中断）
            for m in type_re.finditer(text):
                used.add(m.group(1))
            for m in class_re.finditer(text):
                used.add(m.group(1))
        except Exception:
            stats["errors"] += 1

    return used, stats


def classify_plugins(mappings: dict, plugin_list: list, used: set, include_disabled: bool, comfy_real: str):
    """三态分类。返回分类字典。"""
    plugin_nodes = {}
    for node_name, plugin in mappings.items():
        plugin_nodes.setdefault(plugin, set()).add(node_name)

    result = {"unused": [], "used": [], "undetermined": [], "disabled": []}

    for plugin in plugin_list:
        nodes = plugin_nodes.get(plugin)
        if not nodes:
            result["undetermined"].append(plugin)
            continue
        if used & nodes:
            result["used"].append(plugin)
        else:
            result["unused"].append(plugin)

    if include_disabled:
        custom_nodes = os.path.join(comfy_real, "custom_nodes")
        if os.path.isdir(custom_nodes):
            for item in sorted(os.listdir(custom_nodes)):
                if item.endswith(".disabled"):
                    result["disabled"].append(item)
    return result


def generate_report(comfy_path, cache_path, workflow_dirs, used, stats, result, include_disabled):
    """生成报告文本（同时用于控制台与文件）。"""
    lines = []
    lines.append("=" * 60)
    lines.append("  ComfyUI 未使用插件扫描报告")
    lines.append("=" * 60)
    lines.append(f"生成时间 : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"ComfyUI  : {comfy_path}")
    lines.append(f"缓存文件 : {cache_path}")
    lines.append("工作流目录:")
    for d in workflow_dirs:
        lines.append(f"    - {d}")
    lines.append(f"扫描文件 : {stats['scanned']} 个 JSON（解析异常 {stats['errors']} 个）")
    lines.append(f"引用节点 : {len(used)} 种不同节点类型")
    lines.append("")

    lines.append("-" * 60)
    lines.append(f"【未使用 / 可删除】共 {len(result['unused'])} 个（其 python 节点未被任何工作流引用）")
    lines.append("-" * 60)
    if result["unused"]:
        for p in sorted(result["unused"]):
            lines.append(f"  [ ] {p}")
    else:
        lines.append("  （无）")
    lines.append("")

    lines.append("-" * 60)
    lines.append(f"【已使用】共 {len(result['used'])} 个")
    lines.append("-" * 60)
    if result["used"]:
        for p in sorted(result["used"]):
            lines.append(f"  [x] {p}")
    else:
        lines.append("  （无）")
    lines.append("")

    lines.append("-" * 60)
    lines.append(f"【无法确定】共 {len(result['undetermined'])} 个（无 python 节点映射，可能纯 JS 扩展，勿盲目删除）")
    lines.append("-" * 60)
    if result["undetermined"]:
        for p in sorted(result["undetermined"]):
            lines.append(f"  [?] {p}")
    else:
        lines.append("  （无）")
    lines.append("")

    if include_disabled and result.get("disabled"):
        lines.append("-" * 60)
        lines.append(f"【已禁用(.disabled)】共 {len(result['disabled'])} 个（已手动禁用，仅供参考）")
        lines.append("-" * 60)
        for p in sorted(result["disabled"]):
            lines.append(f"  [D] {p}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("提示：本报告仅列出清单，未做任何删除/重命名操作。")
    lines.append("      删除插件前请确认其未被其它脚本/JS 扩展依赖。")
    lines.append("=" * 60)
    return "\n".join(lines)


def scan(comfy_path=None, cache_path=None, workflow_dirs=None, include_disabled=False):
    """核心扫描入口，供 CLI / GUI 共用。

    返回 (report_text, result_dict, stats_dict)。
    异常时抛出 RuntimeError，由调用方处理。
    """
    comfy_real = os.path.normpath(comfy_path or detect_comfy_path())
    cache_path = cache_path or os.path.join(os.path.dirname(comfy_real), "node_mapping_cache.json")
    workflow_dirs = workflow_dirs or [os.path.join(comfy_real, "user", "default")]

    mappings, plugin_list = load_node_mapping(comfy_real, cache_path)
    if not plugin_list:
        raise RuntimeError("无法获得插件列表（缓存与 AST 兜底均失败），请检查 ComfyUI 路径。")

    used, stats = collect_used_node_types(workflow_dirs)
    result = classify_plugins(mappings, plugin_list, used, include_disabled, comfy_real)
    report = generate_report(comfy_real, cache_path, workflow_dirs, used, stats, result, include_disabled)
    return report, result, stats


def main(argv=None):
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="扫描未被任何工作流使用的 ComfyUI 插件（仅生成报告）"
    )
    parser.add_argument("--comfy", default=None, help="ComfyUI 根目录（默认自动推导）")
    parser.add_argument("--cache", default=None, help="node_mapping_cache.json 路径")
    parser.add_argument("--workflows", nargs="+", default=None, help="工作流目录（可多个，递归扫描 .json）")
    parser.add_argument("--output", default=None, help="报告输出文件路径（可选）")
    parser.add_argument("--include-disabled", action="store_true", help="同时把 .disabled 目录列为已禁用信息")
    args = parser.parse_args(argv)

    try:
        report, result, stats = scan(
            comfy_path=args.comfy,
            cache_path=args.cache,
            workflow_dirs=args.workflows,
            include_disabled=args.include_disabled,
        )
    except Exception as e:
        print(f"[错误] {e}")
        return 1

    print("\n" + report)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report + "\n")
            print(f"\n[完成] 报告已写入：{args.output}")
        except Exception as e:
            print(f"\n[警告] 报告写入失败：{e}")
    else:
        print("\n[完成] 扫描结束。")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
