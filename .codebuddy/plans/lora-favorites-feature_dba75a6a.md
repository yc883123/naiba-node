---
name: lora-favorites-feature
overview: |-
  1. 移除 Visual LoRA Loader 节点中的自动同步功能（仅在图片加载失败时显示"无预览图"）
  2. 给 Lora Data Preview 节点增加收藏功能：支持自定义提示词和图片，收藏的LORA不能被同步
todos:
  - id: remove-visual-lora-sync
    content: 移除 Visual LoRA Loader 的自动同步逻辑
    status: completed
  - id: add-favorites-backend-api
    content: 添加收藏后端 API 路由到 preset_routes.py
    status: completed
  - id: add-favorites-ui-core
    content: 实现 Lora Data Preview 收藏 UI 核心功能
    status: completed
    dependencies:
      - add-favorites-backend-api
  - id: add-favorites-edit-panel
    content: 实现收藏编辑面板（自定义提示词和图片）
    status: completed
    dependencies:
      - add-favorites-ui-core
  - id: add-sync-protection
    content: 实现同步保护逻辑（跳过收藏的 LoRA）
    status: completed
    dependencies:
      - add-favorites-ui-core
  - id: add-favorites-tab-view
    content: 添加收藏视图标签和收藏过滤功能
    status: completed
    dependencies:
      - add-favorites-ui-core
---

## 需求概述

### 需求1：移除 Visual LoRA Loader 的同步功能

- Visual LoRA Loader 节点中的自动 Civitai 同步功能需要完全移除
- 同步功能只能在 Lora Data Preview 节点中进行
- 移除后，图片加载失败时直接显示"无预览图"，不再尝试同步

### 需求2：给 Lora Data Preview 增加收藏功能

- **收藏管理**：用户可以收藏/取消收藏 LoRA
- **自定义内容**：收藏的 LoRA 可以自定义提示词（prompt）和预览图片
- **同步保护**：收藏的 LoRA 不能被同步（包括单个同步和批量同步中的强制更新）
- **取消收藏恢复**：只有取消收藏后，该 LoRA 才能被同步
- **数据持久化**：收藏数据需要服务端持久化存储

## 核心功能

### Visual LoRA Loader

- 移除 previewImg.onerror 中的自动同步逻辑（约35行代码）
- 图片加载失败时直接显示"无预览图"

### Lora Data Preview 收藏功能

- **收藏/取消收藏按钮**：每个 LoRA 卡片上显示收藏状态按钮
- **收藏编辑面板**：点击收藏后可编辑自定义提示词和上传自定义图片
- **收藏视图标签**：在"全部"/"已选择"标签旁增加"收藏"标签
- **同步保护**：
- 单个同步时检查是否为收藏状态，若是则显示提示"收藏的LoRA无法同步"
- 批量同步时自动跳过收藏的 LoRA
- **收藏数据结构**：

```
{
"name": "lora_name.safetensors",
"custom_prompt": "自定义提示词",
"custom_image_path": "自定义图片路径",
"favorited_at": "2026-07-13T12:00:00Z"
}
```

## 技术方案

### 技术栈

- 前端：JavaScript (ComfyUI 前端扩展)
- 后端：Python (aiohttp web server)
- 存储：JSON 文件（复用现有的 presets 存储模式）

### 实现方案

#### 1. 移除 Visual LoRA Loader 同步逻辑

**文件**：`js/visual_lora_loader.js`
**改动**：删除第584-619行的自动同步逻辑，替换为简单的"无预览图"提示

```javascript
// 修改前（第584-619行）
let hasTriedSync = false;
previewImg.onerror = async () => {
    if (!hasTriedSync) {
        // ... 同步逻辑
    } else {
        preview.innerHTML = `<div>无预览图</div>`;
    }
};

// 修改后
previewImg.onerror = () => {
    preview.innerHTML = `<div style="color:${COLORS.textDim};font-size:11px;">无预览图</div>`;
};
```

#### 2. 收藏后端 API

**文件**：`preset_routes.py`
**新增路由**：

| 路由 | 方法 | 功能 |
| --- | --- | --- |
| `/naiba/lora/favorites/list` | GET | 获取所有收藏的 LoRA 列表 |
| `/naiba/lora/favorites/add` | POST | 添加收藏（含自定义提示词和图片） |
| `/naiba/lora/favorites/remove` | DELETE | 取消收藏 |
| `/naiba/lora/favorites/update` | POST | 更新收藏信息（提示词、图片） |
| `/naiba/lora/favorites/upload-image` | POST | 上传自定义收藏图片 |


**存储位置**：`favorites/` 目录（与 `presets/` 同级），每个收藏一个 JSON 文件

**收藏数据格式**：

```
{
  "name": "character/style_lora.safetensors",
  "custom_prompt": "1girl, masterpiece, best quality",
  "custom_image_path": "favorites/images/character_style_lora_custom.webp",
  "favorited_at": "2026-07-13T12:00:00"
}
```

#### 3. 收藏前端功能

**文件**：`js/lora_data_preview.js`

**UI 改动**：

1. 在工具栏增加"收藏"标签（tab）- 与"全部"/"已选择"并列
2. 每个 LoRA 卡片右上角增加收藏按钮（心形图标）
3. 收藏的 LoRA 卡片显示特殊边框样式（金色/橙色）
4. 点击"详情"按钮时，如果已收藏，显示收藏编辑面板

**收藏编辑面板功能**：

- 自定义提示词输入框（多行文本）
- 自定义图片上传区域（支持拖拽上传）
- 自定义图片预览和删除
- 保存/取消按钮

**同步保护逻辑**：

- `syncSingleLora()` 函数开头检查 `favoriteLoras.has(loraName)`，若是则显示警告并返回
- `startBatchSync()` 在过滤同步列表时排除收藏的 LoRA
- 批量同步进度显示中显示"跳过X个收藏的LoRA"

#### 4. 数据流设计

```
用户操作 → 前端状态管理 → 后端 API → JSON 文件存储
                    ↓
            收藏状态更新 → UI 重新渲染
                    ↓
            同步保护检查 → 跳过收藏的 LoRA
```

### 性能考虑

- 收藏列表在弹窗打开时一次性加载（`/naiba/lora/favorites/list`）
- 自定义图片使用服务端存储，通过 `/naiba/lora/preview` API 返回
- 收藏状态检查使用 Set 数据结构，O(1) 查找复杂度

### 向后兼容性

- 不影响现有的 LoRA 加载和使用逻辑
- 不影响现有的预设系统
- 收藏功能完全独立，未收藏的 LoRA 行为不变

## Agent Extensions

### SubAgent

- **code-explorer**
- Purpose: 在实施过程中探索代码库，确认文件路径和代码结构的准确性
- Expected outcome: 提供精确的代码位置和依赖关系信息，确保修改的完整性