import json
import re

with open('anima_prompts.json', 'r', encoding='utf-8') as f:
    original = f.read()

# Restore original first
with open('anima_prompts_backup.json', 'w', encoding='utf-8') as f:
    f.write(original)

data = json.loads(original)

# Manual overrides for entries where auto-split doesn't work well
MANUAL_MAP = {
    # "cn_description" -> {tag: cn} mapping
    "一男一女, 异性": {
        "1girl": "一女",
        "1boy": "一男",
        "hetero": "异性"
    },
    "男娘/伪娘": {
        "otoko no ko": "男娘",
        "femboy": "伪娘",
        "trap": "伪娘"
    },
    "巨乳/大乳": {
        "large breasts": "巨乳"
    },
    "贫乳/平胸/萝莉": {
        "flat breasts": "贫乳/平胸",
        "loli": "萝莉"
    },
    "高光紧身胶衣/第二皮肤": {
        "latex bodysuit": "高光紧身胶衣",
        "shiny": "高光质感",
        "second skin": "第二皮肤"
    },
    "一女, 单人": {
        "1girl": "一女",
        "solo": "单人"
    },
    "两女, 百合": {
        "2girls": "两女",
        "yuri": "百合"
    },
    "螺旋眼/晕厥眼/失神空洞眼": {
        "spiral eyes": "螺旋眼",
        "@\\_@": "晕厥眼",
        "empty eyes": "失神空洞眼"
    },
    "蕾丝情趣内衣/束腰/吊带袜": {
        "lace lingerie": "蕾丝情趣内衣",
        "corset": "束腰",
        "garter belt": "吊带袜"
    },
    "眼罩/蒙眼": {
        "blindfold": "眼罩/蒙眼"
    },
    "half-dressed 半脱衣物/身体半裸": {
        "partially undressed": "半脱衣物"
    },
    "see-through 湿透的衣物/激凸透视": {
        "wet clothes": "湿透衣物/透视"
    },
    "can't move 痴汉/揉乳摸臀/电车无法动弹": {
        "chikan": "痴汉",
        "groping": "揉乳摸臀"
    },
    "strap-on 女反攻后入/假阳具绑带": {
        "pegging": "女攻后入"
    },
    "full-face blush 潮红/全脸大爆红": {
        "blush": "潮红/脸红"
    },
    "close-up 极致特写 (局部细节)": {
        "extreme": "极致特写"
    },
    "top-down view 俯视角度 (传教士压迫)": {
        "from above": "俯视角度"
    },
    "前后夹击/2男前后同入 (多人)": {
        "spitroast": "前后夹击",
        "2boys": "2男",
        "group sex": "多人群交"
    },
    "三穴同入/3男轮奸 (极深RBQ)": {
        "triple penetration": "三穴同入",
        "3boys": "3男"
    },
    "卧室/床上/床单 (安全私密)": {
        "bedroom": "卧室",
        "on bed": "床上",
        "bed sheet": "床单"
    },
    "浴室/花洒下/浴缸/蒸汽 (湿滑)": {
        "bathroom": "浴室",
        "shower": "花洒",
        "bathtub": "浴缸",
        "steam": "蒸汽"
    },
    "地牢/石墙/镣铐铁链 (束缚调教)": {
        "dungeon": "地牢",
        "stone wall": "石墙",
        "chains": "镣铐铁链"
    },
    "办公室/办公桌底/转椅 (加班胁迫)": {
        "office": "办公室",
        "desk": "办公桌",
        "office chair": "转椅"
    },
    "电车/挤爆的电车/拉手 (痴汉)": {
        "train": "电车",
        "crowded train": "挤满的电车",
        "handrail": "拉手"
    },
    "商场试衣间/布帘/试衣镜": {
        "fitting room": "试衣间",
        "curtain": "布帘",
        "mirror": "镜子"
    },
    "公园长椅/户外 (大露特露)": {
        "park": "公园",
        "park bench": "公园长椅",
        "outdoors": "户外"
    },
    "温泉/桑拿热汽/木桶浴": {
        "onsen": "温泉",
        "steam": "蒸汽",
        "wooden bath": "木桶浴"
    },
    "在窗边贴着玻璃/城市夜景 (窗外偷窥)": {
        "against window": "贴窗",
        "glass": "玻璃",
        "city view": "城市夜景"
    },
    "下雨/下雪/大雾/物理蒸汽 (可用环境)": {
        "rain": "下雨",
        "snow": "下雪",
        "fog": "大雾",
        "steam": "蒸汽"
    },
    "催眠/空眼/僵尸站姿 (催眠play)": {
        "hypnosis": "催眠",
        "spiral eyes": "螺旋眼",
        "zombie pose": "僵尸站姿"
    },
    "睡眠/无意识 (睡奸体位)": {
        "sleeping": "睡眠",
        "closed eyes": "闭眼",
        "zzz": "入睡符号"
    },
    "景深虚化背景/光斑 (浪漫特写)": {
        "depth of field": "景深",
        "shallow depth of field": "浅景深虚化",
        "bokeh": "光斑"
    },
    "数字故障艺术/CRT录像带噪点 (偷拍催眠)": {
        "digital glitch effects": "数字故障艺术",
        "VHS distortion": "VHS录像带噪点"
    },
    "男方视角/双手入镜/第一人称胯部": {
        "pov": "第一人称视角",
        "pov hands": "双手入镜",
        "pov crotch": "第一人称胯部"
    },
    "扼喉/窒息/粗暴猛烈性爱 (过激)": {
        "strangling": "扼喉",
        "asphyxiation": "窒息",
        "rough sex": "粗暴性爱"
    },
    "磨镜/百合私处纯磨擦 (百合)": {
        "tribadism": "磨镜",
        "scissoring": "剪刀式",
        "pussy to pussy": "私处对磨"
    },
    "高潮反应/反弓腰/脚趾抓地": {
        "orgasm": "高潮",
        "arched back": "反弓腰",
        "toes curling": "脚趾蜷缩"
    },
    "前列腺液/体内射精/内射灌满": {
        "precum": "前列腺液",
        "cum inside": "体内射精",
        "creampie": "内射灌满"
    },
    "精液漫出/精液滴落/浓稠拉丝": {
        "cum overflow": "精液漫出",
        "cum drip": "精液滴落",
        "cum string": "浓稠拉丝"
    },
    "勒痕/红印/绳缚痕迹 (真实细节)": {
        "rope marks": "绳痕",
        "red marks": "红印",
        "skindentation": "勒痕"
    },
    "口交/深喉/窒息呕吐感": {
        "blowjob": "口交",
        "deepthroat": "深喉",
        "gagging": "窒息呕吐感"
    },
    "呻吟/喘息/粗重急促的呼吸": {
        "moaning": "呻吟",
        "panting": "喘息",
        "heavy breathing": "粗重呼吸"
    },
    "阿黑颜/吐舌头/流口水 (失神)": {
        "ahegao": "阿黑颜",
        "tongue out": "吐舌头",
        "drooling": "流口水"
    },
    "害羞/内疚羞耻/面部遮挡": {
        "shy": "害羞",
        "embarrassed": "羞耻",
        "ashamed": "内疚"
    },
    "漫画式运动抽插线/速度线 (激烈活塞)": {
        "motion lines": "运动线",
        "speed lines": "速度线"
    },
}


def split_cn_description(cn_desc, tags):
    """Split Chinese description to match tags 1:1."""
    tag_count = len(tags)

    # Check manual overrides first
    if cn_desc in MANUAL_MAP:
        mapping = MANUAL_MAP[cn_desc]
        results = []
        for tag in tags:
            if tag in mapping:
                results.append(mapping[tag])
            else:
                results.append(cn_desc)
        return results

    # Clean the description
    clean = cn_desc.strip()

    # Remove trailing parenthetical notes for splitting purposes
    trailing_note = ""
    paren_match = re.search(r'\s*\(([^)]+)\)\s*$', clean)
    if paren_match:
        trailing_note = paren_match.group(0).strip()
        clean = clean[:paren_match.start()].strip()

    # Remove leading English annotations
    en_prefix_match = re.match(r'^([a-zA-Z][a-zA-Z\s\-\'\.]*)\s+', clean)
    if en_prefix_match:
        clean = clean[en_prefix_match.end():]

    # Try splitting by "/"
    parts = [p.strip() for p in clean.split('/')]

    if len(parts) == tag_count:
        return parts

    # Try splitting by ", " (Chinese comma or regular comma)
    if len(parts) < tag_count:
        parts = [p.strip() for p in re.split(r'[,，]\s*', clean)]
        if len(parts) == tag_count:
            return parts

    # If still doesn't match, use full description for each
    if len(parts) != tag_count:
        return [clean] * tag_count

    return parts


def process_entry(entry):
    """Split a multi-tag entry into individual entries."""
    tags = entry['en_tags']
    cn = entry['cn_description']

    if len(tags) <= 1:
        return [entry]

    cn_parts = split_cn_description(cn, tags)

    results = []
    for i, tag in enumerate(tags):
        new_entry = {
            "en_tags": [tag],
            "cn_description": cn_parts[i],
            "raw_en": tag
        }
        results.append(new_entry)

    return results


# Process all categories
new_data = {}
for category, entries in data.items():
    new_entries = []
    for entry in entries:
        split_entries = process_entry(entry)
        new_entries.extend(split_entries)
    new_data[category] = new_entries

with open('anima_prompts.json', 'w', encoding='utf-8') as f:
    json.dump(new_data, f, ensure_ascii=False, indent=2)

print("Done! Split complete.")
for cat, entries in new_data.items():
    print(f"  {cat}: {len(entries)} entries")

# Show some examples to verify
print("\n--- Sample entries ---")
all_entries = new_data["全库标签"]
for e in all_entries[:12]:
    print(f"  {e['en_tags'][0]:25s} → {e['cn_description']}")
print("  ...")
for e in all_entries[30:40]:
    print(f"  {e['en_tags'][0]:25s} → {e['cn_description']}")
