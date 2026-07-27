"""
Naiba Textbox 节点 - 独立的字符串输入/透传/预览/输出节点
提供一个可编辑的字符串输入框，并带一个 passthrough 输入端口。
开关开启时，上游字符串（包括空字符串）传入 passthrough 后覆盖输入框；
开关关闭或 passthrough 未连接时使用输入框；结果在节点内预览并向下游输出。
完全自实现，不依赖任何外部节点模块。
"""

class NaibaTextbox:
    """
    文本盒子节点：
    - text：可编辑的多行字符串输入（通过 print_to_screen 直接在节点体内预览/编辑）
    - allow_passthrough_override：控制 passthrough 是否可以覆盖输入框内容
    - passthrough：可选 STRING 输入端口，允许覆盖时采用上游传入的内容（包括空字符串）
    - 输出：最终字符串
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "forceInput": False,
                        "print_to_screen": True,
                    },
                ),
                "allow_passthrough_override": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "允许覆盖",
                        "label_off": "禁止覆盖",
                    },
                ),
            },
            "optional": {
                "passthrough": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "forceInput": True,
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    OUTPUT_NODE = True
    FUNCTION = "textbox"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "文本盒子节点 - 提供可编辑的字符串输入框，并带一个 passthrough 输入端口。\n"
        "开启开关时，passthrough 输入（包括空字符串）会覆盖文本框；关闭时忽略 passthrough。\n"
        "节点体内直接预览/编辑字符串，并向下游输出该字符串。"
    )
    SEARCH_ALIASES = ["naiba", "textbox", "text", "string", "passthrough"]

    def textbox(self, text="", allow_passthrough_override=True, passthrough=None):
        # None 表示端口未连接；空字符串则是有效的上游输入，可用于清空文本框。
        if allow_passthrough_override and passthrough is not None:
            text = passthrough
            return {
                "ui": {"text": text},
                "result": (text,),
            }
        return (text,)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "NaibaTextbox": NaibaTextbox,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaTextbox": "Naiba Textbox",
}
