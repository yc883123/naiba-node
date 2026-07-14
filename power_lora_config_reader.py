"""
Power LoRA Config Reader 节点
读取画布上 LoRA 加载器节点的 LoRA 配置，转换为 naiba 预设格式

支持的上游节点：
- rgthree Power Lora Loader (RgthreePowerLoraLoader)
- rgthree Lora Loader Stack (RgthreeLoraLoaderStack)
- naiba MultiLoraLoader
- naiba MultiLoraLoaderOnlyModel
- ComfyUI 内置 LoraLoader（单个LoRA）
- 任何包含 lora_* 字典输入的节点
"""

import json


class PowerLoraConfigReader:
    """
    读取上游 LoRA 加载器的配置，输出 naiba 预设格式 JSON

    用法：
    1. 将此节点的 MODEL 输入连接到上游 LoRA 加载器的 MODEL 输出
    2. （可选）将 CLIP 输入连接到上游 LoRA 加载器的 CLIP 输出
    3. preset_json 输出口输出预设配置 JSON（可保存为 .json 预设文件）
    4. lora_names 输出口输出启用的 LoRA 文件名列表
    5. status 输出口输出读取状态信息
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL", {"tooltip": "连接上游 LoRA 加载器的 MODEL 输出"}),
            },
            "optional": {
                "clip": ("CLIP", {"tooltip": "连接上游 LoRA 加载器的 CLIP 输出（可选）"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("preset_json", "lora_names", "status")
    FUNCTION = "read_config"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "读取上游 LoRA 加载器的配置信息，转换为 naiba 预设格式。\n"
        "支持 rgthree Power Lora Loader、Lora Stack、naiba MultiLoraLoader 等。\n"
        "连接 MODEL（必需）和 CLIP（可选）到上游加载器的输出即可。\n"
        "preset_json 输出可直接保存为 .json 预设文件。"
    )
    SEARCH_ALIASES = [
        "naiba", "lora config", "lora reader", "lora preset",
        "配置读取", "预设转换", "power lora"
    ]

    def read_config(self, model, clip=None, prompt=None, unique_id=None):
        """读取上游 LoRA 加载器的配置并转换为预设格式"""

        if prompt is None:
            return self._empty_output("无法获取画布数据（prompt 为空）")

        # 定位当前节点
        our_node_id = self._find_our_node_id(prompt, unique_id)
        if our_node_id is None:
            return self._empty_output("无法在画布中定位当前节点")

        # 获取当前节点的输入
        our_inputs = prompt[our_node_id].get("inputs", {})

        # 追踪 model 输入的来源节点
        model_link = our_inputs.get("model")
        if not isinstance(model_link, list) or len(model_link) < 2:
            return self._empty_output("MODEL 输入未连接到任何上游节点")

        source_node_id = str(model_link[0])
        source_node = prompt.get(source_node_id)

        if source_node is None:
            return self._empty_output(f"找不到上游节点 (ID: {source_node_id})")

        class_type = source_node.get("class_type", "")
        source_inputs = source_node.get("inputs", {})

        # 根据节点类型解析 LoRA 配置
        configs = self._parse_lora_configs(class_type, source_inputs)

        if not configs:
            return self._empty_output(
                f"节点 [{class_type}] 中未找到 LoRA 配置，"
                "请确认连接的是 LoRA 加载器节点"
            )

        # 转换为 naiba 预设格式
        preset_configs = []
        for cfg in configs:
            preset_configs.append({
                "name": cfg["name"],
                "strength_model": cfg["strength_model"],
                "strength_clip": cfg["strength_clip"],
                "enabled": cfg["enabled"],
            })

        # 生成输出
        preset_json = json.dumps(preset_configs, ensure_ascii=False, indent=2)

        enabled_configs = [c for c in preset_configs if c["enabled"]]
        lora_names = json.dumps(
            [c["name"] for c in enabled_configs],
            ensure_ascii=False,
        )

        total = len(preset_configs)
        enabled_count = len(enabled_configs)
        status = (
            f"从 [{class_type}] 读取到 {total} 个 LoRA"
            f"（{enabled_count} 个启用，{total - enabled_count} 个禁用）"
        )

        return (preset_json, lora_names, status)

    def _find_our_node_id(self, prompt, unique_id):
        """在 prompt 中定位当前节点的 ID"""
        # 优先使用 UNIQUE_ID 精确匹配
        if unique_id is not None:
            uid = str(unique_id)
            for node_id, node_data in prompt.items():
                if str(node_id) == uid:
                    return node_id

        # 回退：通过 class_type 查找
        for node_id, node_data in prompt.items():
            if node_data.get("class_type") == "PowerLoraConfigReader":
                return node_id

        return None

    def _parse_lora_configs(self, class_type, inputs):
        """根据节点类型解析 LoRA 配置"""

        # rgthree Power Lora Loader
        # 输入格式: lora_X = {"on": bool, "lora": str, "strength": float, "strengthTwo": float}
        if "PowerLoraLoader" in class_type or "Power Lora" in class_type:
            return self._parse_rgthree_power_lora(inputs)

        # rgthree Lora Loader Stack
        # 输入格式: lora_01=str, strength_01=float, lora_02=str, strength_02=float, ...
        if "LoraStack" in class_type or "Lora Loader Stack" in class_type:
            return self._parse_rgthree_lora_stack(inputs)

        # naiba MultiLoraLoader / MultiLoraLoaderOnlyModel
        # 输入格式: lora_data = JSON 字符串
        if class_type in ("MultiLoraLoader", "MultiLoraLoaderOnlyModel"):
            return self._parse_naiba_multi_lora(inputs)

        # ComfyUI 内置 LoraLoader（单个 LoRA）
        if class_type == "LoraLoader":
            return self._parse_builtin_lora_loader(inputs)

        # 通用解析：尝试从任何包含 lora 相关输入的节点提取配置
        configs = self._parse_generic_lora_inputs(inputs)
        if configs:
            return configs

        return []

    def _parse_rgthree_power_lora(self, inputs):
        """解析 rgthree Power Lora Loader 的输入"""
        configs = []
        for key, value in inputs.items():
            # 跳过非 lora_ 开头的输入和链接
            if not key.lower().startswith("lora_"):
                continue
            if not isinstance(value, dict):
                continue
            if "lora" not in value or "strength" not in value:
                continue

            lora_name = value.get("lora", "")
            if not lora_name:
                continue

            enabled = bool(value.get("on", True))
            strength_model = float(value.get("strength", 1.0))
            # strengthTwo 是 CLIP 强度，如果不存在则与 model 强度相同
            strength_clip = float(value.get("strengthTwo", strength_model))

            configs.append({
                "name": lora_name,
                "strength_model": strength_model,
                "strength_clip": strength_clip,
                "enabled": enabled,
            })

        return configs

    def _parse_rgthree_lora_stack(self, inputs):
        """解析 rgthree Lora Loader Stack 的输入"""
        configs = []
        for i in range(1, 20):  # 支持最多20个槽位
            lora_key = f"lora_{i:02d}"
            if lora_key not in inputs:
                # 也尝试不带前导零的格式
                lora_key = f"lora_{i}"
                if lora_key not in inputs:
                    continue

            lora_name = inputs.get(lora_key, "None")
            if not lora_name or lora_name == "None":
                continue

            # 查找对应的 strength 键
            strength = 1.0
            for skey in [f"strength_{i:02d}", f"strength_{i}"]:
                if skey in inputs:
                    strength = float(inputs[skey])
                    break

            configs.append({
                "name": lora_name,
                "strength_model": strength,
                "strength_clip": strength,  # Stack 通常 model 和 clip 强度相同
                "enabled": strength != 0,
            })

        return configs

    def _parse_naiba_multi_lora(self, inputs):
        """解析 naiba MultiLoraLoader 的输入"""
        lora_data_str = inputs.get("lora_data", "[]")

        # 如果是链接（列表），说明连接了其他节点的输出，无法直接解析
        if isinstance(lora_data_str, list):
            return []

        try:
            loras = json.loads(lora_data_str) if lora_data_str else []
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(loras, list):
            return []

        configs = []
        for item in loras:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            if not name:
                continue
            configs.append({
                "name": name,
                "strength_model": float(item.get("strength_model", 1.0)),
                "strength_clip": float(item.get("strength_clip", 1.0)),
                "enabled": bool(item.get("enabled", True)),
            })

        return configs

    def _parse_builtin_lora_loader(self, inputs):
        """解析 ComfyUI 内置 LoraLoader 的输入"""
        lora_name = inputs.get("lora_name", "")
        if not lora_name or lora_name == "None":
            return []

        return [{
            "name": lora_name,
            "strength_model": float(inputs.get("strength_model", 1.0)),
            "strength_clip": float(inputs.get("strength_clip", 1.0)),
            "enabled": True,
        }]

    def _parse_generic_lora_inputs(self, inputs):
        """通用解析：从任何节点的输入中提取 LoRA 配置"""
        configs = []
        seen_names = set()

        for key, value in inputs.items():
            # 方式1: 字典格式 {"lora": "...", "strength": ..., "on": ...}
            if isinstance(value, dict) and "lora" in value:
                lora_name = value.get("lora", "")
                if lora_name and lora_name not in seen_names:
                    seen_names.add(lora_name)
                    strength = float(value.get("strength", 1.0))
                    configs.append({
                        "name": lora_name,
                        "strength_model": strength,
                        "strength_clip": float(value.get("strengthTwo", strength)),
                        "enabled": bool(value.get("on", value.get("enabled", True))),
                    })

            # 方式2: 字符串格式且键名包含 lora（可能是 LoRA 文件名）
            elif isinstance(value, str) and "lora" in key.lower():
                if value and value != "None" and value not in seen_names:
                    seen_names.add(value)
                    # 尝试查找对应的 strength
                    strength_key = key.replace("lora", "strength").replace("name", "")
                    strength = float(inputs.get(strength_key, 1.0))
                    configs.append({
                        "name": value,
                        "strength_model": strength,
                        "strength_clip": strength,
                        "enabled": strength != 0,
                    })

        return configs

    def _empty_output(self, status):
        """返回空输出"""
        return ("[]", "[]", status)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "PowerLoraConfigReader": PowerLoraConfigReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PowerLoraConfigReader": "Power LoRA Config Reader",
}
