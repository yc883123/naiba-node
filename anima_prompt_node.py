"""
Anima Prompt Node - 基于本地 anima_prompts.json 的交互式提示词节点
按 naiba_tag_picker 风格重写：
  - 模块级数据缓存（不再每次路由都实例化节点重读 JSON）
  - 字符串控件放在 required（由前端 JS 隐藏），杜绝 hidden 段吞参数的坑
  - execute 与前端统一状态结构（{selected:[...]}, {tags:[...]}）严格对齐
数据源：本地 anima_prompts.json，结构为 {分类: [{en_tags, cn_description, raw_en}, ...]}
"""

import os
import json
import random
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 仅在 ComfyUI 环境下导入（缺失时降级，便于纯语法检查）
try:
    from aiohttp import web
    from server import PromptServer
except Exception:  # pragma: no cover
    web = None
    PromptServer = None

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anima_prompts.json")

# ----------------------------- 模块级数据缓存 -----------------------------
_DATA = None
_DATA_LOCK = threading.Lock()


def _load_data(force=False):
    """加载并缓存标签数据；线程安全，多路由/多节点实例共享。"""
    global _DATA
    if _DATA is not None and not force:
        return _DATA
    with _DATA_LOCK:
        if _DATA is not None and not force:
            return _DATA
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            total = sum(len(v) for v in data.values() if isinstance(v, list))
            print(f"[anima_prompt_node] 已加载标签数据：{len(data)} 个分类 / {total} 条")
        except Exception as e:
            print(f"[anima_prompt_node] 加载数据失败: {e}")
            data = {}
        _DATA = data
        return _DATA


def _get_categories():
    return [c for c in _load_data().keys() if c not in _EXCLUDED_CATEGORIES]


def _get_tags(category, query="", page=1, page_size=20):
    data = _load_data()
    tags = data.get(category) or []
    if not isinstance(tags, list):
        tags = []
    if query:
        q = query.lower()
        tags = [
            t for t in tags
            if q in str(t.get("raw_en", "")).lower()
            or q in str(t.get("cn_description", "")).lower()
        ]
    total = len(tags)
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    start = (page - 1) * page_size
    items = tags[start:start + page_size]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 1,
    }


def _gacha(category, count=1):
    data = _load_data()
    tags = data.get(category) or []
    if not isinstance(tags, list) or not tags:
        return []
    count = max(1, int(count))
    return random.sample(tags, min(count, len(tags)))


_EXCLUDED_CATEGORIES = {"全库标签"}


def _gacha_random(count=1):
    """跨全部分类完全随机抽取，返回带 category 的条目。排除全库标签等聚合分类。"""
    data = _load_data()
    pool = []
    for cat, tags in data.items():
        if cat in _EXCLUDED_CATEGORIES:
            continue
        if isinstance(tags, list):
            for t in tags:
                if isinstance(t, dict) and t.get("raw_en"):
                    item = dict(t)
                    item["category"] = cat
                    pool.append(item)
    if not pool:
        return []
    count = max(1, int(count))
    return random.sample(pool, min(count, len(pool)))


def _gacha_multi(categories=None, count=1, category_counts=None):
    """对给定分类列表，每个分类各自随机抽取 count 个（补 category 字段后合并）。
    如果提供 category_counts 字典（{category: count}），则按每个分类的指定数量抽取，忽略 categories 和 count 参数。
    排除全库标签等聚合分类。
    """
    data = _load_data()
    if category_counts is not None:
        # category_counts: {category: count}
        out = []
        for cat, cnt in category_counts.items():
            if cat in _EXCLUDED_CATEGORIES:
                continue
            cnt = max(0, int(cnt))
            if cnt <= 0:
                continue
            tags = data.get(cat) or []
            if not isinstance(tags, list) or not tags:
                continue
            for t in random.sample(tags, min(cnt, len(tags))):
                item = dict(t)
                item["category"] = cat
                out.append(item)
        return out
    # 向后兼容：使用 categories 和 count
    if categories is None:
        categories = []
    count = max(1, int(count))
    out = []
    for cat in categories:
        if cat in _EXCLUDED_CATEGORIES:
            continue
        tags = data.get(cat) or []
        if not isinstance(tags, list) or not tags:
            continue
        for t in random.sample(tags, min(count, len(tags))):
            item = dict(t)
            item["category"] = cat
            out.append(item)
    return out


def _gacha_across(count=1):
    """跨不同分类随机抽取：先洗牌分类，随机取 count 个**不同**分类，每类各取 1 个标签。
    用于『随机抽取』场景，保证每个分类最多 1 个，输出总数恰为 count（不重复）。
    排除全库标签等聚合分类。"""
    data = _load_data()
    count = max(1, int(count))
    cats = [c for c, v in data.items() if isinstance(v, list) and v and c not in _EXCLUDED_CATEGORIES]
    if not cats:
        return []
    random.shuffle(cats)
    cats = cats[: min(count, len(cats))]
    out = []
    for cat in cats:
        tags = data.get(cat) or []
        if not isinstance(tags, list) or not tags:
            continue
        item = dict(random.sample(tags, 1)[0])
        item["category"] = cat
        out.append(item)
    return out


# ----------------------------- 统一状态解析 -----------------------------
def _parse_items(raw, key):
    """解析前端序列化的 JSON，返回条目列表。
    兼容：
      - 新结构 {key: [{tag/raw_en, category, cn}]}
      - 旧结构 {分类: [{tag, category}]}（按分类分组）
    """
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(obj, dict):
        return []
    if isinstance(obj.get(key), list):
        return [it for it in obj[key] if isinstance(it, dict)]
    # 兜底：旧的按分类分组结构
    out = []
    for cat, arr in obj.items():
        if isinstance(arr, list):
            for it in arr:
                if isinstance(it, dict):
                    item = dict(it)
                    item.setdefault("category", cat)
                    out.append(item)
    return out


def _item_text(it):
    """取条目的输出文本：优先 raw_en，其次 tag。"""
    if not isinstance(it, dict):
        return str(it) if it else ""
    return str(it.get("raw_en") or it.get("tag") or "").strip()


# ----------------------------- 节点 -----------------------------
class AnimaPromptNode:
    CATEGORY = "naiba-node"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    OUTPUT_NODE = True
    SEARCH_ALIASES = ["naiba", "anima prompt", "prompt node", "anima"]
    DESCRIPTION = (
        "Anima Prompt Node —— 基于本地 anima_prompts.json 的交互式英文提示词节点。"
        "点击节点打开弹窗，可按分类浏览标签、关键词搜索；支持单分类抽取、跨分类抽取、全库随机抽（扭蛋）。"
        "选中或抽取的标签（raw_en）会自动拼接为英文 prompt，由 prompt 端口输出。"
        "数据来源：本地 anima_prompts.json，结构为 {分类: [{en_tags, cn_description, raw_en}, ...]}。"
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 由前端弹窗写入、JS 隐藏。放 required 而非 hidden，
                # 否则 ComfyUI 的 hidden 只注入特殊类型（PROMPT/UNIQUE_ID 等），
                # 普通 STRING 不会传进 execute，导致输出永远为空。
                "selection_data": ("STRING", {"multiline": True, "default": "{}"}),
                "gacha_data": ("STRING", {"multiline": True, "default": "{}"}),
                "ui_state": ("STRING", {"multiline": True, "default": "{}"}),
                "separator": ("STRING", {"default": "，", "multiline": False, "label": "分隔符", "tooltip": "多个标签拼接成 prompt 时使用的分隔字符，默认中文逗号「，」，避免留空导致词语连在一起"}),
            },
        }

    def execute(self, selection_data="{}", gacha_data="{}", ui_state="{}", separator="，"):
        selected = _parse_items(selection_data, "selected")
        gacha = _parse_items(gacha_data, "tags")

        texts = []
        for it in selected:
            t = _item_text(it)
            if t:
                texts.append(t)
        for it in gacha:
            t = _item_text(it)
            if t:
                texts.append(t)

        # 去重（保序）
        seen = set()
        unique = []
        for t in texts:
            if t not in seen:
                seen.add(t)
                unique.append(t)

        sep = separator if (isinstance(separator, str) and separator != "") else "，"
        return (sep.join(unique),)


# ----------------------------- 线程池 -----------------------------
_EXECUTOR = None
_EXECUTOR_LOCK = threading.Lock()


def _get_executor():
    global _EXECUTOR
    if _EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _EXECUTOR is None:
                _EXECUTOR = ThreadPoolExecutor(max_workers=2)
    return _EXECUTOR


async def _run_in_exec(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), fn, *args)


# ----------------------------- 路由注册 -----------------------------
def register_routes():
    if PromptServer is None or web is None:
        return
    routes = PromptServer.instance.routes

    @routes.get("/anima/prompt/categories")
    async def anima_categories(request):
        cats = await _run_in_exec(_get_categories)
        return web.json_response({"categories": cats})

    @routes.get("/anima/prompt/tags")
    async def anima_tags(request):
        category = request.query.get("category", "")
        query = request.query.get("query", "")
        try:
            page = int(request.query.get("page", "1"))
        except Exception:
            page = 1
        try:
            page_size = int(request.query.get("page_size", "20"))
        except Exception:
            page_size = 20
        res = await _run_in_exec(_get_tags, category, query, page, page_size)
        return web.json_response(res)

    @routes.get("/anima/prompt/gacha")
    async def anima_gacha(request):
        # 优先检查 category_counts 参数（JSON 字符串）
        category_counts_str = request.query.get("category_counts", "")
        if category_counts_str:
            try:
                category_counts = json.loads(category_counts_str)
                if not isinstance(category_counts, dict):
                    category_counts = None
            except Exception:
                category_counts = None
            if category_counts is not None:
                tags = await _run_in_exec(_gacha_multi, None, 1, category_counts)
                return web.json_response({"tags": tags})
        # 向后兼容旧参数
        categories = request.query.get("categories", "")
        category = request.query.get("category", "")
        try:
            count = int(request.query.get("count", "1"))
        except Exception:
            count = 1
        if categories:
            cats = [c.strip() for c in categories.split(",") if c.strip()]
            tags = await _run_in_exec(_gacha_multi, cats, count)
        elif category:
            tags = await _run_in_exec(_gacha, category, count)
            # 补上 category 字段，供前端结果区显示
            tags = [dict(t, category=category) for t in tags]
        else:
            tags = await _run_in_exec(_gacha_random, count)
        return web.json_response({"tags": tags})

    @routes.get("/anima/prompt/gacha_across")
    async def anima_gacha_across(request):
        try:
            count = int(request.query.get("count", "1"))
        except Exception:
            count = 1
        tags = await _run_in_exec(_gacha_across, count)
        return web.json_response({"tags": tags})

    @routes.get("/anima/prompt/reload")
    async def anima_reload(request):
        await _run_in_exec(_load_data, True)
        return web.json_response({"ok": True, "categories": _get_categories()})


try:
    register_routes()
except Exception as e:
    print(f"[anima_prompt_node] register_routes error: {e}")


# ----------------------------- 注册 -----------------------------
NODE_CLASS_MAPPINGS = {
    "AnimaPromptNode": AnimaPromptNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AnimaPromptNode": "Anima Prompt Node ⚓",
}
