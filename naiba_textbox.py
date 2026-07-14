"""
Naiba Textbox 节点 - 独立的字符串输入/透传/预览/输出节点
提供一个可编辑的字符串输入框，并带一个 passthrough 输入端口。
上游字符串传入 passthrough 后采用其值，否则使用输入框；结果在节点内预览并向下游输出。
完全自实现，不依赖任何外部节点模块。
"""

class NaibaTextbox:
    """
    文本盒子节点：
    - text：可编辑的多行字符串输入（通过 print_to_screen 直接在节点体内预览/编辑）
    - passthrough：可选 STRING 输入端口，上游传入后覆盖输入框内容
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
        "上游字符串传入 passthrough 后自动采用其值，否则使用下方输入框。\n"
        "节点体内直接预览/编辑字符串，并向下游输出该字符串。"
    )
    SEARCH_ALIASES = ["naiba", "textbox", "text", "string", "passthrough"]

    def textbox(self, text="", passthrough=""):
        # passthrough 端口有传入且非空时，采用上游值，并通过 ui 回显到预览框
        if passthrough is not None and passthrough != "":
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
