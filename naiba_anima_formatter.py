"""
NaibaAnimaFormatter —— Anima/Noob/CKNoob 标准格式提示词转换器

作为 naiba tag picker 的下游独立节点：接收 artist / character / ip / general 等
逗号连接的标签字符串，按要求重排为对应模型训练习惯的提示词。

特性：
- 三种模型格式：Anima / Noob / CKNoob
- 画师 @ 前缀归一（Anima 自动加、Noob/CKNoob 去 @、artist_at_prefix 强制加）
- 下划线转空格（白名单 score_/rating_/source_/year_ 保留）
- 括号转义
- 自动从 general 抽取计数标签、自动补充质量预制词
- 支持 merged_tags 兜底解析

完全自实现，不导入 ComfyUI-Danbooru-Anima-Prompt 任何符号（参考其顺序/处理逻辑，
但全部在内联常量中重新定义），仅依赖标准库，无网络、无 IO。
"""

import re

CATEGORY = "naiba-node"


# ─────────────────────────────────────────────────────────────────────────────
# 常量：质量预制词（对应 Anima 节点 _QUALITY_PRESETS）
# ─────────────────────────────────────────────────────────────────────────────
_QUALITY_PRESETS = {
    "Anima": "masterpiece, best quality, score_7, score_9, very aesthetic, ultra detailed",
    "Noob": "masterpiece, best quality, newest, absurdres, highres",
    "CKNoob": "high resolution, aesthetic, excellent, medium resolution, year 2025, newest",
}

# 下划线保留前缀白名单（与 Anima 节点 _KEEP_UNDERSCORE_PREFIXES 一致）
_KEEP_UNDERSCORE_PREFIXES = ("score_", "rating_", "source_", "year_")

# Noob 模式 general 子分类 → 排序优先级（场景/其他=0, 动作=1, 表情=2, 服装=3, 配饰=4）
_NOOB_CAT_PRIORITY = {
    "background": 0,      # 场景/背景
    "other": 0,           # 其他
    "body_features": 0,   # 身体特征（归入场景/其他）
    "pose": 1,            # 动作/姿势
    "expression": 2,      # 表情
    "clothing": 3,        # 服装
    "accessories": 4,     # 配饰
}


# ─────────────────────────────────────────────────────────────────────────────
# 常量：general 子分类后缀规则（内联自 Anima 的 tag_classifier._SUFFIX_RULES）
# ─────────────────────────────────────────────────────────────────────────────
_SUB_CATS = {
    "body_features": {"hair", "hair_color", "hair_styles", "eyes_tags", "skin_color", "body_parts"},
    "clothing": {"attire", "legwear", "handwear", "headwear"},
    "pose": {"posture", "gestures"},
    "expression": {"face_tags"},
    "background": {"backgrounds"},
    "accessories": {"accessories"},
    "other": {"image_composition", "lighting", "patterns", "visual_aesthetic", "colors", "focus_tags"},
}
_ALL_SUB_KEYS = list(_SUB_CATS.keys())

_SUFFIX_RULES = [
    (["_hair", "_haired", "twintails", "ponytail", "ahoge", "bangs",
      "_eyes", "_eyebrow", "_eyelash",
      "_ear", "_ears", "_nose", "_lip", "_lips", "_tongue",
      "_breast", "_breasts", "_nipple", "_nipples",
      "_hand", "_hands", "_finger", "_fingers", "_arm", "_arms",
      "_foot", "_feet", "_leg", "_legs", "_thigh", "_thighs",
      "_skin", "_tail", "_wing", "_wings", "_horn", "_horns",
      "_cheek", "_chin", "_neck", "_waist", "_hip", "_hips",
      "_belly", "_navel", "_abs", "_muscle", "_muscles",
      "_fur", "_scales", "_fin", "_tentacle", "_tentacles"], "body_features"),
    (["_shirt", "_skirt", "_dress", "_boots", "_sleeves", "_necktie", "_collar",
      "_uniform", "_socks", "_stockings", "_pants", "_shorts", "_gloves",
      "_ribbon", "_jacket", "_coat", "_cape", "_hat", "_scarf", "_belt",
      "_bow", "_apron", "_shoe", "_sandals", "_loafers", "_heels",
      "_thighhighs", "_pantyhose", "_choker", "_bracelet", "_ring",
      "_trim", "_lace", "_frill", "_bowtie"], "clothing"),
    (["_pose", "sitting", "standing", "lying", "kneeling", "crouching",
      "spread_legs", "leg_up", "arms_up", "hand_up", "hands_up",
      "pointing", "waving", "gesture", "from_side", "from_behind",
      "from_above", "from_below", "full_body", "crotch_up"], "pose"),
    (["smile", "smirk", "frown", "pout", "blush", "angry", "sad",
      "happy", "teeth", "tongue_out", "open_mouth", "closed_mouth",
      "tear", "crying", "expressionless", "excited", "surprised",
      "embarrassed", "annoyed", "disgust"], "expression"),
    (["_background", "outdoors", "indoor", "night", "day", "sunset",
      "cityscape", "nature", "beach", "forest", "room", "street",
      "simple_background", "white_background", "gradient_background",
      "cloud", "sky"], "background"),
    (["_ornament", "_band", "_glass", "_glasses", "_headphone",
      "_headset", "_ribbon", "_pin", "_brooch", "sunglasses"], "accessories"),
]


# ─────────────────────────────────────────────────────────────────────────────
# 计数标签识别
# ─────────────────────────────────────────────────────────────────────────────
# 不以数字开头、但属于计数语义的标签集合
_COUNT_SET = {
    "solo", "solo_focus", "multiple_girls", "multiple_boys",
    "multiple", "group", "duo", "trio", "couple",
}
# 数字 + 该名词 → 计数标签（避免把 3d / 2024 之类误判）
_COUNT_NOUNS = {
    "girl", "girls", "boy", "boys", "other", "others",
    "cat", "cats", "dog", "dogs", "animal", "animals",
    "child", "children", "kid", "kids", "person", "people",
    "men", "women", "female", "male", "pokemon",
    "creature", "creatures", "android", "androids",
    "fox", "foxes", "wolf", "wolves", "bird", "birds", "fish",
}
_COUNT_DIGIT_RE = re.compile(r"^(\d+)([a-z_]+)$")


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────
def _split_tags(text):
    """把逗号连接的标签拆成列表，支持中英文逗号、顿号、换行。

    不做空格切分，避免破坏 'year 2025' 这类含空格的标签。
    """
    if not text or not text.strip():
        return []
    parts = re.split(r"[,，、\n]+", text)
    out = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(p)
    return out


def _should_keep_underscore(tag):
    tl = tag.lower()
    return any(tl.startswith(pre) for pre in _KEEP_UNDERSCORE_PREFIXES)


def _is_count_tag(tag):
    t = tag.lower().strip()
    if not t:
        return False
    if t in _COUNT_SET:
        return True
    m = _COUNT_DIGIT_RE.match(t)
    if m:
        return m.group(2) in _COUNT_NOUNS
    return False


def _pattern_match(tag):
    """后缀 → 子类映射（内联自 tag_classifier._pattern_match）。"""
    t = tag.lower()
    for suffixes, cat in _SUFFIX_RULES:
        for sfx in suffixes:
            if t == sfx or t.endswith("_" + sfx) or t.endswith(sfx):
                return cat
    return None


def _classify_general(tags):
    """内联自 tag_classifier.classify_general（去掉外部 json 依赖版）。

    返回 (result_dict, uncategorized_list)
    """
    result = {k: [] for k in _ALL_SUB_KEYS}
    uncategorized = []
    for tag in tags:
        cat = _pattern_match(tag)
        if cat:
            result[cat].append(tag)
        else:
            uncategorized.append(tag)
    return result, uncategorized


def _get_tag_order(tag_text):
    """Noob 模式下单个标签的排序编号。"""
    result, uncat = _classify_general([tag_text])
    for cat_name, tags in result.items():
        if tag_text in tags:
            return _NOOB_CAT_PRIORITY.get(cat_name, 0)
    return 0


class NaibaAnimaFormatter:
    """把 naiba tag picker 输出的分类标签按 Anima/Noob/CKNoob 标准格式重排。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "artist_tags": ("STRING", {
                    "multiline": True, "default": "",
                    "placeholder": "画师标签（连 ARTIST_NAMES）。可带 @，会自动归一",
                    "tooltip": "对应 NaibaTagPicker 的 ARTIST_NAMES 输出",
                }),
                "character_tags": ("STRING", {
                    "multiline": True, "default": "",
                    "placeholder": "角色标签（连 CHARACTER_NAMES）",
                    "tooltip": "对应 NaibaTagPicker 的 CHARACTER_NAMES 输出",
                }),
                "ip_tags": ("STRING", {
                    "multiline": True, "default": "",
                    "placeholder": "作品/IP/版权标签（连 IP_NAMES）→ 作为 Anima 的 series 槽位",
                    "tooltip": "对应 NaibaTagPicker 的 IP_NAMES 输出；Anima 模式下排在 character 之后、artist 之前",
                }),
                "general_tags": ("STRING", {
                    "multiline": True, "default": "",
                    "placeholder": "通用标签（连 TAG_NAMES）",
                    "tooltip": "对应 NaibaTagPicker 的 TAG_NAMES 输出；计数标签会被自动抽到 count 段",
                }),
                "model_type": (["Anima", "Noob", "CKNoob"], {
                    "default": "Anima",
                    "tooltip": "Anima：画师自动加@，顺序 quality→count→character→series→artist→general；"
                               "Noob/CKNoob：画师去@，顺序 count→character→artist→general→quality，general 内部重排",
                }),
                "underscore_mode": (["转空格", "保留下划线"], {
                    "default": "转空格",
                    "tooltip": "转空格时跳过 score_/rating_/source_/year_ 前缀标签",
                }),
                "escape_parens": ("BOOLEAN", {
                    "default": True,
                    "label_on": "转义 ()", "label_off": "不转义",
                }),
                "escape_ip_parens": ("BOOLEAN", {
                    "default": False,
                    "label_on": "角色\\（作品\\）", "label_off": "角色（作品）",
                    "tooltip": "开启后 CHARACTER_IP_NAMES 段中的 角色（作品） 变为 角色\\（作品\\），仅作用于该段",
                }),
                "artist_at_prefix": ("BOOLEAN", {
                    "default": False,
                    "label_on": "强制加 @", "label_off": "由模型模式控制",
                }),
                "separator": ("STRING", {"default": ", ", "multiline": False}),
            },
            "optional": {
                "merged_tags": ("STRING", {
                    "multiline": True, "default": "",
                    "placeholder": "兜底：四个分类端口全空时，解析此合并字符串（连 MERGED_TAGS）",
                    "tooltip": "连 NaibaTagPicker 的 MERGED_TAGS；仅当四个分类端口都为空时作为兜底",
                }),
                "character_ip_names": ("STRING", {
                    "multiline": True, "default": "",
                    "placeholder": "角色（作品）配对串（连 CHARACTER_IP_NAMES）",
                    "tooltip": "连 NaibaTagPicker 的 CHARACTER_IP_NAMES；填了则替代 character+ip 两段（Anima 的 series 位置）",
                }),
                "quality_meta": ("STRING", {
                    "multiline": True, "default": "",
                    "placeholder": "质量/评分标签（可选；为空时按模型自动填充预制词）",
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "format_prompt"
    CATEGORY = CATEGORY
    SEARCH_ALIASES = ["naiba", "anima formatter", "prompt formatter", "formatter", "anima"]

    # ── 单分类处理：下划线 / 括号 / 画师@ ──
    def _process_single(self, tag_str, is_artist, model_type, underscore_mode,
                        escape_parens, artist_at_prefix, separator):
        if not tag_str or not tag_str.strip():
            return []
        raw_tags = _split_tags(tag_str)
        processed = []
        for t in raw_tags:
            # 下划线 → 空格（跳过白名单前缀）
            if underscore_mode == "转空格" and not _should_keep_underscore(t):
                t = t.replace("_", " ")
            # 括号转义
            if escape_parens:
                t = re.sub(r"(?<!\\)\(", "\\(", t)
                t = re.sub(r"(?<!\\)\)", "\\)", t)
            # 画师 @ 归一
            if is_artist:
                t = t.lstrip("@")
                if model_type in ("Noob", "CKNoob"):
                    pass  # 去 @
                elif artist_at_prefix or model_type == "Anima":
                    if not t.startswith("@"):
                        t = "@" + t
            processed.append(t)
        return processed

    def format_prompt(self, artist_tags="", character_tags="", ip_tags="",
                      general_tags="", model_type="Anima", underscore_mode="转空格",
                      escape_parens=True, artist_at_prefix=False, separator=", ",
                      merged_tags="", quality_meta="", character_ip_names="",
                      escape_ip_parens=False):
        # 0. 兜底：四个分类端口全空时解析 merged_tags
        if (not artist_tags.strip() and not character_tags.strip()
                and not ip_tags.strip() and not general_tags.strip()
                and merged_tags and merged_tags.strip()):
            merged_list = _split_tags(merged_tags)
            artist_raw, character_raw, ip_raw, general_raw, count_raw = [], [], [], [], []
            for tg in merged_list:
                if tg.startswith("@"):
                    artist_raw.append(tg)
                elif _is_count_tag(tg):
                    count_raw.append(tg)
                else:
                    general_raw.append(tg)
        else:
            artist_raw = _split_tags(artist_tags)
            character_raw = _split_tags(character_tags)
            ip_raw = _split_tags(ip_tags)
            general_raw = _split_tags(general_tags)
            count_raw = []

        # 1. 从 general 抽取计数标签
        extracted_count = [t for t in general_raw if _is_count_tag(t)]
        general_raw = [t for t in general_raw if not _is_count_tag(t)]
        count_raw = count_raw + extracted_count

        # 2. 质量框为空时自动填充模型预制词
        if not quality_meta or not quality_meta.strip():
            quality_meta = _QUALITY_PRESETS.get(model_type, "")

        # 3. 各分类格式转换
        q_tags = self._process_single(quality_meta, False, model_type, underscore_mode,
                                      escape_parens, artist_at_prefix, separator)
        c_tags = self._process_single(", ".join(count_raw), False, model_type, underscore_mode,
                                      escape_parens, artist_at_prefix, separator) if count_raw else []
        ch_tags = self._process_single(", ".join(character_raw), False, model_type, underscore_mode,
                                       escape_parens, artist_at_prefix, separator) if character_raw else []
        s_tags = self._process_single(", ".join(ip_raw), False, model_type, underscore_mode,
                                      escape_parens, artist_at_prefix, separator) if ip_raw else []
        a_tags = self._process_single(", ".join(artist_raw), True, model_type, underscore_mode,
                                      escape_parens, artist_at_prefix, separator) if artist_raw else []
        g_tags = self._process_single(", ".join(general_raw), False, model_type, underscore_mode,
                                      escape_parens, artist_at_prefix, separator) if general_raw else []

        # 3.5 作品角色（角色（作品）配对串）：来自 picker 的 CHARACTER_IP_NAMES
        # 填了则替代 character+ip 两段；开关仅作用于该段的全角括号，不影响其他段
        cip_raw = _split_tags(character_ip_names) if character_ip_names else []
        cip_tags = None
        if cip_raw:
            cip_tags = []
            for t in cip_raw:
                tt = t.strip()
                if not tt:
                    continue
                if escape_ip_parens:
                    tt = tt.replace("（", "\\（").replace("）", "\\）")
                cip_tags.append(tt)
            if not cip_tags:
                cip_tags = None

        # 4. 按模型模式拼接
        if model_type in ("Noob", "CKNoob"):
            # general 内部按子分类优先级重排
            if g_tags:
                cat_result, uncat = _classify_general(g_tags)
                tag_order = {}
                for cat_name, tags in cat_result.items():
                    pri = _NOOB_CAT_PRIORITY.get(cat_name, 0)
                    for t in tags:
                        tag_order[t] = pri
                for t in uncat:
                    tag_order[t] = 0
                g_sorted = sorted(g_tags, key=lambda t: tag_order.get(t, 0))
            else:
                g_sorted = []
            # 顺序：count → character → artist → general → quality
            ordered = []
            if c_tags:
                ordered.append(separator.join(c_tags))
            if cip_tags is not None:
                ordered.append(separator.join(cip_tags))
            elif ch_tags:
                ordered.append(separator.join(ch_tags))
            if a_tags:
                ordered.append(separator.join(a_tags))
            if g_sorted:
                ordered.append(separator.join(g_sorted))
            if q_tags:
                ordered.append(separator.join(q_tags))
        else:
            # Anima 顺序：quality → count → character → series → artist → general
            ordered = []
            if q_tags:
                ordered.append(separator.join(q_tags))
            if c_tags:
                ordered.append(separator.join(c_tags))
            if cip_tags is not None:
                ordered.append(separator.join(cip_tags))
            else:
                if ch_tags:
                    ordered.append(separator.join(ch_tags))
                if s_tags:
                    ordered.append(separator.join(s_tags))
            if a_tags:
                ordered.append(separator.join(a_tags))
            if g_tags:
                ordered.append(separator.join(g_tags))

        prompt = separator.join(ordered)
        return (prompt,)


# ─────────────────────────────────────────────────────────────────────────────
# 节点注册
# ─────────────────────────────────────────────────────────────────────────────
NODE_CLASS_MAPPINGS = {
    "NaibaAnimaFormatter": NaibaAnimaFormatter,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaAnimaFormatter": "Anima 格式转换器 (Naiba)",
}
