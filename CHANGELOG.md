# 更新日志

## v3.5.0 (2026-07-24)

### 新增功能
- **「作品角色」标签页（Danbooru + Gelbooru 双站）**：
  - 两个 Tag Picker 新增「作品角色」画廊分页，在 IP 标签页点卡片左下角 👥 按钮可查看该 IP 下的所有角色列表
  - Danbooru：拉取 posts 聚合 `tag_string_character` 字段计数（匿名即可用，`fate_(series)` 实测返回 120 角色）
  - Gelbooru：登录凭据用 dapi post 聚合+逐个校验 type==4；匿名用户因 dapi 全 401 无法聚合，改用公开 autocomplete 近似回退并给出明确提示
  - 节点新增 `CHARACTER_IP_NAMES` 输出，单独输出作品角色名（不混入 `MERGED_TAGS`，方便单独调控角色权重）
  - 后端新增 `/naiba/tag/ip_characters` 和 `/naiba/gelbooru/ip_characters` 路由，支持分页与磁盘缓存

### Bug 修复
- **「查看角色」按钮位置冲突**：👥 按钮从 IP 卡片右上角移到左下角（`left:6px;bottom:6px`），不再与 🚫黑名单 / ★收藏 按钮重叠
- **画廊渲染静默崩溃**：修复 `state.tabState.ipChar`（驼峰）与 `GALLERY_TABS` 的 `"ip_char"`（下划线）键名不一致，导致 `renderGallery()` 取 `undefined` 抛 TypeError，整页「作品角色」无法渲染
- **Danbooru IP 卡片缺失按钮**：补上之前 Danbooru IP 卡片缺失的「查看角色」👥 按钮（原仅 Gelbooru 有）
- **Gelbooru IP→角色静默为空**：匿名无凭据时不直接返回空，改为匿名近似回退（autocomplete 取名称含该 IP 的角色），并前端区分 `auth_required` / `approximate` 提示

### 新增节点
- **Naiba Anima Formatter**：新增 `naiba_anima_formatter.py` 节点，已注册到 `__init__.py`

### 修复 - Lora Data Preview
- **无节点上下文崩溃**：修复 `createLoraDataPreviewModal` 中 `applyBtn` 在无 `node` 参数时引用空对象的问题

---

## v3.4.0 (2026-07-23)

### Bug 修复
- **Lora Data Preview 本地+Civitai 校验崩溃**：修复 `startCivitaiVerifyFromUpload` 引用 `renderCivitaiCheckView` 内部局部变量（`gateBanner` / `verifyBtn` / `verifyProgressWrap` / `setVerifyProgress`）导致的 `ReferenceError`，改为通过参数传入
- **aiohttp 连接未关闭警告**：修复 `preset_routes` 中 `verify-preset`、`civitai-by-hash`、`civitai-search` 三个接口创建 `CivitaiClient` 后未关闭 session 导致的 `Unclosed client session` / `Unclosed connector` 警告，统一在 `finally` 中关闭

### 优化改进
- **调试按钮可切换**：「列出本地LoRA」调试按钮再次点击可隐藏列表，使用标记自同步状态，避免与校验清空面板后状态错乱
- **「已选择」空状态引导**：未选择任何 LoRA 时显示「去「全部」选择」按钮，可直接跳转回全部列表勾选

---

## v3.2.0 (2026-07-21)

### Bug 修复
- **缓存状态获取失败修复**：修复 `cache_status` 接口访问不存在的 `_DISK_CACHE._index` 属性导致 500 错误，改为遍历目录统计文件数
- **设置面板遗留文本清理**：移除设置面板底部遗留的 "节点上的「随机生成」按钮会自动同步到弹窗扭蛋结果（双向同步）" 叙述

### 新增功能
- **页面关闭停止预加载**：浏览器页面关闭时自动发送停止预加载请求，防止后台线程继续运行

### 优化改进
- **预加载逻辑增强**：预加载现在会主动缓存预览图，持续循环直到缓存空间用满，而非固定 150 个任务

---

## v3.1.0 (2026-07-21)

### 新增功能
- **预览图磁盘缓存按大小限制**：
  - 将磁盘缓存从「按文件数量」限制改为「按磁盘占用大小（MB）」限制
  - 支持 500MB、1000MB 等单位，按总字节 LRU 裁剪
  - 设置面板「文件数」控件改为「缓存上限(MB)」，默认 500MB，范围 100-20000MB
- **标签搜索结果离线缓存**：
  - 标签搜索结果写入同一 `preview_cache/` 文件夹（.json），与图片共用同一 MB 预算
  - 断网时从本地缓存回退，可离线浏览已拉取过的标签
  - 搜索命中离线缓存时在结果中附加 `cached: true` 标记
- **D 站连接状态指示灯**：
  - 弹窗右上角新增 D 站（Danbooru）连接状态指示灯
  - 绿灯表示已连接，红灯表示未连接
  - 状态灯带柔和外发光与轻微呼吸动画
  - 打开弹窗时首次探测，之后每 15 秒轮询
  - 搜索/预览请求失败即时置红，成功置绿

### 新功能
- **后台缓存预加载**：弹窗打开后自动按分类逐页预加载标签到缓存，标题栏显示进度，达到上限自动停止
- **缓存管理面板**：设置页显示当前缓存用量（MB/文件数/百分比），提供「清理缓存」按钮
- **硬性上限保护**：缓存最大限制 50GB，防止用户设置过大

### Bug 修复与优化
- **设置面板缓存描述修正**：`cache_max_items` → `cache_max_mb`，标签「文件数」→「大小(MB)」
- **缓存描述更新**：「预览图缓存」→「本地缓存」，说明包含预览图和标签搜索结果
- **外部随机双向同步**：移除 `sync_external_random` 开关，节点「随机生成」按钮始终同步到弹窗

### 技术改进
- DiskCache 类重构：`max_items` → `max_size_mb`，新增 `get_json/set_json` 方法
- 新增 `/naiba/tag/status` 路由，用于 D 站连接状态探测
- 搜索路由新增 `_consume_cache_params` 调用，支持缓存参数配置
- 控件更名同步：`cache_max_items` → `cache_max_mb`（Python/JS 五处同步）
- 弹窗打开时注册 `_tpSetGacha`/`_tpClearSelection` 回调实现双向同步

---

## v3.0.1 (2026-07-21)

### 问题修复
- **DOM 节点高度修复（anima_prompt_node / naiba_tag_picker）**：
  - 移除 `addDOMWidget` 高度计算中的硬编码 `Math.max(200, …)` 下限，改为按容器真实内容高度（`scrollHeight`）自适应，避免内容较少的节点被强制撑高
  - 新增 `applyContainerHeight()`：在容器完成布局、宽度稳定后调用 `node.setSize()` 将节点高度收敛到真实内容高度
  - 修复初次 `computeSize` 测量时节点 DOM 尚未布局、宽度未定导致 `scrollHeight` 误测成约 2 倍、且旧逻辑仅重绘未重设尺寸而长期停留于错误高度的问题
  - `ResizeObserver` 与初始 `requestAnimationFrame` 均调用 `applyContainerHeight()`，带 >4px 阈值防抖，避免与尺寸监听互相触发抖动

---

## v3.0.0 (2026-07-21)

### 重大改进
- **扭蛋系统重构**：完全移除勾选框机制，改为纯数量驱动
  - 移除复选框，每个分类只保留数量输入框
  - 数量 > 0 表示参与扭蛋，数量 = 0 表示不参与
  - 简化用户操作流程，避免勾选与数量输入的冲突

### 新增功能
- **快速操作按钮**：
  - 「默认值」：一键将所有分类数量设为 3
  - 「清零」：一键将所有分类数量归零
- **数字输入优化**：
  - 所有数量输入框支持直接键盘输入数字
  - 使用 `text` + `inputmode="numeric"` 替代 `type="number"`
  - 自动过滤非数字字符，居中对齐显示

### 问题修复
- **全库标签排除**：
  - 后端 `_gacha_random`、`_gacha_multi`、`_gacha_across` 三个函数均排除"全库标签"分类
  - 前端分类列表过滤"全库标签"，防止重复标签参与扭蛋
  - 双重过滤机制：后端 API + 前端加载均排除
- **默认值调整**：
  - 移除默认数量输入框，改为「默认值」按钮
  - 所有分类默认数量从 3 改为 0
- **输入框修复**：
  - 修复数字输入框只能通过鼠标滚轮修改的问题
  - 支持键盘直接输入数字

### 界面优化
- 扭蛋面板提示文字更新，移除"勾选"相关描述
- 移除不再使用的 `.ap-cat-cb` 复选框样式
- 优化数字输入框外观：居中对齐、移除浏览器默认样式

### 技术改进
- 前端状态管理优化，减少对 `checkedCats` 的依赖
- 后端 `_get_categories()` 自动排除聚合分类
- 统一所有数字输入框的交互方式

---

## v2.x.x (历史版本)
- 详见 git 提交记录
