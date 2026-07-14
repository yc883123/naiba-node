---
name: visual-lora-favorites-tab
overview: 在 Visual LoRA Loader 弹窗中添加收藏标签页，与 Lora Data Preview 共享收藏数据
todos:
  - id: add-favorites-tab
    content: 在 visual_lora_loader.js 中添加颜色常量、收藏状态变量和收藏 API 函数
    status: completed
  - id: modify-sidebar-tabs
    content: 修改 renderFolderTree() 添加"收藏"标签页和收藏视图
    status: completed
    dependencies:
      - add-favorites-tab
  - id: add-heart-button
    content: 在网格和列表视图的卡片上添加心形收藏按钮和橙色边框
    status: completed
    dependencies:
      - add-favorites-tab
  - id: filter-favorites-view
    content: 修改 renderLoraList() 支持收藏视图过滤，完成初始化加载
    status: completed
    dependencies:
      - modify-sidebar-tabs
      - add-heart-button
---

## 需求概述

为 Visual LoRA Loader 节点的弹窗模态框添加"收藏"标签页，实现"全部/已选择/收藏"三标签切换，并且收藏数据与 Lora Data Preview 节点保持一致（共用同一套收藏 API 和存储）。

## 核心功能

- Visual LoRA Loader 弹窗左侧标签栏新增"收藏"标签
- 点击"收藏"标签显示所有已收藏的 LoRA
- 每个 LoRA 卡片右上角显示心形收藏按钮，可直接切换收藏状态
- 收藏的 LoRA 卡片使用橙色边框高亮
- 收藏数据通过现有 API `/naiba/lora/favorites/*` 实现，与 Lora Data Preview 完全共享

## 技术方案

### 修改文件

- `d:/comfyuibyte/ComfyUI_portable_TE_v260619/ComfyUI/custom_nodes/naiba-test/js/visual_lora_loader.js`

### 现有架构

- 收藏 API 已完整存在于 `preset_routes.py`：`GET /naiba/lora/favorites/list`、`POST /naiba/lora/favorites/add`、`DELETE /naiba/lora/favorites/remove`
- 收藏数据存储在 `favorites/favorites.json`
- Lora Data Preview 已有完整收藏实现可参考（`lora_data_preview.js` 第 396-452 行）
- Visual LoRA Loader 当前只有"全部"和"已选择"两个标签（`currentCategory` 变量控制）

### 实现细节

1. **添加颜色常量** - 在 COLORS 对象中添加 `favorite: "#ff9f43"`、`favoriteActive: "#ff6b6b"`、`favoriteBorder: "#ff9f43"`

2. **添加收藏状态** - `let favoriteLoras = new Map()` 存储收藏数据

3. **添加收藏 API 函数**:

- `loadFavorites()` - 调用 `/naiba/lora/favorites/list` 加载
- `toggleFavorite(loraName)` - 调用 add/remove API 切换

4. **修改 `renderFolderTree()`** - 添加第三个标签"收藏"，收藏视图显示收藏数量

5. **修改 `renderLoraList()`**:

- `currentCategory === "favorite"` 时只显示收藏的 LoRA
- 网格卡片添加心形收藏按钮（右上角绝对定位）
- 收藏卡片使用橙色边框 + box-shadow

6. **初始化** - 模态框创建时调用 `loadFavorites()`

### 性能考量

- 收藏数据仅在模态框打开时加载一次，无性能瓶颈
- 收藏切换操作为单次 API 调用，响应快