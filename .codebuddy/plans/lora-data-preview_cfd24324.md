---
name: lora-data-preview
overview: 创建Lora Data Preview节点，从Civitai自动同步LoRA封面图片和元数据，支持NSFW过滤和缓存
design:
  architecture:
    framework: html
  styleKeywords:
    - Minimalism
    - Dark
    - Functional
  fontSystem:
    fontFamily: system-ui
    heading:
      size: 18px
      weight: 600
    subheading:
      size: 14px
      weight: 500
    body:
      size: 12px
      weight: 400
  colorSystem:
    primary:
      - "#6c5ce7"
      - "#7c6cf7"
    background:
      - "#1a1a2e"
      - "#16213e"
      - "#0f1729"
    text:
      - "#e0e0e0"
      - "#888888"
    functional:
      - "#2ed573"
      - "#ff6b6b"
      - "#ffa502"
todos:
  - id: explore-codebase
    content: 使用 [subagent:code-explorer] 探索项目结构，分析现有实现模式
    status: completed
  - id: create-civitai-utils
    content: 创建civitai_utils.py，实现Civitai API客户端工具类
    status: completed
    dependencies:
      - explore-codebase
  - id: create-lora-preview-node
    content: 创建lora_data_preview.py节点，实现核心业务逻辑
    status: completed
    dependencies:
      - create-civitai-utils
  - id: modify-preset-routes
    content: 修改preset_routes.py，添加Civitai同步API路由
    status: completed
    dependencies:
      - create-lora-preview-node
  - id: update-init-py
    content: 修改__init__.py，注册新节点到NODE_CLASS_MAPPINGS
    status: completed
    dependencies:
      - modify-preset-routes
  - id: enhance-frontend
    content: 增强前端JS，支持自动触发Civitai同步和预览显示
    status: completed
    dependencies:
      - update-init-py
  - id: test-integration
    content: 测试完整流程，验证预览图是否可用于visual lora loader
    status: completed
    dependencies:
      - enhance-frontend
---

## 产品概述

一个LoRA数据预览节点，能够从Civitai自动同步封面图片和元数据，支持通过SHA256哈希值查询、自动下载预览图、NSFW级别过滤和元数据缓存功能。

## 核心功能

- 通过LoRA文件的SHA256哈希值向Civitai API（red区）查询模型信息和预览图片
- 自动下载预览图片保存到LoRA文件同目录（.preview.webp格式）
- 在前端弹窗中，当本地无预览图时自动触发Civitai封面获取
- 支持NSFW级别过滤（跳过过高NSFW级别的图片）
- 缓存已获取的元数据，避免重复请求
- 验证封面图片是否可以用于visual lora loader

## 技术栈选择

- **后端**: Python + aiohttp（项目中已有使用）
- **前端**: 复用现有visual_lora_loader.js或创建新的JS扩展
- **存储**: JSON文件缓存元数据
- **API**: Civitai red区API（`https://civitai.red/api/v1`）
- **依赖**: ComfyUI基础库、hashlib、aiohttp、json、os

## 实现方案

### 系统架构

采用模块化设计，将核心功能分离为独立的工具类，通过API路由与前端交互。后端负责SHA256计算、API查询、图片下载和缓存管理，前端负责触发同步和显示预览。

### 关键技术决策

1. **使用aiohttp进行异步HTTP请求**：项目中已有aiohttp依赖，保持一致性
2. **JSON文件缓存**：简单可靠，避免引入额外依赖
3. **NSFW过滤算法**：参考comfyui-lora-manager的实现，优先选择安全图片
4. **API路由设计**：添加新的API端点支持Civitai同步和元数据获取

### 性能考虑

- 使用异步IO避免阻塞主线程
- 实现元数据缓存减少重复API请求
- 限制并发请求数量避免触发Civitai速率限制

## 实现细节

### 核心目录结构

```
naiba-test/
├── lora_data_preview.py          # [NEW] LoRA数据预览节点主文件
├── civitai_utils.py              # [NEW] Civitai API工具类
├── preset_routes.py              # [MODIFY] 添加Civitai同步API路由
├── __init__.py                   # [MODIFY] 注册新节点
└── js/
    ├── lora_data_preview.js      # [NEW] 前端JS扩展（可选）
    └── visual_lora_loader.js     # [MODIFY] 增强预览获取逻辑
```

### 关键接口设计

```python
# civitai_utils.py
class CivitaiClient:
    async def query_by_hash(self, file_hash: str) -> dict
    async def download_preview(self, image_url: str, save_path: str) -> bool
    def select_preview_image(self, images: list, max_nsfw_level: int) -> dict
    def calculate_sha256(self, file_path: str) -> str

# lora_data_preview.py
class LoraDataPreview:
    def get_lora_data(self, lora_name: str, nsfw_level: str, auto_sync: bool) -> tuple
```

### 数据流

1. 前端请求LoRA预览 → 后端检查本地预览文件
2. 如果本地无预览 → 调用Civitai同步API
3. 计算SHA256哈希 → 查询Civitai API
4. 选择合适预览图（NSFW过滤） → 下载并保存
5. 返回预览图路径给前端

## 设计风格

采用现代简约设计，与现有naiba节点保持一致的深色主题。界面简洁实用，专注于功能实现而非华丽视觉效果。

## 设计内容

- **主题**: 深色主题，与ComfyUI界面协调
- **布局**: 简洁的卡片式布局，信息层次清晰
- **交互**: 微动画提升用户体验，状态反馈明确
- **响应式**: 适配不同屏幕尺寸

## 代理扩展

### SubAgent

- **code-explorer**
- 用途：探索代码库结构，分析现有实现模式
- 预期结果：获得项目架构理解和实现参考