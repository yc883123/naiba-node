# Naiba Test Custom Nodes for ComfyUI

自定义ComfyUI节点集合，包含WAN模型优化、Multi LoRA Loader、Multi LoRA Loader (only model)、Visual LoRA Loader、Lora Testing Converter、Save Text File、Lora Data Preview、Civitai Info Reader和Custom Data Reader功能。

## 节点列表

### 1. Naiba Wan Block Swap (WAN模型Block Swap节点)

**节点名称**: `NaibaWanBlockSwap`  
**显示名称**: Naiba Wan Block Swap  
**分类**: `naiba-node`

#### 功能说明
通过将transformer block在GPU和CPU内存之间交换，显著降低显存占用，使大模型能够在显存较小的GPU上运行。

#### 输入参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model | MODEL | - | 输入的扩散模型 |
| blocks_to_swap | INT | 20 | 要交换的transformer block数量 |
| offload_img_emb | BOOLEAN | False | 将img_emb卸载到CPU内存 |
| offload_txt_emb | BOOLEAN | False | 将txt_emb卸载到CPU内存 |
| use_non_blocking | BOOLEAN | False | 使用非阻塞内存传输 |
| force_fp16_bias | BOOLEAN | True | 强制将bias转换为float16 |
| vace_blocks_to_swap | INT | 0 | 要交换的VACE block数量 |
| prefetch_blocks | INT | 0 | 预取块数量 |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| model | MODEL | 优化后的模型 |

#### 使用建议
- **14B模型**: 有40个block，建议 `blocks_to_swap` 设置为 20-35
- **1.3B/5B模型**: 有30个block，建议 `blocks_to_swap` 设置为 15-25
- **LongCat-video**: 有48个block，建议 `blocks_to_swap` 设置为 25-40
- **VACE模型**: 有15个block，可通过 `vace_blocks_to_swap` 参数单独控制
- **预取优化**: 设置 `prefetch_blocks` 为 1-2 可以抵消block swap的速度损失

---

### 2. Multi LoRA Loader (多LoRA加载器)

**节点名称**: `MultiLoraLoader`  
**显示名称**: Multi LoRA Loader  
**分类**: `naiba-node`

#### 功能说明
支持动态添加/删除多个LoRA，每个LoRA都有独立的启用开关和权重控制。通过前端UI提供直观的操作界面，无需手动编辑JSON配置。

#### 输入参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model | MODEL | - | 输入的扩散模型 |
| clip | CLIP (可选) | - | 输入的CLIP模型（可选，不连接时仅加载模型部分） |
| lora_data | STRING | [] | LoRA配置JSON数据（由前端UI自动管理） |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| model | MODEL | 应用LoRA后的模型 |
| clip | CLIP? | 应用LoRA后的CLIP模型（可选） |

#### 前端UI功能
- **+ Add LoRA**: 点击添加新的LoRA
- **LoRA选择**: 从下拉列表中选择LoRA文件，支持文本过滤搜索
- **权重控制** (M=Model, C=CLIP): 
  - **M**: 模型强度，支持小数输入（步长0.01，范围-100到100）
  - **C**: CLIP强度，支持小数输入（步长0.01，范围-100到100）
- **启用开关**: 每个LoRA都有独立的启用/禁用开关
- **全局控制**: All开关控制所有LoRA的启用状态
- **Clear**: 清除所有已添加的LoRA
- **预设**: 打开预设管理面板，支持保存/加载/导入/导出预设配置
- **删除**: 单个LoRA的删除按钮

#### JSON数据格式
```json
[
    {
        "name": "some_lora.safetensors",
        "strength_model": 1.0,
        "strength_clip": 1.0,
        "enabled": true
    }
]
```

---

### 3. Multi LoRA Loader (only model) (仅模型多LoRA加载器)

**节点名称**: `MultiLoraLoaderOnlyModel`  
**显示名称**: Multi LoRA Loader (only model)  
**分类**: `naiba-node`

#### 功能说明
仅加载模型，不处理CLIP。支持动态添加/删除多个LoRA，每个LoRA都有独立的启用开关和M权重控制（M=Model）。通过前端UI提供直观的操作界面，无需手动编辑JSON配置。

#### 输入参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model | MODEL | - | 输入的扩散模型 |
| lora_data | STRING | [] | LoRA配置JSON数据（由前端UI自动管理） |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| model | MODEL | 应用LoRA后的模型 |

#### 前端UI功能
- **+ Add LoRA**: 点击添加新的LoRA
- **LoRA选择**: 从下拉列表中选择LoRA文件，支持文本过滤搜索
- **权重控制** (M=Model): 
  - **M**: 模型强度，支持小数输入（步长0.01，范围-100到100）
- **启用开关**: 每个LoRA都有独立的启用/禁用开关
- **全局控制**: All开关控制所有LoRA的启用状态
- **Clear**: 清除所有已添加的LoRA
- **预设**: 打开预设管理面板，支持保存/加载/导入/导出预设配置
- **删除**: 单个LoRA的删除按钮

#### JSON数据格式
```json
[
    {
        "name": "some_lora.safetensors",
        "strength_model": 1.0,
        "enabled": true
    }
]
```

#### 与Multi LoRA Loader的区别
- **无CLIP输入输出**: 不处理CLIP模型，仅影响模型
- **无C权重**: 每个LoRA只有M权重，没有C权重
- **更简洁**: 适用于只需要调整模型而不需要调整CLIP的场景

---

### 4. Lora Testing Converter (Lora Testing预设转换器)

**节点名称**: `LoraTestingConverter`  
**显示名称**: Lora Testing Converter  
**分类**: `naiba-node`

#### 功能说明
将 lora_testing 节点的预设文件转换为 Multi LoRA Loader 可用的格式。方便用户将已有的 lora_testing 预设迁移到 Multi LoRA Loader 使用。

#### 输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| preset_name | 下拉选择 | 选择要导入的 lora_testing 预设 |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| lora_data | STRING | 转换后的 JSON 格式数据，可直接用于 Multi LoRA Loader |

#### 使用方法
1. 在 `naiba-node` 分类下添加 `Lora Testing Converter` 节点
2. 从下拉框选择要导入的 lora_testing 预设
3. 节点会自动显示预览（每个 LoRA 的名称和权重）
4. 复制输出的 JSON 数据到 Multi LoRA Loader 的 `lora_data` 输入

#### 格式转换规则
- lora_testing 的 `lora_name_list` → Multi LoRA Loader 的 `name`
- lora_testing 的 `min_weight` → Multi LoRA Loader 的 `strength_model` 和 `strength_clip`
- lora_testing 的 `enabled_list` → Multi LoRA Loader 的 `enabled`

---

### 5. Save Text File (通用文本文件保存)

**节点名称**: `SaveTextFile`  
**显示名称**: Save Text File  
**分类**: `naiba-node`

#### 功能说明
通用的文本文件保存工具，可以将任意字符串内容保存到指定文件路径。支持自动创建目录。

#### 输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| text | STRING (输入端口) | 要保存的文本内容 |
| file_path | STRING | 保存文件的完整路径 |
| filename | STRING | 文件名（可选，默认 output.txt） |
| auto_mkdir | BOOLEAN | 自动创建目录（默认 True） |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| saved_path | STRING | 实际保存的文件路径 |

#### 使用方法
1. 在 `naiba-node` 分类下添加 `Save Text File` 节点
2. 将其他节点的字符串输出连接到 `text` 输入
3. 在 `file_path` 中输入完整的文件路径
4. 节点会自动创建目录并保存文件

#### 示例
- 连接 Lora Testing Converter 的 `lora_data` 输出，保存转换后的 JSON
- 连接任意文本节点，保存日志、配置文件等

---

### 6. Visual LoRA Loader (可视化LoRA加载器)

**节点名称**: `VisualLoRALoader`  
**显示名称**: Visual LoRA Loader  
**分类**: `naiba-node`

#### 功能说明
带全屏模态弹窗的可视化LoRA选择器，支持图片预览、搜索导航、文件夹浏览、网格/列表视图切换。支持多选、权重控制、预设管理。

#### 输入参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model | MODEL | - | 输入的扩散模型 |
| lora_data | STRING | [] | LoRA配置JSON数据（由前端弹窗UI自动管理） |
| clip | CLIP (可选) | - | 输入的CLIP模型（可选，不连接时仅加载模型部分） |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| model | MODEL | 应用LoRA后的模型 |
| clip | CLIP? | 应用LoRA后的CLIP模型（可选） |

#### 前端UI功能
- **全屏模态弹窗**: 点击按钮弹出全屏弹窗选择LoRA
- **图片预览**: 支持LoRA缩略图预览
- **搜索导航**: 支持文本搜索和文件夹浏览
- **视图切换**: 支持网格和列表两种视图模式
- **多选支持**: 可同时选择多个LoRA
- **权重控制**: 每个LoRA都有独立的M/C权重控制
- **启用开关**: 每个LoRA都有独立的启用/禁用开关
- **预设管理**: 支持保存/加载/导入/导出预设配置

#### JSON数据格式
```json
[
    {
        "name": "some_lora.safetensors",
        "strength_model": 1.0,
        "strength_clip": 1.0,
        "enabled": true
    }
]
```

---

### 7. Civitai Info Reader (Civitai信息读取器)

**节点名称**: `CivitaiInfoReader`  
**显示名称**: Civitai Info Reader  
**分类**: `naiba-node`

#### 功能说明
读取 LoRA 文件对应的 `.civitai.info.json` 元数据文件，输出模型信息、触发词、预览图片、评分等。支持单个或多个 LoRA 信息合并输出，多 LoRA 时自动将预览图拼接为 batch。

#### 输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| lora_names | STRING (可选) | 连接 LoRA 加载器的 lora_names 输出端口，支持单个或多个 LoRA |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| preview_image | IMAGE | 预览图片（多LoRA时输出batch） |
| model_info | STRING | 模型信息（名称、版本、基础模型、类型、描述） |
| trigger_words | STRING | 触发词（无触发词时显示"无触发词"） |
| rating_info | STRING | 评分信息（评分、评价次数、下载量） |
| model_tags | STRING | 模型标签（无标签时显示"无标签"） |
| nsfw_level | INT | NSFW 级别 |
| preview_url | STRING | 预览图 URL |
| civitai_url | STRING | Civitai 模型页面 URL |
| raw_json | STRING | 原始 JSON 元数据 |
| custom_prompt | STRING | 自定义提示词（读取 `.custom.info.json` 中的 custom_prompt 字段） |

#### 使用方法
1. 在 `naiba-node` 分类下添加 `Civitai Info Reader` 节点
2. 将 Multi LoRA Loader 或 Visual LoRA Loader 的 `lora_names` 输出连接到本节点的 `lora_names` 输入
3. 节点会自动读取每个 LoRA 对应的 `.civitai.info.json` 元数据文件
4. 多个 LoRA 时，预览图会自动拼接为 batch，其他信息合并输出

#### 元数据文件
- 元数据文件由 Lora Data Preview 节点从 Civitai 同步生成
- 文件格式：`{lora文件名}.civitai.info.json`
- 存储位置：与 LoRA 文件同目录

---

### 8. Lora Data Preview (LoRA数据预览)

**节点名称**: `LoraDataPreview`  
**显示名称**: Lora Data Preview  
**分类**: `naiba-node`

#### 功能说明
从 Civitai 自动同步 LoRA 封面图片和元数据的预览节点。通过弹窗界面浏览 LoRA 列表、查看元数据、执行同步操作。输出所有启用的 LoRA 名称列表，可连接到 Civitai Info Reader 等节点。

#### 输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| lora_data | STRING | LoRA配置JSON数据（由前端弹窗UI自动管理，无需手动编辑） |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| lora_names | STRING | 所有启用的 LoRA 名称列表（JSON 数组字符串） |

#### 使用方法
1. 在 `naiba-node` 分类下添加 `Lora Data Preview` 节点
2. 通过前端弹窗 UI 浏览和管理 LoRA 数据
3. 节点会自动输出所有启用的 LoRA 名称列表
4. 可将 `lora_names` 输出连接到 Civitai Info Reader 节点，获取详细的元数据信息

---

### 9. Custom Data Reader (自定义数据读取器)

**节点名称**: `CustomDataReader`  
**显示名称**: Custom Data Reader  
**分类**: `naiba-node`

#### 功能说明
读取 LoRA 文件对应的 `.custom.info.json` 自定义数据文件，输出自定义提示词、预览图片、下载链接、NSFW级别、模型介绍等。支持单个或多个 LoRA 数据合并输出，多 LoRA 时自动将预览图拼接为 batch。

#### 输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| lora_names | STRING (可选) | 连接 LoRA 加载器的 lora_names 输出端口，支持单个或多个 LoRA |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| preview_image | IMAGE | 预览图片（多LoRA时输出batch，预览图优先级：Civitai图 > 自定义图 > 空白占位） |
| custom_prompt | STRING | 自定义提示词（多LoRA时带编号合并） |
| model_description | STRING | 自定义模型介绍（多LoRA时带编号合并） |
| download_link | STRING | 自定义下载链接（多LoRA时带编号合并） |
| nsfw_level | INT | NSFW 级别（多LoRA时取最大值） |
| raw_json | STRING | 原始 JSON 自定义数据 |

#### 使用方法
1. 在 `naiba-node` 分类下添加 `Custom Data Reader` 节点
2. 将 Multi LoRA Loader 或 Visual LoRA Loader 的 `lora_names` 输出连接到本节点的 `lora_names` 输入
3. 节点会自动读取每个 LoRA 对应的 `.custom.info.json` 自定义数据文件
4. 多个 LoRA 时，预览图会自动拼接为 batch，其他信息带编号合并输出

#### 自定义数据文件
- 数据文件由 Lora Data Preview 节点的编辑面板生成
- 文件格式：`{lora文件名}.custom.info.json`
- 存储位置：与 LoRA 文件同目录
- 与 `.civitai.info.json` 平行存储，Civitai 同步不会覆盖

---

## 安装方法

1. 将 `naiba-test` 文件夹复制到 `ComfyUI/custom_nodes/` 目录
2. 重启ComfyUI
3. 节点将出现在 `naiba-node` 分类下

## 项目结构

```
naiba-test/
├── __init__.py                             # 节点注册入口
├── naiba_wan_blockswap.py                  # WAN模型Block Swap节点
├── multi_lora_loader.py                    # Multi LoRA Loader节点
├── multi_lora_loader_only_model.py         # Multi LoRA Loader (only model)节点
├── visual_lora_loader.py                   # Visual LoRA Loader节点
├── lora_testing_converter.py               # Lora Testing预设转换器节点
├── save_text_file.py                       # 通用文本文件保存节点
├── lora_data_preview.py                    # LoRA数据预览节点（Civitai同步）
├── civitai_info_reader.py                  # Civitai信息读取节点
├── custom_data_reader.py                   # 自定义数据读取节点
├── civitai_utils.py                        # Civitai API工具模块
├── preset_routes.py                        # 预设管理API路由
├── presets/                                # 预设存储目录（运行时自动创建）
├── js/
│   ├── multi_lora_loader.js                # Multi LoRA Loader前端UI
│   ├── multi_lora_loader_only_model.js     # Multi LoRA Loader (only model)前端UI
│   ├── visual_lora_loader.js               # Visual LoRA Loader前端UI
│   ├── lora_data_preview.js                # Lora Data Preview前端UI
│   ├── lora_testing_converter.js           # Lora Testing Converter前端扩展
│   └── naiba_preset_utils.js               # 共享预设模态框和工具函数
└── README.md                               # 项目说明文档
```

## 依赖项

- ComfyUI
- PyTorch
- tqdm

## 注意事项

1. **Block Swap性能**: Block Swap会增加采样时间，但显著降低显存占用
2. **预取优化**: 使用 `prefetch_blocks` 参数可以减少Block Swap的性能损失
3. **量化兼容性**: 某些量化格式（如INT8）与Block Swap可能存在兼容性问题
4. **LoRA加载**: 每个LoRA都会增加模型的显存占用，请根据GPU显存合理配置
5. **Filter List**: Multi LoRA Loader和Multi LoRA Loader (only model)都支持在下拉框中输入文字过滤搜索LoRA

---

## 预设管理功能

Multi LoRA Loader 和 Multi LoRA Loader (only model) 都支持预设管理功能，可以保存和加载常用的 LoRA 配置。

### 功能说明

#### 服务端预设（存储在服务器）
- **保存预设**: 将当前 LoRA 配置保存为服务端 JSON 文件
- **加载预设**: 从预设列表中选择并导入到节点
- **删除预设**: 删除已保存的预设
- **重命名预设**: 双击预设名称进行重命名

#### 本地文件导入导出
- **导出到文件**: 将当前配置下载为 JSON 文件到本地电脑，方便分享
- **从文件导入**: 从本地选择 JSON 文件导入到节点

### 预设格式

```json
[
    {
        "name": "some_lora.safetensors",
        "strength_model": 1.0,
        "strength_clip": 1.0,
        "enabled": true
    },
    {
        "name": "another_lora.safetensors",
        "strength_model": 0.8,
        "strength_clip": 0.8,
        "enabled": false
    }
]
```

> **注意**: Multi LoRA Loader (only model) 节点导入含 `strength_clip` 的预设时会自动忽略 clip 字段。两个节点的预设可以互相导入。

## 更新日志

### v2.0.0
- 新增自定义数据系统（Custom Data System）
  - **CustomDataReader 节点**：独立的自定义数据读取节点，读取 `.custom.info.json` 文件，输出预览图、自定义提示词、模型介绍、下载链接、NSFW级别、原始JSON
  - **后端 API 路由**：新增合并详情接口、自定义数据保存、图片上传、图片获取等4个 API 端点
  - **详情面板双标签页**：点击详情时显示"元数据"和"自定义"两个标签页，一次请求获取全部数据
  - **独立编辑面板扩展**：支持编辑全部自定义字段（提示词、预览图、下载链接、NSFW分级、模型介绍），所有 LoRA 均可编辑
  - **预览图优先级**：统一使用 `/naiba/lora/preview` 接口，Civitai 图优先、自定义图 fallback
- 扩展 Civitai Info Reader 节点
  - 新增第10个输出端口 `custom_prompt`，读取 `.custom.info.json` 中的自定义提示词字段
  - 支持单个和多个 LoRA 的自定义提示词合并输出
- 移除收藏限制
  - 同步按钮不再因收藏状态而禁用，所有 LoRA 均可同步
  - 编辑按钮对所有 LoRA 可用，不再限制仅收藏 LoRA
- 废弃旧 favorites 自定义字段
  - favorites 中的 `custom_prompt` 和 `custom_image_path` 字段已废弃（不做数据迁移）
  - favorites 仅保留收藏状态，自定义数据独立存储在 `.custom.info.json` 文件中
- 自定义数据存储设计
  - 数据文件：`{lora_name}.custom.info.json`（与 LoRA 文件同目录）
  - 预览图片：`{lora_name}.custom.preview.{ext}`（与 LoRA 文件同目录）
  - 与 `.civitai.info.json` 平行存储，Civitai 同步不会覆盖

### v1.8.0
- 新增 Civitai Info Reader 节点
  - 读取 LoRA 文件对应的 `.civitai.info.json` 元数据文件
  - 支持单个或多个 LoRA 信息合并输出
  - 多 LoRA 时自动将预览图拼接为 batch 输出
  - 输出内容包括：预览图片、模型信息、触发词、评分信息、标签、NSFW级别、预览URL、Civitai链接、原始JSON
  - 支持连接 Multi LoRA Loader / Visual LoRA Loader 的 `lora_names` 输出口
  - 空字段显示友好提示（"无触发词"、"无标签"、"无元数据"等），不再输出空白
- 新增 Lora Data Preview 节点
  - 从 Civitai 自动同步 LoRA 封面图片和元数据
  - 通过弹窗界面浏览 LoRA 列表、查看元数据、执行同步操作
  - 新增 `lora_names` 输出口，输出所有启用的 LoRA 名称列表（JSON 数组字符串）
  - 可直接连接 Civitai Info Reader 节点，形成完整的数据预览链路
- 新增 Civitai API 工具模块（`civitai_utils.py`）
  - SHA256 哈希计算，用于通过文件哈希查询 Civitai 模型信息
  - Civitai API 客户端，支持公开 API 和自定义 API 密钥
  - NSFW 过滤机制，支持多级别配置
  - 预览图自动下载和缓存
  - 本地元数据缓存系统（`.civitai.info.json` 文件）
- 多图预览支持
  - Civitai Info Reader 支持多个 LoRA 时自动拼接预览图为 batch
  - 自动统一图片尺寸，确保 batch 拼接无误
- 节点映射更新
  - 所有节点统一注册到 `__init__.py`，搜索 "naiba" 即可显示全部节点

### v1.5.1
- Visual LoRA Loader 预览图功能增强
  - 扩展支持更多图片格式：`.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.gif`, `.tiff`, `.tif`, `.svg`, `.avif`, `.heic`, `.heif`, `.ico`, `.apng`
  - 参考 lora_testing 项目的图片代理实现，提供完整的 MIME 类型映射
  - 修复子目录中 LoRA 文件预览图无法显示的问题
- 修复 Visual LoRA Loader 节点布局问题
  - 修复已选择 LoRA 预览框超出节点边界的问题
  - 重新设计容器布局，移除 flex:1 避免内容撑开节点
  - 添加 max-height 限制，确保预览框不会超出节点边界
  - 优化高度计算逻辑，动态分配按钮区域和显示区域的高度
- 安全性增强
  - 添加路径遍历攻击防护（检测 `..` 和绝对路径）
  - 验证路径安全性，确保只能访问 LoRA 目录内的文件
  - 添加安全警报日志
- 性能优化
  - 添加内存缓存系统，缓存已加载的图片数据
  - 缓存最多200张图片，1小时过期
  - 新增缓存管理 API：`POST /naiba/cache/clear`（清理缓存）、`GET /naiba/cache/status`（查看缓存状态）

### v1.5.0
- 新增 Visual LoRA Loader 节点
  - 带全屏模态弹窗的可视化LoRA选择器
  - 支持图片预览、搜索导航、文件夹浏览、网格/列表视图切换
  - 支持多选、权重控制、预设管理
- CLIP端口可选
  - Multi LoRA Loader 和 Visual LoRA Loader 的 CLIP 输入现在为可选
  - 不连接CLIP时，节点只加载模型部分，不修改文本编码器
  - 输出类型改为 `CLIP?`，表示CLIP输出可选
- 搜索优化
  - 所有节点都包含 "naiba" 搜索别名，搜索 "naiba" 显示所有节点
- 修复 Visual LoRA Loader 预设导入问题
  - 修复导入预设后 LoRA 选择器主弹窗未自动关闭的问题
  - 导入预设现在会同时关闭预设管理弹窗和主选择器弹窗
- 清理调试日志
  - 移除 Visual LoRA Loader 中的调试日志输出
  - 移除预设管理工具中的调试日志输出

### v1.4.2
- 修复 LoRA 选择框首次点击闪退问题
  - 原因：focus 和 click 事件冲突，导致下拉框打开后立即关闭
  - 方案：使用 pointerdown 事件代替 click，避免 focus/click 竞态条件
  - 同时支持鼠标、触摸屏、触控笔等多种输入设备
- 影响文件
  - `js/multi_lora_loader.js`
  - `js/multi_lora_loader_only_model.js`

### v1.4.1
- 新增 Lora Testing Converter 节点
  - 支持从下拉框选择 lora_testing 预设或手动输入文件路径
  - 将 lora_testing 格式转换为 Multi LoRA Loader 可用的 JSON 格式
  - 自动预览转换结果
- 新增 Save Text File 节点
  - 通用的文本文件保存工具
  - 支持自动创建目录
  - 可连接任意字符串输出
- 清理 Lora Testing Converter 节点
  - 移除 output_path 和 output_file 参数
  - 简化节点接口，只保留 lora_data 输出

### v1.4.0
- 新增预设管理功能
  - Multi LoRA Loader 和 Multi LoRA Loader (only model) 都支持预设管理
  - 服务端预设：保存/加载/删除/重命名预设配置
  - 本地文件导入导出：支持导出为 JSON 文件和从 JSON 文件导入
  - 预设数据格式兼容两种节点，Only Model 节点自动忽略 strength_clip 字段
- 新增 Lora Testing Converter 节点
  - 将 lora_testing 的预设文件转换为 Multi LoRA Loader 可用的格式
  - 提供下拉框选择预设，自动显示转换预览
  - 方便用户迁移已有的 lora_testing 预设配置
- 架构改进
  - 新增 `preset_routes.py` 集中管理预设 API 路由
  - 新增 `js/naiba_preset_utils.js` 共享预设模态框组件
  - 使用 `/naiba/presets/*` API 前缀，避免与其他插件冲突
- 安全增强
  - 所有预设 API 都进行路径遍历防护
  - 使用原子重命名操作，确保数据一致性

### v1.3.0
- 优化 Multi LoRA Loader 和 Multi LoRA Loader (only model) 的UI布局
  - 将 LoRA 选择框、M/C 输入框放在同一行，节省垂直空间
  - 标签从 `Model`/`CLIP` 简化为 `M`/`C`
  - M/C 输入框宽度固定为 52px，更适合显示小数
- 改进搜索功能
  - 所有节点都添加了 "naiba" 搜索别名，搜索 "naiba" 即可显示所有节点
  - 为 Naiba Wan Block Swap 节点添加了 `SEARCH_ALIASES`

### v1.2.0
- 新增 Multi LoRA Loader (only model) 节点
  - 仅加载模型，不处理CLIP
  - 适用于只需要调整模型而不需要调整CLIP的场景
- 改进 Multi LoRA Loader 和 Multi LoRA Loader (only model) 的前端UI
  - 新增 Filter List 功能，支持在下拉框中输入文字过滤搜索LoRA
  - 改进响应式设计，节点内部元素会随节点宽度自适应

### v1.1.0
- 改进Multi LoRA Loader前端UI
  - 标签从 `Mdl`/`Clip` 改为 `Model`/`CLIP`，更清晰易懂
  - 修复小数点输入问题，现在支持输入小数（如0.75、1.5等）
  - 步长设置为0.01，支持两位小数精度
- 清理项目结构，移除未使用的节点文件

### v1.0.0
- 初始版本
- 包含WAN模型Block Swap节点
- 包含Multi LoRA Loader节点