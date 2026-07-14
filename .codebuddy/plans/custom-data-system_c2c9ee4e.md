---
name: custom-data-system
overview: 为 LoRA 自定义数据系统添加完整支持：修改详情面板显示双数据源，废弃旧 favorites 自定义字段（不迁移），在 CivitaiInfoReader 增加 custom_prompt 输出，移除编辑和同步的收藏限制
status: completed
completed_at: "2026-07-14"
todos:
  - id: backend-custom-api
    content: 在 preset_routes.py 添加自定义数据 API 路由（合并详情接口 detail、save、upload-image、image），路径验证需允许子目录但防止遍历攻击
    status: completed
  - id: frontend-detail-tabs
    content: 修改 js/lora_data_preview.js 的 showLoraDetail 函数，添加元数据/自定义双标签页
    status: completed
    dependencies:
      - backend-custom-api
  - id: frontend-edit-panel
    content: 更新独立编辑面板（showFavoriteEditPanel → showEditPanel），移除收藏限制，扩展可编辑字段（提示词、图片、下载链接、NSFW分级、模型介绍），所有 LoRA 可编辑
    status: completed
    dependencies:
      - backend-custom-api
  - id: frontend-remove-fav-restrictions
    content: 移除同步按钮的收藏保护限制，移除列表页卡片中的自定义提示词摘要显示，清理对 favorites 自定义字段的依赖
    status: completed
  - id: frontend-preview-priority
    content: 修改前端预览图显示逻辑，移除收藏自定义图优先逻辑，改为 Civitai 图优先、自定义图 fallback
    status: completed
    dependencies:
      - backend-custom-api
  - id: extend-civitai-reader
    content: 在 civitai_info_reader.py 的 CivitaiInfoReader 节点增加 custom_prompt 输出，读取对应 .custom.info.json 中的 custom_prompt 字段
    status: completed
    dependencies:
      - backend-custom-api
  - id: new-custom-reader-node
    content: 创建 custom_data_reader.py，参考 civitai_info_reader.py 独立实现自定义数据读取节点，输出预览图/提示词/介绍/链接/NSFW/原始JSON
    status: completed
    dependencies:
      - backend-custom-api
  - id: register-new-node
    content: 修改 __init__.py 注册新节点 CustomDataReader
    status: completed
    dependencies:
      - new-custom-reader-node
---

## 需求概述

修改 LoRA Data Preview 节点的详情面板，支持同时查看 Civitai 元数据与自定义数据；更新独立编辑面板支持完整自定义字段；废弃旧 favorites 自定义字段（不做数据迁移）；在 CivitaiInfoReader 节点增加 custom_prompt 输出；移除编辑和同步的收藏限制。

## 核心功能

1. **详情面板双标签页**：点击详情时显示"元数据"和"自定义"两个标签页，分别展示 Civitai 拉取的元数据和用户自定义数据
2. **自定义数据独立存储**：自定义数据以 `{lora_name}.custom.info.json` 保存在 LoRA 文件同目录（与 `.civitai.info.json` 同位置但不同文件名），避免 Civitai 同步时覆盖
3. **自定义数据内容**：自定义提示词、自定义预览图、自定义下载链接、自定义 NSFW 分级、自定义模型介绍
4. **预览图优先级**：优先显示 Civitai 预览图，无 Civitai 图时 fallback 到自定义图（自定义图为备用）
5. **独立编辑面板扩展**：更新编辑面板，可编辑字段从"提示词+图片"扩展为全部自定义字段，所有 LoRA 均可编辑
6. **废弃 favorites 自定义字段**：不做数据迁移，直接废弃 favorites 中的 custom_prompt/custom_image_path，favorites 只保留收藏状态
7. **移除收藏限制**：同步按钮不再因收藏而禁用，编辑按钮对所有 LoRA 可用
8. **扩展 CivitaiInfoReader**：在现有节点中增加 custom_prompt 输出端口，读取 .custom.info.json
9. **列表页简化**：移除卡片中的自定义提示词摘要显示，自定义数据仅在详情/编辑面板中查看

## 技术栈

- **后端**: Python + aiohttp (现有项目技术栈，用于 API 路由)
- **前端**: 原生 JavaScript (现有 JS 扩展机制)
- **数据存储**: JSON 文件（与 LoRA 文件同目录）

## 实现方案

### 1. 后端 API 层 (preset_routes.py)

在现有 `preset_routes.py` 中添加自定义数据管理路由：

**新增路由**:

- `GET /naiba/lora/detail` - 合并接口，一次性返回 Civitai 元数据 + 自定义数据（替代详情面板原来的单独 metadata 请求）
- `POST /naiba/lora/custom-data/save` - 保存自定义数据
- `POST /naiba/lora/custom-data/upload-image` - 上传自定义预览图
- `GET /naiba/lora/custom-data/image` - 获取自定义预览图

**路径安全**:

- LoRA 名称可能包含子目录（如 `subfolder/model.safetensors`），验证逻辑需允许正斜杠子目录分隔，但拒绝 `..`、反斜杠、以及解析后超出 LoRA 根目录的路径
- 使用 `os.path.realpath` 解析后确认最终路径在 `folder_paths.get_folder_paths("loras")` 范围内

**存储设计**:

- 自定义数据文件: `{lora_dir}/{lora_basename}.custom.info.json`
- 自定义图片: 保存在 `{lora_dir}/{lora_basename}.custom.preview.{ext}`
- 与 `.civitai.info.json` 同目录但不同文件名，确保 Civitai 同步不会覆盖

**自定义数据 JSON 结构**:

```
{
  "custom_prompt": "自定义提示词文本",
  "custom_download_link": "https://...",
  "custom_nsfw_level": 0,
  "custom_model_description": "自定义模型介绍",
  "custom_preview_image_path": "/path/to/custom.preview.webp",
  "updated_at": "2026-07-14T..."
}
```

**合并详情接口响应结构** (`GET /naiba/lora/detail?name=xxx`):

```
{
  "success": true,
  "metadata": { ... },       // Civitai 元数据（与现有 /naiba/lora/metadata 返回格式一致）
  "custom_data": { ... }     // 自定义数据（上述 JSON 结构），无自定义数据时为 null
}
```

### 2. 前端详情面板 (lora_data_preview.js)

修改 `showLoraDetail` 函数：

- 调用合并接口 `GET /naiba/lora/detail?name=xxx`，一次请求获取 Civitai 元数据和自定义数据
- 添加标签页切换 UI（"元数据" / "自定义"）
- "自定义"标签页仅展示自定义数据（只读），编辑在独立编辑面板中进行
- 修改预览图逻辑：优先显示 Civitai 图，fallback 到自定义图

### 3. 独立编辑面板 (lora_data_preview.js)

更新现有 `showFavoriteEditPanel` → `showEditPanel`：

- 移除收藏状态检查，所有 LoRA 均可打开编辑面板
- 扩展可编辑字段：
  - 自定义提示词（textarea，保留）
  - 自定义预览图上传（保留）
  - 自定义下载链接（input，新增）
  - 自定义 NSFW 分级（select/number，新增）
  - 自定义模型介绍（textarea，新增）
- 保存调用 `POST /naiba/lora/custom-data/save`
- 图片上传调用 `POST /naiba/lora/custom-data/upload-image`

### 4. 列表页卡片清理 (lora_data_preview.js)

- 移除卡片中 `favoriteData.custom_prompt` 摘要显示
- 移除预览图的收藏自定义图优先逻辑，统一使用 `/naiba/lora/preview` 接口
- 编辑按钮对所有 LoRA 可见，点击打开独立编辑面板
- 移除同步按钮的收藏禁用逻辑

### 5. 扩展 CivitaiInfoReader (civitai_info_reader.py)

在现有 CivitaiInfoReader 节点中：

- 新增输出端口 `custom_prompt` (STRING)
- 在 `_read_single_lora` / `_read_multiple_loras` 中查找对应的 `.custom.info.json`
- 读取 `custom_prompt` 字段并输出
- 无自定义数据时输出空字符串

### 6. 新建自定义数据读取节点 (custom_data_reader.py)

参考 `civitai_info_reader.py` 的结构，完全独立实现：

- 查找 `.custom.info.json` 文件
- 输出：预览图(IMAGE)、自定义提示词(STRING)、模型介绍(STRING)、下载链接(STRING)、NSFW级别(INT)、原始JSON(STRING)
- 支持单个/多个 LoRA 输入
- 预览图优先级：Civitai 图 > 自定义图 > 空白占位

### 7. 节点注册 (__init__.py)

- 导入 `custom_data_reader.py` 并注册 `CustomDataReader` 节点
- CivitaiInfoReader 只增加输出端口，无需额外注册

## 关键技术决策

1. **存储位置选择**：自定义数据放在 LoRA 同目录（而非 favorites/），确保数据跟随 LoRA 文件移动
2. **文件命名**：使用 `.custom.info.json` 后缀，与 `.civitai.info.json` 平行，清晰区分
3. **图片存储**：自定义预览图也放在 LoRA 同目录，命名为 `{basename}.custom.preview.{ext}`
4. **路径安全**：验证 LoRA 名称时允许子目录斜杠，但使用 realpath 确认解析后路径在 LoRA 根目录范围内，防止路径遍历攻击
5. **不做数据迁移**：直接废弃 favorites 中的自定义字段，用户从零开始使用新系统
6. **双重输出**：CivitaiInfoReader 增加 custom_prompt 便捷输出，同时提供独立 CustomDataReader 节点输出完整自定义数据
7. **预览图为备用**：自定义预览图仅在无 Civitai 图时显示，不覆盖 Civitai 数据
8. **详情只读 + 独立编辑**：详情面板的"自定义"标签页仅展示数据，编辑在独立面板中完成
9. **列表页不显示自定义摘要**：减少列表页复杂度和请求量，自定义数据仅在详情/编辑面板中访问
10. **移除所有收藏限制**：同步和编辑不再受收藏状态约束，收藏只影响排序/过滤
