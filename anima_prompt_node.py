"""
Anima Prompt Node - 基于ANIMA3提示词生成模板的自定义提示词节点
从anima_prompts.json读取标签数据，支持分类选择、搜索和扭蛋功能
"""

import json
import os
import random
import time
from typing import Dict, List, Any, Optional, Tuple

# 导入ComfyUI基础库
try:
    import aiohttp
    from aiohttp import web
    import server
except Exception:  # pragma: no cover
    aiohttp = None
    web = None
    server = None

try:
    import folder_paths
except Exception:  # pragma: no cover
    folder_paths = None


class AnimaPromptNode:
    """Anima提示词节点"""
    
    # 节点属性
    CATEGORY = "naiba-node"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    OUTPUT_NODE = True
    
    # 数据文件路径
    DATA_FILE = os.path.join(os.path.dirname(__file__), "anima_prompts.json")
    
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入类型"""
        return {
            "required": {},
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "selection_data": ("STRING", {"default": "{}"}),
                "gacha_data": ("STRING", {"default": "{}"}),
            },
        }
    
    def __init__(self):
        """初始化节点"""
        self._data = None
        self._load_data()
    
    def _load_data(self):
        """加载标签数据"""
        try:
            if os.path.exists(self.DATA_FILE):
                with open(self.DATA_FILE, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                print(f"[AnimaPromptNode] 已加载标签数据：{sum(len(tags) for tags in self._data.values())} 个标签")
            else:
                print(f"[AnimaPromptNode] 警告：找不到数据文件 {self.DATA_FILE}")
                self._data = {}
        except Exception as e:
            print(f"[AnimaPromptNode] 加载数据失败: {e}")
            self._data = {}
    
    def _get_categories(self) -> List[str]:
        """获取所有分类"""
        if not self._data:
            return []
        return list(self._data.keys())
    
    def _get_tags_by_category(self, category: str, query: str = "", page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取指定分类的标签"""
        if not self._data or category not in self._data:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        
        tags = self._data[category]
        
        # 搜索过滤
        if query:
            query_lower = query.lower()
            filtered_tags = []
            for tag in tags:
                # 搜索英文标签和中文说明
                if (query_lower in tag.get("raw_en", "").lower() or 
                    query_lower in tag.get("cn_description", "").lower()):
                    filtered_tags.append(tag)
            tags = filtered_tags
        
        # 分页
        total = len(tags)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_tags = tags[start_idx:end_idx]
        
        return {
            "items": page_tags,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    def _gacha(self, category: str, count: int = 1) -> List[Dict[str, Any]]:
        """扭蛋：随机获取标签"""
        if not self._data or category not in self._data:
            return []
        
        tags = self._data[category]
        if not tags:
            return []
        
        # 随机选择标签
        selected = random.sample(tags, min(count, len(tags)))
        return selected
    
    def _format_tag(self, tag: Dict[str, Any]) -> str:
        """格式化标签为提示词字符串"""
        # 使用原始英文标签
        return tag.get("raw_en", "")
    
    # 路由函数
    def get_categories(self, _id: str, **kwargs) -> Dict[str, Any]:
        """获取分类列表"""
        categories = self._get_categories()
        return {"categories": categories}
    
    def get_tags(self, _id: str, category: str, query: str = "", page: int = 1, **kwargs) -> Dict[str, Any]:
        """获取标签列表"""
        return self._get_tags_by_category(category, query, page)
    
    def gacha(self, _id: str, category: str, count: int = 1, **kwargs) -> Dict[str, Any]:
        """扭蛋：随机获取标签"""
        tags = self._gacha(category, count)
        return {"tags": tags}
    
    # 主执行函数
    def execute(self, selection_data, gacha_data, unique_id) -> Tuple[str]:
        """主执行函数：生成提示词"""
        # 直接使用输入参数
        # selection_data 和 gacha_data 由前端通过widget传递
        
        # 解析选择数据
        selected_tags = []
        try:
            data = json.loads(selection_data)
            if "selected" in data:
                selected_tags = data["selected"]
        except:
            pass
        
        # 解析扭蛋数据
        gacha_tags = []
        try:
            data = json.loads(gacha_data)
            if "tags" in data:
                gacha_tags = data["tags"]
        except:
            pass
        
        # 合并标签
        all_tags = []
        
        # 添加选择的标签
        for tag_item in selected_tags:
            if isinstance(tag_item, dict):
                tag_str = self._format_tag(tag_item)
                if tag_str:
                    all_tags.append(tag_str)
            elif isinstance(tag_item, str):
                all_tags.append(tag_item)
        
        # 添加扭蛋标签
        for tag_item in gacha_tags:
            if isinstance(tag_item, dict):
                tag_str = self._format_tag(tag_item)
                if tag_str:
                    all_tags.append(tag_str)
            elif isinstance(tag_item, str):
                all_tags.append(tag_item)
        
        # 去重
        unique_tags = list(dict.fromkeys(all_tags))
        
        # 生成提示词
        prompt_text = ", ".join(unique_tags)
        
        return (prompt_text,)


# 路由注册
def register_routes():
    """注册API路由"""
    if server is None or web is None:
        return
    
    PromptServer = server.PromptServer.instance
    routes = PromptServer.routes
    
    @routes.get("/anima/prompt/categories")
    async def get_categories(request):
        """获取分类列表"""
        try:
            node = AnimaPromptNode()
            result = node.get_categories("0")
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    
    @routes.get("/anima/prompt/tags")
    async def get_tags(request):
        """获取标签列表"""
        try:
            category = request.query.get("category", "")
            query = request.query.get("query", "")
            page = int(request.query.get("page", "1"))
            
            node = AnimaPromptNode()
            result = node.get_tags("0", category, query, page)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    
    @routes.get("/anima/prompt/gacha")
    async def gacha(request):
        """扭蛋：随机获取标签"""
        try:
            category = request.query.get("category", "")
            count = int(request.query.get("count", "1"))
            
            node = AnimaPromptNode()
            result = node.gacha("0", category, count)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)


# 初始化路由
try:
    register_routes()
except Exception as e:
    print(f"[anima_prompt_node] register_routes error: {e}")


# 节点映射
NODE_CLASS_MAPPINGS = {
    "AnimaPromptNode": AnimaPromptNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AnimaPromptNode": "Anima Prompt Node"
}