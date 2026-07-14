"""
Save Text File - 保存文本内容到文件的节点
"""

import os


class SaveTextFile:
    """
    将文本内容保存到指定文件路径
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "forceInput": True,
                    "tooltip": "要保存的文本内容（连接其他节点的输出）"
                }),
                "file_path": ("STRING", {
                    "default": "",
                    "tooltip": "保存文件的完整路径（如 D:\\output\\data.json）"
                }),
            },
            "optional": {
                "filename": ("STRING", {
                    "default": "output.json",
                    "tooltip": "文件名（如果 file_path 已包含文件名则忽略此项）"
                }),
                "auto_mkdir": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "自动创建目录（如果目录不存在）"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_path",)
    FUNCTION = "save_file"
    CATEGORY = "naiba-node"
    DESCRIPTION = (
        "保存文本内容到指定文件路径。\n"
        "支持自动创建目录。"
    )
    SEARCH_ALIASES = ["naiba", "save", "file", "export", "保存", "导出"]
    OUTPUT_NODE = True
    
    def save_file(self, text, file_path, filename="output.json", auto_mkdir=True):
        """保存文本到文件"""
        
        # 确定最终文件路径
        if not file_path.strip():
            return ("",)
        
        # 如果 file_path 是目录，添加文件名
        if os.path.isdir(file_path):
            final_path = os.path.join(file_path, filename)
        elif not file_path.lower().endswith(('.txt', '.json', '.csv', '.xml', '.yaml', '.yml', '.md')):
            # 如果没有常见扩展名，可能是目录路径
            if file_path.endswith(('\\', '/')):
                final_path = os.path.join(file_path, filename)
            else:
                final_path = file_path
        else:
            final_path = file_path
        
        try:
            # 自动创建目录
            if auto_mkdir:
                output_dir = os.path.dirname(final_path)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
            
            # 写入文件
            with open(final_path, 'w', encoding='utf-8') as f:
                f.write(text)
            
            print(f"[SaveTextFile] 已保存到: {final_path}")
            return (final_path,)
            
        except Exception as e:
            print(f"[SaveTextFile] 保存失败: {e}")
            return ("",)


# 节点注册
NODE_CLASS_MAPPINGS = {
    "SaveTextFile": SaveTextFile
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveTextFile": "Save Text File"
}
