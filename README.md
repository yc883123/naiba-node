# Naiba Test Custom Nodes for ComfyUI

自定义ComfyUI节点集合，包含WAN模型优化、Multi LoRA Loader、Multi LoRA Loader (only model)、Visual LoRA Loader、List LoRA Loader、Lora Testing Converter、Save Text File、Lora Data Preview、Civitai Info Reader、Custom Data Reader和Power LoRA Config Reader功能。

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

### 10. Power LoRA Config Reader (LoRA配置读取器)

**节点名称**: `PowerLoraConfigReader`  
**显示名称**: Power LoRA Config Reader  
**分类**: `naiba-node`

#### 功能说明
读取画布上 LoRA 加载器节点的配置信息，转换为 naiba 预设格式 JSON。通过 ComfyUI 的 PROMPT 隐藏输入追踪上游节点连接链路，自动定位并解析 LoRA 配置。

#### 支持的上游节点
- rgthree Power Lora Loader
- rgthree Lora Loader Stack
- naiba MultiLoraLoader / MultiLoraLoaderOnlyModel
- ComfyUI 内置 LoraLoader
- 任何包含 lora 相关输入的节点（通用兜底）

#### 输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| model | MODEL (必需) | 连接上游 LoRA 加载器的 MODEL 输出 |
| clip | CLIP (可选) | 连接上游 LoRA 加载器的 CLIP 输出 |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| preset_json | STRING | naiba 预设格式 JSON，可直接保存为 .json 文件 |
| lora_names | STRING | 启用的 LoRA 文件名 JSON 数组 |
| status | STRING | 读取状态信息 |

#### 使用方法
1. 在 `naiba-node` 分类下添加 `Power LoRA Config Reader` 节点
2. 将上游 LoRA 加载器的 MODEL 输出连接到本节点的 MODEL 输入
3. 节点会自动读取上游加载器的 LoRA 配置
4. `preset_json` 输出口输出预设配置，配合 Save Text File 节点可保存为文件

---

### 11. Naiba Textbox (可编辑文本框)

**节点名称**: `NaibaTextbox`  
**显示名称**: Naiba Textbox  
**分类**: `naiba-node`

#### 功能说明
提供一个可编辑的多行字符串输入框，并带一个 `passthrough` 输入端口。上游字符串传入 `passthrough` 后自动采用其值并回显到节点预览框，否则使用输入框内容。结果在节点内直接预览/编辑，并向下游输出该字符串。

#### 输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| text | STRING (多行) | 可编辑的字符串输入，节点内直接预览/编辑 |
| passthrough | STRING (可选, 输入端口) | 上游字符串输入，传入后覆盖 text 内容并回显到预览框 |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| text | STRING | 最终字符串（passthrough 优先，否则使用输入框） |

#### 使用方法
1. 在 `naiba-node` 分类下添加 `Naiba Textbox` 节点
2. 直接在节点输入框编辑字符串，或连接上游节点的字符串输出到 `passthrough` 端口
3. 字符串会出现在节点预览框中，可继续编辑并向下游传递

---

### 12. Naiba Tag Picker (标签画廊选择器 / 扭蛋)

**节点名称**: `NaibaTagPicker`  
**显示名称**: Naiba Tag Picker (画师/角色/IP/扭蛋)  
**分类**: `naiba-node`

#### 功能说明
通过 Danbooru 公开 API 搜索 画师(artist) / 角色(character) / IP(copyright) 三类标签，前端三标签页画廊多选（带缩略图预览），选图结果以分组 JSON 写回隐藏控件，并输出三类标签名串 + 选中图批量预览（IMAGE，仅内存、不落盘）。

内置**扭蛋随机**功能：弹窗内分别指定「画师 / 角色 / IP 每类抽几个（0~10）」：
- **部分随机**：由后端从 Danbooru 实时随机取样 画师 a 个 + 角色 c 个 + IP i 个；
- **完全随机**：忽略数量，随机抽 0~(a+c+i) 个标签；
- 扭蛋面板内与节点外部均提供「清除」按钮一键清空。
- **节点外部「随机生成」按钮**：无需打开弹窗、无需开启任何开关，点击即直接生成一组随机标签，实时显示在节点预览区并输出到 `RANDOM_TAGS`；可反复点击重新生成。
- 弹窗内或外部生成 / 删除扭蛋结果会**自动开启**后端扭蛋输出并实时刷新预览，不必再点「应用选中」或手动开关。

#### 输入参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| selection_data | STRING | {} | 三分类选中数据（由前端画廊自动管理，无需手动编辑） |
| max_images | INT | 16 | 批量预览图最大张数（超出截断） |
| preview_size | INT | 320 | 预览图边长上限（保持比例居中贴到正方形，控制显存） |
| artist_at | BOOLEAN | False | 开启后画师标签输出为 `@画师名`（ARTIST_NAMES 与扭蛋 RANDOM_TAGS 中的画师标签都会加 @）；关闭则原样输出画师名 |
| gacha_mode | BOOLEAN | False | 由前端自动管理（无需手动操作）：有扭蛋结果时自动开启以输出 RANDOM_TAGS，清除时关闭 |
| gacha_data | STRING | {} | 扭蛋结果（由弹窗扭蛋标签页自动管理）：`{"tags": [{"tag","category"}]}` |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| ARTIST_NAMES | STRING | 选中的画师标签名串（逗号分隔，artist_at 开启时加 @） |
| CHARACTER_NAMES | STRING | 选中的角色标签名串 |
| IP_NAMES | STRING | 选中的 IP 标签名串 |
| MERGED_TAGS | STRING | 画师+角色+IP 选中项合并成一条（artist_at 开启时画师部分加 @） |
| RANDOM_TAGS | STRING | 扭蛋随机标签名串（有扭蛋结果时自动输出，画师标签同样按 artist_at 加 @） |
| PREVIEW_IMAGES | IMAGE | 选中标签代表作批量预览（仅内存，不落盘） |

#### 使用方法
1. 在 `naiba-node` 分类下添加 `Naiba Tag Picker` 节点
2. 点击节点上的「打开标签画廊」按钮，在弹窗内切换 画师/角色/IP 标签页搜索并多选
3. 切到「扭蛋」标签页，分别设定每类数量，点「部分随机」或「完全随机」生成随机标签；每个扭蛋结果卡片右上角「✕」可删除不想要的标签
4. 点「应用选中」写回数据；需要清空时点「清除已选」（节点侧）或「清除」（扭蛋面板内）
5. 节点上 `artist_at`（画师加 @）开关控制画师标签是否加 @ 前缀（作用于 ARTIST_NAMES / MERGED_TAGS / 扭蛋 RANDOM_TAGS）
6. 点击「随机生成」即可直接得到扭蛋组合并输出到 `RANDOM_TAGS`（无需开启开关）；需要合并全部选中标签时用 `MERGED_TAGS`，可直接接入提示词

#### 注意事项
- Danbooru 匿名 API 有访问频率限制，搜索与预览走限流 + 重试（429/403 指数退避）；如遇持续 403/限流，设置环境变量 `DANBOORU_USER` / `DANBOURU_API_KEY` 可提升限额
- 预览图字节仅做魔数 MIME 识别 + 进程内内存缓存（上限 100、TTL 1h），绝不写盘
- UA 刻意避开 "ComfyUI" 字样（Danbooru/Cloudflare 对含该字样的请求返回 403），仅以本项目名 `naiba` 标识

---

### 13. List LoRA Loader (列表LoRA加载器)

**节点名称**: `ListLoRALoader`  
**显示名称**: List LoRA Loader  
**分类**: `naiba-node`

#### 功能说明
读取 Visual LoRA Loader 输出的 `preset_json`（JSON 字符串），依次加载所有启用的 LoRA。三个纯连接端口（无文本框），`lora_list` 直接连接 `visual_lora_loader` 的 `preset_json` 输出。输出的 `LORA_NAMES` 可直接连接 `Civitai Info Reader` / `Custom Data Reader` 的 `lora_names` 输入。

#### 输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| model | MODEL | 输入的扩散模型 |
| clip | CLIP | 输入的CLIP模型 |
| lora_list | STRING (forceInput) | LoRA组合列表（连接 visual lora loader 的 preset_json 输出） |

#### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| MODEL | MODEL | 加载LoRA后的模型 |
| CLIP | CLIP | 加载LoRA后的CLIP模型 |
| LORA_NAMES | STRING | 启用的LoRA名字JSON数组，供 Civitai Info Reader / Custom Data Reader 使用 |

---

## 安装方法

1. 将 `naiba-test` 文件夹复制到 `ComfyUI/custom_nodes/` 目录
2. 重启ComfyUI
3. 节点将出现在 `naiba-node` 分类下

### 预设管理
- 首次使用时，系统会自动从 `presets.example` 目录复制示例预设到 `presets` 目录
- 用户自定义的预设保存在 `presets` 目录中，不会被git跟踪
- 如果需要重置预设，可以删除 `presets` 目录，系统会在下次启动时重新复制示例

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
├── power_lora_config_reader.py             # Power LoRA Config Reader节点
├── naiba_textbox.py                        # 可编辑文本框节点（Textbox）
├── naiba_tag_picker.py                     # Danbooru 标签画廊选择器 / 扭蛋节点
├── civitai_utils.py                        # Civitai API工具模块
├── preset_routes.py                        # 预设管理API路由
├── presets/                                # 预设存储目录（运行时自动创建）
├── js/
│   ├── multi_lora_loader.js                # Multi LoRA Loader前端UI
│   ├── multi_lora_loader_only_model.js     # Multi LoRA Loader (only model)前端UI
│   ├── visual_lora_loader.js               # Visual LoRA Loader前端UI
│   ├── lora_data_preview.js                # Lora Data Preview前端UI
│   ├── lora_testing_converter.js           # Lora Testing Converter前端扩展
│   ├── naiba_textbox.js                    # Naiba Textbox前端UI
│   ├── naiba_tag_picker.js                 # Naiba Tag Picker 前端画廊扩展
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

### v2.10.0
- 新增 **List LoRA Loader** 节点
  - 读取 Visual LoRA Loader 输出的 `preset_json`（JSON 字符串），依次加载所有启用的 LoRA
  - 三个纯连接端口（无文本框）：`MODEL`、`CLIP`、`lora_list`（`forceInput=True`，直接连 `preset_json`）
  - 输出 `MODEL`、`CLIP` 和 `LORA_NAMES`（JSON 数组字符串），可直接连接 `Civitai Info Reader` / `Custom Data Reader` 的 `lora_names` 输入

### v2.9.2
- Civitai 同步视频/GIF 预览支持
  - `select_preview_image` 不再排除视频和 GIF：当模型在 Civitai 仅有视频/动态预览时（如音频/视频模型），回退选用视频/GIF 并标记 `_is_motion_preview=True`
  - `sync_lora_from_civitai` 遇到动态预览自动下载后抽取首帧保存为 `.preview.png` 封面，抽帧成功后删除中间视频/GIF 文件节省空间
  - 首帧抽取三路兜底：PIL（GIF）→ cv2 → imageio → ffmpeg 子进程，任一可用即可
- 下载图片 MIME 校验（拒绝 HTML/JSON 错误页）
  - `download_image` 新增 `validate` 参数（默认开启），基于魔数严格校验响应是否为真实图片
  - 新增 `_looks_like_image` / `detect_image_mime` 工具函数，支持 PNG/JPEG/WebP/GIF/TIFF/AVIF/HEIC/ICO 等魔数识别
  - 静态图下载默认开启校验，视频/GIF 中间文件下载时关闭（`validate=False`）
- 避免无图模型反复请求 Civitai
  - 元数据新增 `_preview_resolved` 守卫标记：无论最终是否有预览图，处理完成后标记为已解析，后续同步时直接跳过 API 请求
  - 解决无预览模型（如纯音频模型）每次同步都重复查询 Civitai 的性能浪费

### v2.9.1
- Naiba Tag Picker 分类与输出修复
  - 修复「IP」分页与「标签」分页内容一模一样的问题：根因是后端搜索路由的 `cat` 映射字典键写成 `ip`，而前端已把 IP 映射为 `copyright` 后再传参，导致 IP 页被兜底成 `tag`、与标签页返回同一批 general 标签；现改为按 `copyright` 键匹配，IP 页返回版权/IP 标签、标签页返回 general 标签，彻底分离
  - 新增 `TAG_NAMES` 输出口：此前「标签」分类即便选中也无处输出（节点缺该输出端），现四类均有独立输出（`ARTIST_NAMES` / `CHARACTER_NAMES` / `IP_NAMES` / `TAG_NAMES`）
  - `MERGED_TAGS` 整合全部分类：由原先仅合并 画师+角色+IP，改为 画师+角色+IP+标签，可直接作为最终提示词使用
  - 节点开启 `OUTPUT_NODE`，画布上可直接查看各输出文本

### v2.9.0
- Naiba Tag Picker 节点 UI 还原与体验修复
  - 恢复「随机生成 → 预览框 → 清除已选 → 打开标签画廊」DOM 控件布局（此前被改为纯按钮且误删预览框与清除已选，并将 `gacha_mode` 误设为节点可见开关）
  - 预览框与弹窗联动：弹窗内点「应用」后画布上的已选摘要预览框实时刷新；应用同时自动同步 `gacha_mode` 开关，使扭蛋结果正确进入 `RANDOM_TAGS` 输出
  - 黑名单能力补全：标签画廊 / 扭蛋结果卡片新增「🚫 加入黑名单」按钮，扭蛋结果拉黑后自动从当前结果移除
- 节点「随机生成」按钮改进
  - 调用时读取节点黑名单传给后端，生成的标签自动排除已拉黑项
  - 随机 3~9 组（每组 画师+角色+IP），避免每次固定数量
  - 勾选「随机同步弹窗」时一键打开弹窗并切到扭蛋页，便于查看/加黑名单/重抽（修复此前该开关失效、不打钩也一直同步弹窗的问题）
- 老工作流自愈（无需删节点重加）
  - 载入/创建节点时自动修复因结构变更错位或损坏的控件值：`max_images`/`preview_size` 越界或空值夹回合法范围，`artist_at`/`gacha_mode` 强制布尔；已选标签与扭蛋结果按名保留

### v2.8.2
- Naiba Tag Picker 扭蛋体验简化
  - 移除节点上的「扭蛋模式」手动开关；点击「随机生成」或在弹窗内生成/删除扭蛋结果时，后端扭蛋输出（`RANDOM_TAGS`）由前端自动开启/关闭，无需手动操作

### v2.8.1
- Naiba Tag Picker 体验与输出增强
  - 新增 `MERGED_TAGS` 输出：把弹窗中选中的 画师 + 角色 + IP 标签合并成一条（顺序 画师→角色→IP），方便直接接提示词
  - 新增 `artist_at` 开关（位于 `preview_size` 下方）：开启后画师标签输出为 `@画师名`，作用于 `ARTIST_NAMES` / `MERGED_TAGS` / 扭蛋 `RANDOM_TAGS` 中的画师标签
  - 扭蛋结果卡片新增「✕」删除按钮：逐个移除不想要的随机标签
  - 扭蛋随机标签结果改为携带 `category`（画师/角色/IP），`RANDOM_TAGS` 中画师部分可按 `artist_at` 加 @（旧版纯字符串扭蛋数据仍可兼容加载）
  - 后端预览请求限流由「固定 2s 硬串行」改为令牌桶（稳态 ~2 req/s、突发 12），首屏可见图 ~1s 内出现，一页 50 图由 ~100s 降至 ~20s；保留 429/403 指数退避重试兜底

### v2.8.0
- 新增 Naiba Tag Picker 节点（标签画廊选择器 / 扭蛋）
  - 通过 Danbooru 公开 API（`/tags.json`）搜索 画师(artist) / 角色(character) / IP(copyright) 三类标签
  - 前端三标签页画廊多选，缩略图走两步法代理（`/naiba/tag/preview` 取代表作 URL → `/naiba/tag/image` 取字节），懒加载 + 并发队列 + 失败自动重试
  - 输出三类标签名串（ARTIST_NAMES / CHARACTER_NAMES / IP_NAMES）+ 选中标签代表作批量预览 IMAGE（仅内存、不落盘，绝不写盘）
  - 预览图魔数 MIME 识别 + 进程内内存缓存（上限 100、TTL 1h）
- 修复 Danbooru 搜索 403（Cloudflare 风控）
  - 根因：Danbooru/Cloudflare 已把 UA 中含 "ComfyUI" 字样的请求列入黑名单，一律返回 403
  - 请求 UA 改为 `naiba-tag-picker/1.0 (+naiba-node)`（绝不含 "ComfyUI"），实测 tags.json / posts.json / CDN 图片均恢复 200
  - 429 / 403 做指数退避重试；可选 `DANBOURU_USER` / `DANBOURU_API_KEY` 环境变量走 Basic Auth 提升限额
- 扭蛋模式重构：由「输入候选画师/角色/IP」改为「指定每类数量」
  - 弹窗内分别设定 画师 / 角色 / IP 各抽几个（0~10）
  - 「部分随机」：由后端 `get_random_tags_from_category` 从 Danbooru 实时随机取样（a 个画师 + c 个角色 + i 个 IP），无需手填候选
  - 「完全随机」：忽略数量，随机抽 0~(a+c+i) 个标签
  - 新增路由 `GET /naiba/tag/gacha_partial`（按数量实时取样）
- 新增清除能力
  - 扭蛋面板内「清除」按钮：清空当前扭蛋结果
  - 节点外部「清除已选」按钮：重置 `selection_data` / `gacha_data` 控件，并通过 `node._tpClearSelection` 同步清空弹窗内存状态（含选中与扭蛋结果）

### v2.7.0
- Lora Data Preview 主弹窗复用 Visual LoRA Loader 结构
  - 新增左侧**文件夹侧边栏**，按 LoRA 目录层级浏览（`buildFolderStructure` / `getLorasInFolder` / `renderFolderTree` / `renderFolderLevel`）
  - 标题栏新增**网格 / 列表视图切换**按钮（`currentView` 与类别状态 `currentCategory` 解耦）
  - 保留「全部 / 已选择 / 收藏」类别标签，网格与列表视图均提供 `同步 / 编辑 / 详情` + 收藏按钮
  - 刷新列表 / 初始化 / 全选均改为按「文件夹 + 类别 + 搜索」计算可见项并同步刷新侧边栏
- Lora Data Preview 编辑面板改造
  - 顶部新增 **Civitai 元数据只读区**（模型名、版本、基础模型、触发词、描述、标签），纯展示不可编辑
  - 下方保留原有可编辑的自定义数据（提示词、预览图上传、下载链接、NSFW、模型介绍）
  - 修复详情页「加载中」占位框未被真实内容替换的问题
  - 自定义标签页新增「删除自定义数据」按钮，调用后端 `DELETE /naiba/lora/custom-data`
  - 修复编辑面板内容过长时被浏览器窗口截断且无法滚动：改为「标题栏固定 + 内容区滚动 + 底部按钮固定」布局（`max-height:90vh` + 纵向 flex + 内容区 `overflow-y:auto`）
- 后端新增自定义数据删除路由
  - `DELETE /naiba/lora/custom-data`：删除 `{lora}.custom.info.json` 及全部 `{lora}.custom.preview.*`，清理预览缓存，不影响 Civitai 元数据
- Visual LoRA Loader 交互修复
  - 增强选中卡片对比度（网格 3px 边框 + 辉光 + 深色底；列表 2px 边框 + 辉光）
  - 移除卡片左上角红色 `×` 删除按钮，改为点击卡片本身取消选中（保留右上角关闭按钮）
  - 点击选中改为增量刷新 `refreshCardState()`，消除每次全量 `renderLoraList()` 造成的卡顿
  - 修复列表模式空白 Bug：为未选中 LoRA 的 `selectedLoras.get()` 访问补充 `has()` 守卫
- Multi LoRA Loader / Multi LoRA Loader (only model) 悬浮预览优化
  - 悬浮预览仅绑定到 LoRA 名称选择框（不再整张卡片触发），划过权重/开关/删除区域不再弹浮层
  - 新增 hover 延迟调度（`scheduleLoraFloatPreview`，320ms），快速划过不触发预览；下拉选项同步使用延迟

### v2.5.0
- 新增 Preset Folder Reader 节点
  - 直接读取 `custom_nodes/naiba-test/presets/` 目录下的预设 JSON，绕开画布连线即可拿到带 sha256 的预设配置
  - `preset_name` 下拉列出所有预设，带「🔄 刷新预设列表」按钮（复用 `/naiba/presets/list` 接口重新扫描目录）
  - 输出 `preset_json` / `lora_names` / `status`，格式与 Power LoRA Config Reader 完全一致，可直接接 Preset Sha256 Aligner / Civitai Sha256 Info Reader
  - 每条自动带 `sha256`：预设已写入则用，缺失则按文件名现场计算（带 mtime/size 缓存）；可选 `skip_disabled` 只输出启用项
- Preset Sha256 Aligner 缺失输出携带 lora 名字
  - `missing_sha256` 输出从纯哈希数组改为 `[{"name":..., "sha256":...}]`，便于下游节点识别缺失模型
- Civitai Sha256 Info Reader 优化
  - 移除 `nsfw_level` 输入控件，内部默认 `Blocked`（=32）实现完全不过滤，保留 `nsfw_level` 输出端口
  - `not_found_sha256` 端口输出改为 `[{"name":..., "sha256":...}]`，C站查不到的 LORA 可显示对应名字
  - 解析支持三种输入格式：上游 `missing_sha256` 输出（含名字）/ 纯 JSON 数组 / 每行 `lora名|sha256` 文本
  - 兜底：输入仅含纯哈希时反查本地 lora 目录补全文件名

### v2.3.4
- 预设保存/导入 SHA256 扫描进度提示
  - 根因：后端计算 sha256 已在 worker 线程执行（浏览器画布不会真正冻结），但大文件（GB 级、尤其机械硬盘）扫描可超 4–5 秒，前端无任何反馈，易误以为卡死
  - `js/naiba_preset_utils.js` 新增单例浮层 `showShaProgress()` / `hideShaProgress()`，居中显示「扫描sha256中.....」加旋转动画（z-index 高于预设弹窗）
  - 在保存（`/naiba/presets/save`）与两种导入（`/naiba/presets/resolve` 扫描全部本地 LoRA）发起前显示，结束（成功/异常）经 `finally` 统一隐藏，绝不残留
- 修复 Multi LoRA Loader 搜索下拉被顶到屏幕顶
  - 根因：`openDropdown` 仅在展开瞬间按输入框中心定位一次 `top`，而 `filterOptions` 每次键入都重建列表（高度变化）却不再重算 `top`，导致列表从下往上缩短、最后贴屏幕顶
  - 抽出 `positionDropdown()`，在 `openDropdown`（设 `display:flex` 后）与 `filterOptions` 每次过滤末尾均调用，使下拉框围绕 LORA 框中心垂直居中、随匹配数量对称展开/收缩
  - 影响文件：`js/multi_lora_loader.js`、`js/multi_lora_loader_only_model.js`

### v2.3.3
- Multi LoRA Loader 与 Multi LoRA Loader (only model) 节点布局二次修复（参照成熟案例）
  - 根因：ComfyUI 前端给 DOM 面板自动加 `h-full`，而其父容器初始高度为 0，导致 `panel.offsetHeight` 只能测到极小值、节点高度计算错误、边框异常
  - 在 `addDOMWidget(...)` 后加入 `panel.classList.remove("h-full")` 并设 `height:auto` / `minHeight:max-content`，让面板按条目真实内容高度展开，节点边框随条目数量自动增减
  - 修复横向只能拉长、不能缩短：自定义 `computeSize()` 原以当前宽度为最小宽度下限，拉宽后无法缩短；改为 `res[0] = node.minWidth || 280`，横向只受真正最小宽度限制，可自由拉长/缩短，纵向内容自适应不受影响

### v2.3.1
- Multi LoRA Loader 与 Multi LoRA Loader (only model) 节点尺寸自适应修复
  - 隐藏的 `lora_data` 多行文本控件现覆写 `computeSize = () => [0, 0]`，让 ComfyUI 布局彻底忽略其高度，避免节点矩形被异常撑高/压低
  - 根因：本版本 ComfyUI 的 `node.computeSize()` 不会可靠地把 DOM 面板控件高度计入节点总高，导致节点被钉在过矮高度、`+ Add LoRA` 按钮溢出节点矩形
  - 改用覆写 `node.computeSize` 与 `node.setSize`：以「面板 `offsetTop` + 面板真实内容高度 + 底部留白」作为节点总高，用户仍可拖大节点但不会被压到比内容更矮
  - 面板高度闭包缓存（`panelHeight`），仅当真实渲染高度 `offsetHeight > 0` 时刷新，杜绝初始/离屏布局偶发测得 `0` 把节点压垮
- 预设导入逻辑简化
  - 删除前端 `resolvePreset` 与后端 `/naiba/presets/resolve` 路由
  - 导入预设（从列表或文件）直接 `setNodeData` 完整套用 JSON 全部条目，不再按本地是否安装对应 LoRA 进行过滤（缺失项在下拉中以红色 `(missing)` 显示）
  - 修复本地未安装对应 LoRA 时（如 `Klein漫转真.json`）无法导入的问题

### v2.3.2
- 预设保存写入 sha256，导入支持按 sha256 定位改名文件（非破坏性）
  - 保存预设时后端自动为每个条目计算并写入 `sha256`（基于本地 LoRA 文件哈希，缺失文件跳过）
  - 重新加入非破坏性 `/naiba/presets/resolve` 路由与前端 `resolvePreset`：
    - 条目含 `sha256` 且本地存在同哈希文件 → 自动改名为本地真实相对路径（改名也能匹配）
    - 含 `sha256` 但本地无匹配 / 不含 `sha256` → 保留原始 `name`，绝不丢弃任何条目
  - **向后兼容**：旧预设（保存时尚未写入 sha256）不含 `sha256`，会原样返回并正常导入
  - 解析失败（网络/后端异常）时自动回退为原始数据，保证导入不中断

### v2.3.0
- 新增 Naiba Textbox 节点
  - 提供可编辑的多行字符串输入框，节点内直接预览/编辑字符串
  - 带 `passthrough` 输入端口，上游字符串传入后自动采用其值并回显到预览框，否则使用输入框内容
  - 输出最终字符串，可向下游节点传递
- Save Text File 默认保存格式调整
  - `filename` 默认值由 `output.txt` 改为 `output.json`，默认保存为 JSON 文件
- Multi LoRA Loader 与 Multi LoRA Loader (only model) 新增悬停封面预览开关
  - 工具栏新增「预览」开关（默认开启）
  - 关闭后，下拉选项与 LoRA 卡片悬停时不再显示封面浮层
  - 开关为节点内存态，不影响加载逻辑与序列化，向后兼容

### v2.2.0
- 可视化 LoRA 加载器（Visual LoRA Loader）UI 重构
  - 卡片化显示区：每个 LoRA 独立卡片，展示名称、启停开关、权重滑块、删除按钮
  - 权重滑块：鼠标滚轮微调 `strength_model` / `strength_clip`，支持直接输入数值
  - 启停开关：一键切换 LoRA 启用状态，关闭后卡片变暗并跳过加载
  - 删除按钮：直接移除单个 LoRA，改动实时写回 `lora_data`
- 预设系统增强
  - 预设封面图：支持为预设设置封面（上传/预览），新增 `/naiba/presets/upload-image` 与 `/naiba/presets/image` 路由
  - 预设搜索过滤：预设列表支持按名称实时筛选
  - 预设导入：无论本地是否安装对应 LoRA，均完整套用预设 JSON 中所有条目（缺失项在下拉中以 `(missing)` 显示），不再过滤未匹配项
- Multi LoRA Loader 下拉体验优化
  - 下拉选项悬停预览封面图，无需选中即可预览
  - 节点尺寸自适应：修复 Add 按钮溢出问题，以面板高度为闭包缓存（仅当真实渲染高度 > 0 时刷新）+ `ResizeObserver` 实时更新节点高度，避免离屏测量为 0 导致节点坍塌，`box-sizing:border-box` 防止内边距溢出
- 后端简化
  - 移除 MultiLoraLoader / MultiLoraLoaderOnlyModel 的 `output_lora_names` 冗余参数，始终输出已启用 LoRA 名称列表

### v2.1.0
- 新增 Power LoRA Config Reader 节点
  - 读取画布上 LoRA 加载器节点的配置信息，转换为 naiba 预设格式 JSON
  - 支持的上游节点：rgthree Power Lora Loader、rgthree Lora Loader Stack、naiba MultiLoraLoader、naiba MultiLoraLoaderOnlyModel、ComfyUI 内置 LoraLoader
  - 通用兜底解析：对未知 LoRA 加载器，自动扫描输入中包含 lora 关键字的字段
  - 三个输出口：`preset_json`（预设格式 JSON）、`lora_names`（启用的 LoRA 文件名列表）、`status`（读取状态）
  - 使用 ComfyUI 隐藏输入 `PROMPT` + `UNIQUE_ID` 追踪上游节点连接链路
  - 通过 MODEL 输入自动定位上游 LoRA 加载器，无需手动指定节点 ID
  - 配合 Save Text File 节点可直接保存为 .json 预设文件

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