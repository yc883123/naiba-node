---
name: civitai-info-reader-node
overview: 创建一个新节点，用于读取 LoRA 文件对应的 .civitai.info.json 元数据，并输出模型名称、描述、触发词、预览图片等信息。
todos:
  - id: create-node-file
    content: 创建 civitai_info_reader.py 节点文件，实现 CivitaiInfoReader 类
    status: completed
  - id: implement-input-types
    content: 实现 INPUT_TYPES，从 folder_paths 获取 LoRA 文件列表作为下拉选项
    status: completed
    dependencies:
      - create-node-file
  - id: implement-file-finding
    content: 实现 .civitai.info.json 文件查找逻辑
    status: completed
    dependencies:
      - create-node-file
  - id: implement-json-parsing
    content: 实现 JSON 元数据解析和字段提取
    status: completed
    dependencies:
      - implement-file-finding
  - id: implement-image-loading
    content: 实现预览图加载和 IMAGE tensor 转换
    status: completed
    dependencies:
      - create-node-file
  - id: define-return-types
    content: 定义完整的 RETURN_TYPES 和 RETURN_NAMES 输出端口
    status: completed
    dependencies:
      - implement-json-parsing
      - implement-image-loading
  - id: register-node
    content: 在 __init__.py 中注册新节点的 NODE_CLASS_MAPPINGS
    status: completed
    dependencies:
      - create-node-file
  - id: test-node
    content: 测试节点功能，验证所有输出端口正常工作
    status: completed
    dependencies:
      - register-node
---

## 产品概述

创建一个新的 ComfyUI 自定义节点 `CivitaiInfoReader`，用于读取 LoRA 模型对应的 `.civitai.info.json` 元数据文件，并将其中的各项信息分别输出，方便在工作流中使用。

## 核心功能

- **LoRA 文件选择**: 通过下拉菜单选择 LoRA 文件，自动查找对应的 `.civitai.info.json` 文件
- **图片输出**: 读取本地预览图，转换为 ComfyUI IMAGE tensor 格式输出
- **元数据输出**: 分别输出模型名称、触发词、模型介绍、基础模型、版本名称、模型类型、评分、下载量、NSFW 级别等信息
- **原始 JSON 输出**: 输出完整的原始 JSON 字符串，供其他节点使用

## 技术栈

- **语言**: Python 3.x
- **框架**: ComfyUI 节点开发框架
- **依赖库**: 
- `torch` (tensor 处理)
- `PIL/Pillow` (图片加载)
- `numpy` (数组转换)
- `json` (JSON 解析)
- `folder_paths` (ComfyUI 路径工具)

## 技术架构

### 系统架构

节点采用单文件独立实现，复用现有 `civitai_utils.py` 的工具函数，遵循项目现有的节点开发模式。

### 数据流

```mermaid
graph LR
    A[LoRA 文件名] --> B[查找 .civitai.info.json]
    B --> C[解析 JSON 元数据]
    C --> D[提取各字段]
    C --> E[加载预览图]
    E --> F[转换为 IMAGE tensor]
    D --> G[输出各类型数据]
    F --> G
```

### 实现方案

1. **文件查找**: 使用 `folder_paths.get_full_path("loras", lora_name)` 获取 LoRA 路径，替换扩展名为 `.civitai.info.json`
2. **元数据加载**: 使用 `civitai_utils.load_cached_metadata()` 读取 JSON
3. **图片加载**: 使用 PIL 打开图片，转换为 numpy 数组，再转为 torch tensor (BHWC, float32, 0-1)
4. **输出定义**: 使用多种 RETURN_TYPES（IMAGE、STRING、INT、FLOAT、BOOLEAN）

### 性能考虑

- 图片加载后缓存在内存中，避免重复读取
- JSON 解析使用标准库，性能开销可忽略
- 图片转换使用 numpy 向量化操作，效率高

## 实现细节

### 关键代码结构

```python
class CivitaiInfoReader:
    @classmethod
    def INPUT_TYPES(cls):
        # 从 folder_paths 获取 LoRA 文件列表
        loras = folder_paths.get_filename_list("loras")
        return {
            "required": {
                "lora_name": (loras, {"tooltip": "选择 LoRA 文件"}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "STRING", ...)
    RETURN_NAMES = ("image", "model_name", "trigger_words", "description", ...)
    FUNCTION = "read_info"
    CATEGORY = "naiba-node"
```

### 图片转换逻辑

```python
from PIL import Image
import numpy as np
import torch

def load_image_as_tensor(image_path):
    img = Image.open(image_path).convert("RGB")
    img_array = np.array(img).astype(np.float32) / 255.0
    tensor = torch.from_numpy(img_array)[None,]  # 添加 batch 维度 -> (1, H, W, C)
    return tensor
```

### 路径安全

- 使用 `os.path.exists()` 验证文件存在
- 使用 `os.path.realpath()` 防止路径遍历