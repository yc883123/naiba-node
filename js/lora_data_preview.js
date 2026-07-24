/**
 * Lora Data Preview - 前端UI扩展
 * 提供弹窗预览LoRA元数据和预览图，支持批量同步功能
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ========== 颜色常量 ==========
const COLORS = {
    modalBg: "#1a1a2e",
    headerBg: "#16213e",
    contentBg: "#0f1729",
    accent: "#6c5ce7",
    accentHover: "#7c6cf7",
    danger: "#ff6b6b",
    dangerHover: "#ff8b8b",
    success: "#2ed573",
    successBg: "#2ed57320",
    warning: "#ffa502",
    warningBg: "#ffa50220",
    error: "#ff4757",
    favorite: "#ff9f43",      // 收藏按钮颜色（橙色）
    favoriteActive: "#ff6b6b", // 已收藏颜色（红色）
    text: "#e0e0e0",
    textDim: "#888",
    border: "#2a3a5c",
    inputBg: "#0a0f1e",
    cardBg: "#16213e",
    cardBorder: "#2a3a5c",
    sidebarBg: "#0d1117",
    listItemBg: "#1c2333",
    favoriteBorder: "#ff9f43", // 收藏卡片边框颜色
};

// ========== 单例模态框管理 ==========
let currentModal = null;

/**
 * 创建Lora Data Preview模态框
 * @param {Object} node - ComfyUI 节点实例
 * @param {Array} loraList - LoRA文件列表
 */
function createLoraDataPreviewModal(node, loraList) {
    // 防止重复打开
    if (currentModal) {
        currentModal.focus();
        return;
    }

    // ========== 创建模态框容器 ==========
    const overlay = document.createElement("div");
    overlay.style.cssText = `
        position:fixed;top:0;left:0;width:100%;height:100%;
        background:rgba(0,0,0,0.8);z-index:10000;
        display:flex;align-items:center;justify-content:center;
    `;

    const modal = document.createElement("div");
    modal.style.cssText = `
        width:90vw;max-width:1200px;height:85vh;
        background:${COLORS.modalBg};
        border-radius:8px;border:1px solid ${COLORS.border};
        display:flex;flex-direction:column;overflow:hidden;
        box-shadow:0 10px 40px rgba(0,0,0,0.5);
    `;

    // ========== 标题栏 ==========
    const header = document.createElement("div");
    header.style.cssText = `
        display:flex;align-items:center;justify-content:space-between;
        padding:12px 16px;background:${COLORS.headerBg};
        border-bottom:1px solid ${COLORS.border};
    `;

    const title = document.createElement("div");
    title.textContent = "Lora Data Preview - Civitai 同步";
    title.style.cssText = `color:${COLORS.text};font-size:16px;font-weight:600;`;

    const headerRight = document.createElement("div");
    headerRight.style.cssText = "display:flex;align-items:center;gap:12px;";

    // 视图切换按钮（网格/列表）
    const viewToggle = document.createElement("div");
    viewToggle.style.cssText = `
        display:flex;align-items:center;gap:4px;
        background:${COLORS.inputBg};border-radius:4px;padding:2px;
    `;

    const gridViewBtn = document.createElement("button");
    gridViewBtn.textContent = "网格";
    gridViewBtn.style.cssText = `
        padding:4px 8px;border:none;background:${COLORS.accent};
        color:white;border-radius:3px;cursor:pointer;font-size:11px;
    `;

    const listViewBtn = document.createElement("button");
    listViewBtn.textContent = "列表";
    listViewBtn.style.cssText = `
        padding:4px 8px;border:none;background:transparent;
        color:${COLORS.textDim};border-radius:3px;cursor:pointer;font-size:11px;
    `;

    viewToggle.appendChild(gridViewBtn);
    viewToggle.appendChild(listViewBtn);
    headerRight.appendChild(viewToggle);

    gridViewBtn.addEventListener("click", () => {
        currentView = "grid";
        gridViewBtn.style.background = COLORS.accent;
        gridViewBtn.style.color = "white";
        listViewBtn.style.background = "transparent";
        listViewBtn.style.color = COLORS.textDim;
        if (typeof mainContent !== "undefined") renderLoraList();
    });
    listViewBtn.addEventListener("click", () => {
        currentView = "list";
        listViewBtn.style.background = COLORS.accent;
        listViewBtn.style.color = "white";
        gridViewBtn.style.background = "transparent";
        gridViewBtn.style.color = COLORS.textDim;
        if (typeof mainContent !== "undefined") renderLoraList();
    });

    // 批量同步按钮
    const batchSyncBtn = document.createElement("button");
    batchSyncBtn.textContent = "批量同步所有";
    batchSyncBtn.style.cssText = `
        padding:6px 12px;background:${COLORS.accent};
        color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
    `;
    batchSyncBtn.addEventListener("mouseenter", () => {
        batchSyncBtn.style.background = COLORS.accentHover;
    });
    batchSyncBtn.addEventListener("mouseleave", () => {
        batchSyncBtn.style.background = COLORS.accent;
    });
    batchSyncBtn.addEventListener("click", () => {
        startBatchSync();
    });

    // 离线仅计算 SHA256 缓存按钮（不查询 C 站）
    const cacheSha256Btn = document.createElement("button");
    cacheSha256Btn.textContent = "离线缓存SHA256";
    cacheSha256Btn.title = "纯本地扫描所有 LoRA 并计算 sha256 写入全局缓存，完全不调用 Civitai。网络不佳时先收齐本地 sha256。";
    cacheSha256Btn.style.cssText = `
        padding:6px 12px;background:${COLORS.accent2 || COLORS.accent};
        color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
    `;
    cacheSha256Btn.addEventListener("mouseenter", () => {
        cacheSha256Btn.style.background = COLORS.accentHover || COLORS.accent;
    });
    cacheSha256Btn.addEventListener("mouseleave", () => {
        cacheSha256Btn.style.background = COLORS.accent2 || COLORS.accent;
    });
    cacheSha256Btn.addEventListener("click", () => {
        startCacheSha256Only();
    });

    // SHA256 缓存状态徽章（按钮旁的常驻指示）
    const cacheSha256Badge = document.createElement("span");
    cacheSha256Badge.textContent = "SHA256 —";
    cacheSha256Badge.title = "本地 LoRA 的 sha256 全局缓存覆盖状态（由离线缓存/批量同步写入）。绿=全部已缓存，黄=部分缺失，灰=未缓存。";
    cacheSha256Badge.style.cssText = `
        padding:2px 9px;border-radius:10px;font-size:11px;line-height:1.6;
        background:transparent;color:${COLORS.textDim};
        border:1px solid ${COLORS.border};white-space:nowrap;
    `;

    // 关闭按钮
    const closeBtn = document.createElement("div");
    closeBtn.textContent = "\u2715";
    closeBtn.style.cssText = `
        color:${COLORS.textDim};cursor:pointer;font-size:16px;
        padding:4px 8px;border-radius:4px;transition:all 0.15s;
    `;
    closeBtn.addEventListener("mouseenter", () => {
        closeBtn.style.color = COLORS.text;
        closeBtn.style.background = "rgba(255,255,255,0.1)";
    });
    closeBtn.addEventListener("mouseleave", () => {
        closeBtn.style.color = COLORS.textDim;
        closeBtn.style.background = "none";
    });
    closeBtn.addEventListener("click", () => closeModal());

    header.appendChild(title);
    headerRight.appendChild(batchSyncBtn);
    headerRight.appendChild(cacheSha256Btn);
    headerRight.appendChild(cacheSha256Badge);
    header.appendChild(headerRight);

    // 打开弹窗即拉取一次 sha256 缓存状态，刷新按钮旁徽章
    refreshSha256CacheHint();
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // ========== 工具栏 ==========
    const toolbar = document.createElement("div");
    toolbar.style.cssText = `
        display:flex;align-items:center;gap:12px;padding:8px 16px;
        background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};
    `;

    // 视图切换标签
    let currentCategory = "all"; // "all", "selected", "favorite", 或 "civitai-check"
    const tabGroup = document.createElement("div");
    tabGroup.style.cssText = `display:flex;gap:2px;background:${COLORS.inputBg};border-radius:4px;padding:2px;`;

    const tabAll = document.createElement("div");
    tabAll.textContent = "全部";
    tabAll.style.cssText = `
        padding:4px 12px;border-radius:3px;cursor:pointer;font-size:12px;
        background:${COLORS.accent};color:white;
    `;

    const tabSelected = document.createElement("div");
    tabSelected.textContent = "已选择";
    tabSelected.style.cssText = `
        padding:4px 12px;border-radius:3px;cursor:pointer;font-size:12px;
        background:transparent;color:${COLORS.textDim};
    `;

    const tabFavorite = document.createElement("div");
    tabFavorite.textContent = "收藏";
    tabFavorite.style.cssText = `
        padding:4px 12px;border-radius:3px;cursor:pointer;font-size:12px;
        background:transparent;color:${COLORS.textDim};
    `;

    const tabCivitaiCheck = document.createElement("div");
    tabCivitaiCheck.textContent = "Civitai校验";
    tabCivitaiCheck.style.cssText = `
        padding:4px 12px;border-radius:3px;cursor:pointer;font-size:12px;
        background:transparent;color:${COLORS.textDim};
    `;

    const updateTabStyle = () => {
        // 重置所有标签样式
        tabAll.style.background = "transparent";
        tabAll.style.color = COLORS.textDim;
        tabSelected.style.background = "transparent";
        tabSelected.style.color = COLORS.textDim;
        tabFavorite.style.background = "transparent";
        tabFavorite.style.color = COLORS.textDim;
        tabCivitaiCheck.style.background = "transparent";
        tabCivitaiCheck.style.color = COLORS.textDim;
        
        // 设置当前活动标签样式
        if (currentCategory === "all") {
            tabAll.style.background = COLORS.accent;
            tabAll.style.color = "white";
        } else if (currentCategory === "selected") {
            tabSelected.style.background = COLORS.accent;
            tabSelected.style.color = "white";
        } else if (currentCategory === "favorite") {
            tabFavorite.style.background = COLORS.favorite;
            tabFavorite.style.color = "white";
        } else if (currentCategory === "civitai-check") {
            tabCivitaiCheck.style.background = COLORS.warning;
            tabCivitaiCheck.style.color = "white";
        }
    };

    const updateStatusDisplay = () => {
        const searchTerm = searchInput.value.toLowerCase();
        let baseLoras = searchTerm 
            ? loraList.filter(lora => lora.toLowerCase().includes(searchTerm))
            : loraList;
        
        if (currentCategory === "selected") {
            const selectedCount = baseLoras.filter(l => selectedLoras.has(l)).length;
            statusDisplay.textContent = searchTerm 
                ? `已选择: ${selectedCount} 个结果` 
                : `已选择: ${selectedCount} 个LoRA`;
        } else if (currentCategory === "favorite") {
            const favCount = baseLoras.filter(l => favoriteLoras.has(l)).length;
            statusDisplay.textContent = searchTerm 
                ? `收藏: ${favCount} 个结果` 
                : `收藏: ${favCount} 个LoRA`;
        } else if (currentCategory === "civitai-check") {
            statusDisplay.textContent = "Civitai校验模式";
        } else {
            statusDisplay.textContent = searchTerm 
                ? `搜索: ${baseLoras.length} 个结果` 
                : `全部: ${baseLoras.length} 个LoRA`;
        }
    };

    tabAll.addEventListener("click", () => {
        currentCategory = "all";
        updateTabStyle();
        updateStatusDisplay();
        renderLoraList();
    });

    tabSelected.addEventListener("click", () => {
        currentCategory = "selected";
        updateTabStyle();
        updateStatusDisplay();
        renderLoraList();
    });

    tabFavorite.addEventListener("click", () => {
        currentCategory = "favorite";
        updateTabStyle();
        updateStatusDisplay();
        renderLoraList();
    });

    tabCivitaiCheck.addEventListener("click", () => {
        currentCategory = "civitai-check";
        updateTabStyle();
        updateStatusDisplay();
        renderLoraList();
    });

    tabGroup.appendChild(tabAll);
    tabGroup.appendChild(tabSelected);
    tabGroup.appendChild(tabFavorite);
    tabGroup.appendChild(tabCivitaiCheck);

    // 搜索框
    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "搜索LoRA...";
    searchInput.style.cssText = `
        flex:1;max-width:250px;padding:6px 10px;
        background:${COLORS.inputBg};border:1px solid ${COLORS.border};
        border-radius:4px;color:${COLORS.text};font-size:12px;outline:none;
    `;

    // 状态显示
    const statusDisplay = document.createElement("div");
    statusDisplay.style.cssText = `color:${COLORS.textDim};font-size:12px;flex:1;`;
    statusDisplay.textContent = `共 ${loraList.length} 个LoRA文件`;

    toolbar.appendChild(tabGroup);
    toolbar.appendChild(searchInput);
    toolbar.appendChild(statusDisplay);
    modal.appendChild(toolbar);

    // 当前目录面包屑（对标 visual_lora_loader.js：必须声明 currentPath 为 DOM 元素，
    // 否则目录点击 handler 中访问 currentPath.textContent 会抛 ReferenceError，导致列表不刷新）
    const pathBar = document.createElement("div");
    pathBar.style.cssText = `
        display:flex;align-items:center;gap:6px;padding:6px 16px;
        background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};
        font-size:12px;color:${COLORS.textDim};
    `;
    const pathLabel = document.createElement("span");
    pathLabel.textContent = "当前目录:";
    pathLabel.style.cssText = `color:${COLORS.textDim};`;
    const currentPath = document.createElement("span");
    currentPath.style.cssText = `color:${COLORS.accent};font-weight:500;`;
    currentPath.textContent = "/";
    pathBar.appendChild(pathLabel);
    pathBar.appendChild(currentPath);
    modal.appendChild(pathBar);

    // ========== 内容区域 ==========
    const content = document.createElement("div");
    content.style.cssText = `
        flex:1;display:flex;overflow:hidden;
    `;

    // 左侧文件夹树
    const sidebar = document.createElement("div");
    sidebar.style.cssText = `
        width:200px;border-right:1px solid ${COLORS.border};
        overflow-y:auto;padding:8px;
    `;

    // 右侧LoRA列表
    const mainContent = document.createElement("div");
    mainContent.style.cssText = `
        flex:1;overflow-y:auto;padding:8px;
    `;

    content.appendChild(sidebar);
    content.appendChild(mainContent);
    modal.appendChild(content);

    // 进度条（批量同步时显示）
    const progressBarContainer = document.createElement("div");
    progressBarContainer.style.cssText = `
        display:none;margin-bottom:16px;padding:12px;
        background:${COLORS.headerBg};border-radius:6px;
        border:1px solid ${COLORS.border};
    `;

    const progressBarTitle = document.createElement("div");
    progressBarTitle.style.cssText = `color:${COLORS.text};font-size:14px;font-weight:500;margin-bottom:8px;`;

    const progressBar = document.createElement("div");
    progressBar.style.cssText = `
        width:100%;height:8px;background:${COLORS.inputBg};
        border-radius:4px;overflow:hidden;margin-bottom:8px;
    `;

    const progressBarInner = document.createElement("div");
    progressBarInner.style.cssText = `
        width:0%;height:100%;background:${COLORS.accent};
        transition:width 0.3s ease;
    `;
    progressBar.appendChild(progressBarInner);

    const progressBarStatus = document.createElement("div");
    progressBarStatus.style.cssText = `color:${COLORS.textDim};font-size:12px;`;

    progressBarContainer.appendChild(progressBarTitle);
    progressBarContainer.appendChild(progressBar);
    progressBarContainer.appendChild(progressBarStatus);

    // ========== 底部状态栏 ==========
    const statusBar = document.createElement("div");
    statusBar.style.cssText = `
        display:flex;align-items:center;justify-content:space-between;
        padding:8px 16px;background:${COLORS.headerBg};
        border-top:1px solid ${COLORS.border};
    `;

    const syncStatus = document.createElement("span");
    syncStatus.style.cssText = `color:${COLORS.textDim};font-size:12px;`;
    syncStatus.textContent = "就绪";

    // SHA256 全局缓存状态提示（批量同步/离线缓存后显示）
    const sha256CacheHint = document.createElement("span");
    sha256CacheHint.style.cssText = `color:${COLORS.success};font-size:12px;margin-left:8px;display:none;`;
    sha256CacheHint.title = "本地 LoRA 的 sha256 全局缓存状态，供上传预设做本地匹配";

    async function refreshSha256CacheHint() {
        try {
            const ctrl = new AbortController();
            const tid = setTimeout(() => ctrl.abort(), 8000);
            const resp = await fetch('/naiba/lora/sha256-cache', { signal: ctrl.signal });
            clearTimeout(tid);
            const data = await resp.json();
            if (data && data.success) {
                if (data.all_cached && data.cached_count > 0) {
                    sha256CacheHint.textContent = `✓ 所有 LoRA 已有 sha256 缓存（共 ${data.cached_count} 个）`;
                    sha256CacheHint.style.color = COLORS.success;
                } else {
                    sha256CacheHint.textContent = `⚠ 已缓存 ${data.cached_count}/${data.total_loras} 个 sha256（缺失 ${data.missing_count} 个）`;
                    sha256CacheHint.style.color = '#d29922';
                }
                sha256CacheHint.style.display = 'inline';

                // 按钮旁徽章：绿=全部，黄=部分，灰=未缓存
                if (data.cached_count === 0) {
                    cacheSha256Badge.textContent = "SHA256 未缓存";
                    cacheSha256Badge.style.background = "transparent";
                    cacheSha256Badge.style.color = COLORS.textDim;
                } else if (data.all_cached) {
                    cacheSha256Badge.textContent = `SHA256 ✓ ${data.cached_count}/${data.total_loras}`;
                    cacheSha256Badge.style.background = COLORS.successBg;
                    cacheSha256Badge.style.color = COLORS.success;
                } else {
                    cacheSha256Badge.textContent = `SHA256 ${data.cached_count}/${data.total_loras}`;
                    cacheSha256Badge.style.background = COLORS.warningBg;
                    cacheSha256Badge.style.color = COLORS.warning;
                }
            }
        } catch (e) {
            // 接口不可用时静默
        }
    }

    const buttonGroup = document.createElement("div");
    buttonGroup.style.cssText = "display:flex;gap:8px;";

    const refreshBtn = document.createElement("button");
    refreshBtn.textContent = "刷新列表";
    refreshBtn.style.cssText = `
        padding:6px 12px;background:transparent;
        color:${COLORS.textDim};border:1px solid ${COLORS.border};
        border-radius:4px;cursor:pointer;font-size:12px;
    `;
    refreshBtn.addEventListener("click", async () => {
        refreshBtn.disabled = true;
        refreshBtn.textContent = "刷新中...";
        try {
            const resp = await api.fetchApi("/object_info/LoraLoader");
            const info = await resp.json();
            if (info.LoraLoader?.input?.required?.lora_name) {
                const newList = info.LoraLoader.input.required.lora_name[0] || [];
                // 更新 loraList（通过闭包引用的外部变量）
                loraList.length = 0;
                loraList.push(...newList);
                folderStructure = buildFolderStructure(loraList);
                currentFolder = "/";
                currentPath.textContent = "/";
                statusDisplay.textContent = `共 ${loraList.length} 个LoRA文件`;
                renderFolderTree();
                renderLoraList();
            }
        } catch (e) {
            console.warn("[LoraDataPreview] 刷新列表失败:", e);
        }
        refreshBtn.textContent = "刷新列表";
        refreshBtn.disabled = false;
    });

    // 全选按钮
    const selectAllBtn = document.createElement("button");
    selectAllBtn.textContent = "全选";
    selectAllBtn.style.cssText = `
        padding:6px 12px;background:transparent;
        color:${COLORS.textDim};border:1px solid ${COLORS.border};
        border-radius:4px;cursor:pointer;font-size:12px;
    `;
    selectAllBtn.addEventListener("click", () => {
        const searchTerm = (searchInput.value || "").toLowerCase().trim();
        let list = [];
        if (currentCategory === "selected") list = Array.from(selectedLoras.keys());
        else if (currentCategory === "favorite") list = Array.from(favoriteLoras.keys());
        else list = getLorasInFolder(currentFolder);
        if (searchTerm) list = list.filter(lora => lora.toLowerCase().includes(searchTerm));
        list.forEach(lora => selectedLoras.add(lora));
        renderLoraList();
    });

    // 清除选择按钮
    const clearSelectBtn = document.createElement("button");
    clearSelectBtn.textContent = "清除";
    clearSelectBtn.style.cssText = `
        padding:6px 12px;background:transparent;
        color:${COLORS.textDim};border:1px solid ${COLORS.border};
        border-radius:4px;cursor:pointer;font-size:12px;
    `;
    clearSelectBtn.addEventListener("click", () => {
        selectedLoras.clear();
        renderLoraList();
    });

    // 应用按钮（仅在节点上下文中显示）
    let applyBtn;
    if (node) {
        applyBtn = document.createElement("button");
        applyBtn.textContent = "应用选中 (0)";
        applyBtn.style.cssText = `
            padding:6px 12px;background:${COLORS.success};
            color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
        `;
        applyBtn.addEventListener("click", () => {
            applySelectedLora();
        });
    }

    const closeFooterBtn = document.createElement("button");
    closeFooterBtn.textContent = "关闭";
    closeFooterBtn.style.cssText = `
        padding:6px 12px;background:${COLORS.accent};
        color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
    `;
    closeFooterBtn.addEventListener("click", () => closeModal());

    buttonGroup.appendChild(refreshBtn);
    buttonGroup.appendChild(selectAllBtn);
    buttonGroup.appendChild(clearSelectBtn);
    if (applyBtn) buttonGroup.appendChild(applyBtn);
    buttonGroup.appendChild(closeFooterBtn);

    statusBar.appendChild(syncStatus);
    statusBar.appendChild(sha256CacheHint);
    statusBar.appendChild(buttonGroup);
    modal.appendChild(statusBar);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // ========== 内部状态 ==========
    let filteredLoras = [...loraList];
    let isSyncing = false;
    let selectedLoras = new Set(); // 已选中的LoRA集合（支持多选）
    let favoriteLoras = new Map(); // 收藏的LoRA集合 (name -> {custom_prompt, custom_image_path, favorited_at})
    let modalTimestamp = Date.now(); // 模态框级别时间戳，用于缓存破坏，确保预览图一致性

    // 视图/文件夹/类别状态
    let currentView = "grid";      // "grid" 或 "list"
    let currentFolder = "/";       // 当前文件夹
    let folderStructure = buildFolderStructure(loraList);
    
    // Civitai校验相关变量
    let checkVerifyResultsContent = null;
    let checkMissingContent = null;
    let checkMissingSection = null;

    // 从节点widget中恢复已选中的LoRA，确保重新打开弹窗时"已选择"标签能正确显示
    if (node) {
        const existingDataWidget = node.widgets?.find((w) => w.name === "lora_data");
        if (existingDataWidget) {
            try {
                const existingData = JSON.parse(existingDataWidget.value || "[]");
                existingData.forEach(item => {
                    if (item.name) {
                        selectedLoras.add(item.name);
                    }
                });
            } catch (e) {
                // ignore parse errors
            }
        }
    }

    // ========== 构建文件夹结构 ==========
    function buildFolderStructure(loraList) {
        const structure = { "/": [] };
        loraList.forEach(lora => {
            const parts = lora.split(/[\\/]/);
            if (parts.length === 1) {
                structure["/"].push(lora);
            } else {
                let cur = "/";
                for (let i = 0; i < parts.length - 1; i++) {
                    const folder = parts[i];
                    const parentPath = cur;
                    cur = cur === "/" ? `/${folder}` : `${cur}/${folder}`;
                    if (!structure[cur]) {
                        structure[cur] = [];
                        if (!structure[parentPath]) structure[parentPath] = [];
                        if (!structure[parentPath].includes(folder + "/")) {
                            structure[parentPath].push(folder + "/");
                        }
                    }
                }
                if (!structure[cur]) structure[cur] = [];
                structure[cur].push(parts[parts.length - 1]);
            }
        });
        return structure;
    }

    // ========== 获取文件夹中的LoRA ==========
    function getLorasInFolder(folder) {
        const items = folderStructure[folder] || [];
        const loras = [];
        items.forEach(item => {
            if (item.endsWith("/")) {
                const subFolder = folder === "/" ? `/${item.slice(0, -1)}` : `${folder}/${item.slice(0, -1)}`;
                loras.push(...getLorasInFolder(subFolder));
            } else {
                const fullPath = folder === "/" ? item : `${folder}/${item}`;
                loras.push(fullPath);
            }
        });
        return loras;
    }

    // ========== 渲染文件夹树 ==========
    function renderFolderTree() {
        sidebar.innerHTML = "";
        const rootItem = document.createElement("div");
        rootItem.textContent = "根目录";
        rootItem.style.cssText = `
            padding:6px 8px;cursor:pointer;font-size:12px;
            color:${currentFolder === "/" ? COLORS.accent : COLORS.text};
            background:${currentFolder === "/" ? COLORS.listItemActive : "transparent"};
            border-radius:4px;margin-bottom:4px;
        `;
        rootItem.addEventListener("click", () => {
            currentFolder = "/";
            currentPath.textContent = "/";
            renderFolderTree();
            renderLoraList();
        });
        sidebar.appendChild(rootItem);
        renderFolderLevel("/", sidebar, 0);
    }

    function renderFolderLevel(folder, container, depth) {
        const items = folderStructure[folder] || [];
        const folders = items.filter(item => item.endsWith("/"));
        folders.forEach(folderItem => {
            const folderName = folderItem.slice(0, -1);
            const fullPath = folder === "/" ? `/${folderName}` : `${folder}/${folderName}`;
            const folderElement = document.createElement("div");
            folderElement.style.cssText = `
                padding:4px 8px 4px ${8 + depth * 16}px;cursor:pointer;font-size:12px;
                color:${currentFolder === fullPath ? COLORS.accent : COLORS.text};
                background:${currentFolder === fullPath ? COLORS.listItemActive : "transparent"};
                border-radius:4px;margin-bottom:2px;
            `;
            const folderIcon = document.createElement("span");
            folderIcon.textContent = "📁 ";
            folderIcon.style.cssText = "margin-right:4px;";
            const folderText = document.createElement("span");
            folderText.textContent = folderName;
            folderElement.appendChild(folderIcon);
            folderElement.appendChild(folderText);
            folderElement.addEventListener("click", () => {
                currentFolder = fullPath;
                currentPath.textContent = fullPath;
                renderFolderTree();
                renderLoraList();
            });
            container.appendChild(folderElement);
            renderFolderLevel(fullPath, container, depth + 1);
        });
    }

    // ========== 关闭模态框 ==========
    function closeModal() {
        document.body.removeChild(overlay);
        currentModal = null;
        document.removeEventListener("keydown", escHandler);
    }

    // ========== 加载收藏数据 ==========
    async function loadFavorites() {
        try {
            const response = await api.fetchApi('/naiba/lora/favorites/list');
            const result = await response.json();
            if (result.success && result.favorites) {
                favoriteLoras.clear();
                Object.entries(result.favorites).forEach(([name, data]) => {
                    favoriteLoras.set(name, data);
                });
            }
        } catch (e) {
            console.warn("[LoraDataPreview] 加载收藏数据失败:", e);
        }
    }

    // ========== 切换收藏状态 ==========
    async function toggleFavorite(loraName) {
        const isFavorited = favoriteLoras.has(loraName);
        
        try {
            if (isFavorited) {
                // 取消收藏
                const response = await api.fetchApi(`/naiba/lora/favorites/remove?name=${encodeURIComponent(loraName)}`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (result.success) {
                    favoriteLoras.delete(loraName);
                    renderLoraList();
                }
            } else {
                // 添加收藏
                const response = await api.fetchApi('/naiba/lora/favorites/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: loraName })
                });
                const result = await response.json();
                if (result.success && result.favorite) {
                    favoriteLoras.set(loraName, result.favorite);
                    renderLoraList();
                }
            }
        } catch (e) {
            console.warn("[LoraDataPreview] 收藏操作失败:", e);
        }
    }

    // ========== 应用选中的LoRA ==========
    function applySelectedLora() {
        if (!node) return;
        if (selectedLoras.size === 0) {
            alert("请先选择至少一个LoRA");
            return;
        }

        // 更新节点的lora_data字段
        const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
        if (loraDataWidget) {
            const data = Array.from(selectedLoras).map(name => ({
                name: name,
                strength_model: 1.0,
                strength_clip: 1.0,
                enabled: true
            }));
            loraDataWidget.value = JSON.stringify(data);
        }

        // 更新节点预览
        if (node._updateLoraDataPreview) {
            node._updateLoraDataPreview();
        }

        // 关闭弹窗
        closeModal();
    }

    // ESC 关闭
    const escHandler = (e) => {
        if (e.key === "Escape") closeModal();
    };
    document.addEventListener("keydown", escHandler);

    // ========== 搜索功能 ==========
    searchInput.addEventListener("input", () => {
        const searchTerm = searchInput.value.toLowerCase();
        if (searchTerm) {
            filteredLoras = loraList.filter(lora => 
                lora.toLowerCase().includes(searchTerm)
            );
        } else {
            filteredLoras = [...loraList];
        }
        updateStatusDisplay();
        renderLoraList();
    });

    // ========== 渲染LoRA列表 ==========
    function renderLoraList() {
        mainContent.innerHTML = "";
        // 进度条（批量同步时显示）
        mainContent.appendChild(progressBarContainer);

        // 更新应用按钮文本显示选中数量
        if (applyBtn) applyBtn.textContent = `应用选中 (${selectedLoras.size})`;

        // 根据类别 / 文件夹 / 搜索确定渲染列表
        const searchTerm = (searchInput.value || "").toLowerCase().trim();
        let displayLoras = [];
        if (currentCategory === "selected") {
            displayLoras = Array.from(selectedLoras.keys());
        } else if (currentCategory === "favorite") {
            displayLoras = Array.from(favoriteLoras.keys());
        } else if (currentCategory === "civitai-check") {
            // Civitai校验模式：显示基于lora_data的校验视图
            renderCivitaiCheckView();
            return;
        } else {
            displayLoras = getLorasInFolder(currentFolder);
        }
        if (searchTerm) {
            displayLoras = displayLoras.filter(lora => lora.toLowerCase().includes(searchTerm));
        }

        if (displayLoras.length === 0) {
            const emptyMsg = document.createElement("div");
            emptyMsg.style.cssText = `
                color:${COLORS.textDim};text-align:center;padding:40px;font-size:14px;
                display:flex;flex-direction:column;align-items:center;gap:14px;
            `;
            if (currentCategory === "selected") {
                const tip = document.createElement("div");
                tip.textContent = "尚未选择任何LoRA";
                emptyMsg.appendChild(tip);
                const goBtn = document.createElement("button");
                goBtn.textContent = "去「全部」选择";
                goBtn.style.cssText = `
                    padding:8px 16px;background:${COLORS.accent};color:white;
                    border:none;border-radius:4px;cursor:pointer;font-size:12px;
                `;
                goBtn.addEventListener("click", () => {
                    currentCategory = "all";
                    currentFolder = currentFolder || "all";
                    updateTabStyle();
                    updateStatusDisplay();
                    renderLoraList();
                });
                emptyMsg.appendChild(goBtn);
            } else if (currentCategory === "favorite") {
                emptyMsg.textContent = "尚未收藏任何LoRA";
            } else {
                emptyMsg.textContent = searchTerm ? "没有匹配的LoRA文件" : "没有找到LoRA文件";
            }
            mainContent.appendChild(emptyMsg);
            return;
        }

        // 列表视图
        if (currentView === "list") {
            const list = document.createElement("div");
            list.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:8px;";
            displayLoras.forEach(lora => {
                const isSelected = selectedLoras.has(lora);
                const isFavorited = favoriteLoras.has(lora);
                const item = document.createElement("div");
                item.style.cssText = `
                    display:flex;align-items:center;gap:12px;
                    padding:8px 12px;background:${COLORS.listItemBg};
                    border-radius:4px;cursor:pointer;transition:all 0.2s;
                    border:${isSelected ? "2px solid " + COLORS.accent : "1px solid transparent"};
                `;
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.checked = isSelected;
                checkbox.addEventListener("click", (e) => e.stopPropagation());
                const name = document.createElement("span");
                name.textContent = lora.split('/').pop().split('\\').pop();
                name.style.cssText = `color:${COLORS.text};font-size:12px;flex:1;`;
                const path = document.createElement("span");
                path.textContent = lora;
                path.style.cssText = `color:${COLORS.textDim};font-size:11px;flex:2;`;
                const favBtn = document.createElement("div");
                favBtn.textContent = isFavorited ? "♥" : "♡";
                favBtn.title = isFavorited ? "取消收藏" : "收藏";
                favBtn.style.cssText = `width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:14px;color:${isFavorited ? COLORS.favoriteActive : COLORS.textDim};`;
                favBtn.addEventListener("click", async (e) => { e.stopPropagation(); await toggleFavorite(lora); });
                const btnWrap = document.createElement("div");
                btnWrap.style.cssText = "display:flex;gap:4px;";
                const mkBtn = (label, bg, handler) => {
                    const b = document.createElement("button");
                    b.textContent = label;
                    b.style.cssText = `padding:4px 8px;background:${bg};color:white;border:none;border-radius:3px;cursor:pointer;font-size:11px;`;
                    b.addEventListener("click", async (e) => { e.stopPropagation(); await handler(b); });
                    return b;
                };
                btnWrap.appendChild(mkBtn("同步", COLORS.accent, (btn) => syncSingleLora(lora, btn)));
                btnWrap.appendChild(mkBtn("编辑", "transparent", () => showEditPanel(lora)));
                btnWrap.appendChild(mkBtn("详情", "transparent", () => showLoraDetail(lora)));
                item.appendChild(checkbox);
                item.appendChild(name);
                item.appendChild(path);
                item.appendChild(favBtn);
                item.appendChild(btnWrap);
                item.addEventListener("click", () => {
                    if (selectedLoras.has(lora)) selectedLoras.delete(lora);
                    else selectedLoras.add(lora);
                    renderLoraList();
                });
                list.appendChild(item);
            });
            mainContent.appendChild(list);
            return;
        }

        // 网格视图
        const grid = document.createElement("div");
        grid.style.cssText = `
            display:grid;grid-template-columns:repeat(auto-fill, minmax(280px, 1fr));
            gap:12px;padding:8px;
        `;

        displayLoras.forEach(lora => {
            const isSelected = selectedLoras.has(lora);
            const isFavorited = favoriteLoras.has(lora);
            const card = document.createElement("div");
            
            // 卡片边框样式：选中=绿色，收藏=橙色，普通=默认
            let borderColor = COLORS.cardBorder;
            let boxShadow = '';
            if (isSelected) {
                borderColor = COLORS.success;
                boxShadow = `box-shadow:0 0 0 2px ${COLORS.success}40;`;
            } else if (isFavorited) {
                borderColor = COLORS.favoriteBorder;
                boxShadow = `box-shadow:0 0 0 2px ${COLORS.favoriteBorder}40;`;
            }
            
            card.style.cssText = `
                background:${COLORS.cardBg};border:1px solid ${borderColor};
                border-radius:6px;padding:12px;cursor:pointer;
                transition:all 0.2s;position:relative;
                ${boxShadow}
            `;

            // 卡片点击事件 - 切换选中状态（支持多选）
            card.addEventListener("click", () => {
                if (selectedLoras.has(lora)) {
                    selectedLoras.delete(lora);
                } else {
                    selectedLoras.add(lora);
                }
                renderLoraList(); // 重新渲染以更新选中状态
            });

            // 图片预览区域
            const preview = document.createElement("div");
            preview.style.cssText = `
                width:100%;height:160px;background:${COLORS.inputBg};
                border-radius:4px;margin-bottom:8px;display:flex;
                align-items:center;justify-content:center;
                color:${COLORS.textDim};font-size:12px;overflow:hidden;
                position:relative;
            `;

            // 收藏按钮（右上角）
            const favBtn = document.createElement("div");
            favBtn.style.cssText = `
                position:absolute;top:8px;right:8px;z-index:10;
                width:28px;height:28px;border-radius:50%;
                display:flex;align-items:center;justify-content:center;
                cursor:pointer;font-size:16px;
                background:rgba(0,0,0,0.5);backdrop-filter:blur(4px);
                transition:all 0.2s;
                color:${isFavorited ? COLORS.favoriteActive : COLORS.textDim};
            `;
            favBtn.textContent = isFavorited ? "♥" : "♡";
            favBtn.title = isFavorited ? "取消收藏" : "收藏";
            favBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                await toggleFavorite(lora);
            });
            favBtn.addEventListener("mouseenter", () => {
                favBtn.style.transform = "scale(1.1)";
            });
            favBtn.addEventListener("mouseleave", () => {
                favBtn.style.transform = "scale(1)";
            });
            preview.appendChild(favBtn);

            // 预览图
            const previewImg = document.createElement("img");
            previewImg.style.cssText = `
                width:100%;height:100%;object-fit:cover;
            `;

            // 加载元数据
            let hasLoadedMetadata = false;
            let metadataCache = null;

            previewImg.onerror = async () => {
                if (!hasLoadedMetadata) {
                    hasLoadedMetadata = true;
                    preview.innerHTML = `<div style="color:${COLORS.textDim};font-size:11px;">正在加载...</div>`;
                    // 重新添加收藏按钮
                    preview.appendChild(favBtn);
                    
                    try {
                        // 获取元数据（10秒超时）
                        const metaController = new AbortController();
                        const metaTimeoutId = setTimeout(() => metaController.abort(), 10000);
                        const metadataResponse = await fetch(`/naiba/lora/metadata?name=${encodeURIComponent(lora)}`, { signal: metaController.signal });
                        clearTimeout(metaTimeoutId);
                        const metadataResult = await metadataResponse.json();
                        
                        if (metadataResult.success && metadataResult.metadata) {
                            metadataCache = metadataResult.metadata;
                            
                            // 如果有预览图，显示它
                            if (metadataResult.has_local_preview) {
                                const previewUrl = `/naiba/lora/preview?name=${encodeURIComponent(lora)}&t=${modalTimestamp}`;
                                previewImg.src = previewUrl;
                                return;
                            }
                            
                            // 显示元数据摘要
                            showMetadataPreview(preview, metadataResult.metadata);
                            preview.appendChild(favBtn);
                        } else {
                            preview.innerHTML = `<div style="color:${COLORS.textDim};font-size:11px;">无预览图</div>`;
                            preview.appendChild(favBtn);
                        }
                    } catch (error) {
                        if (error.name === 'AbortError') {
                            preview.innerHTML = `<div style="color:${COLORS.textDim};font-size:11px;">加载超时</div>`;
                        } else {
                            console.warn("[LoraDataPreview] 加载元数据失败:", error);
                            preview.innerHTML = `<div style="color:${COLORS.textDim};font-size:11px;">加载失败</div>`;
                        }
                        preview.appendChild(favBtn);
                    }
                } else {
                    preview.innerHTML = `<div style="color:${COLORS.textDim};font-size:11px;">无预览图</div>`;
                    preview.appendChild(favBtn);
                }
            };

            // 显示元数据预览
            function showMetadataPreview(container, metadata) {
                let html = `<div style="padding:8px;text-align:left;">`;
                
                if (metadata.model_name) {
                    html += `<div style="color:${COLORS.text};font-size:12px;font-weight:500;margin-bottom:4px;">${metadata.model_name}</div>`;
                }
                
                if (metadata.version_name) {
                    html += `<div style="color:${COLORS.textDim};font-size:11px;margin-bottom:4px;">${metadata.version_name}</div>`;
                }
                
                const triggerWords = metadata.trigger_words || metadata.trained_words || [];
                if (triggerWords.length > 0) {
                    html += `<div style="color:${COLORS.accent};font-size:10px;margin-top:4px;">触发词: ${triggerWords.slice(0, 3).join(', ')}</div>`;
                }
                
                html += `</div>`;
                container.innerHTML = html;
            }

            // 预览图：优先使用自定义预览图，Civitai预览图作为fallback
            const previewUrl = `/naiba/lora/preview?name=${encodeURIComponent(lora)}&t=${modalTimestamp}`;
            previewImg.src = previewUrl;
            preview.appendChild(previewImg);

            // LoRA名称
            const name = document.createElement("div");
            name.textContent = lora.split('/').pop().split('\\').pop();
            name.style.cssText = `
                color:${COLORS.text};font-size:12px;font-weight:500;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
            `;

            // 文件路径
            const path = document.createElement("div");
            path.textContent = lora;
            path.style.cssText = `
                color:${COLORS.textDim};font-size:10px;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                margin-top:4px;
            `;

            // 操作按钮
            const actionButtons = document.createElement("div");
            actionButtons.style.cssText = `
                display:flex;gap:4px;margin-top:8px;
            `;

            // 同步按钮
            const syncBtn = document.createElement("button");
            syncBtn.textContent = "同步";
            syncBtn.style.cssText = `
                flex:1;padding:4px 8px;background:${COLORS.accent};
                color:white;border:none;border-radius:3px;cursor:pointer;font-size:11px;
            `;
            syncBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                await syncSingleLora(lora, syncBtn);
            });

            // 编辑自定义数据按钮（所有LoRA可用）
            const editBtn = document.createElement("button");
            editBtn.textContent = "编辑";
            editBtn.style.cssText = `
                padding:4px 8px;background:transparent;
                color:${COLORS.textDim};border:1px solid ${COLORS.border};
                border-radius:3px;cursor:pointer;font-size:11px;
            `;
            editBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                showEditPanel(lora);
            });

            // 查看详情按钮
            const detailBtn = document.createElement("button");
            detailBtn.textContent = "详情";
            detailBtn.style.cssText = `
                flex:1;padding:4px 8px;background:transparent;
                color:${COLORS.textDim};border:1px solid ${COLORS.border};
                border-radius:3px;cursor:pointer;font-size:11px;
            `;
            detailBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                showLoraDetail(lora);
            });

            actionButtons.appendChild(syncBtn);
            actionButtons.appendChild(editBtn);
            actionButtons.appendChild(detailBtn);

            card.appendChild(preview);
            card.appendChild(name);
            card.appendChild(path);
            card.appendChild(actionButtons);

            grid.appendChild(card);
        });

        mainContent.appendChild(grid);
    }

    // ========== Civitai校验视图 ==========
    function renderCivitaiCheckView() {
        mainContent.innerHTML = "";
        mainContent.appendChild(progressBarContainer);
        
        // 创建校验视图容器
        const checkContainer = document.createElement("div");
        checkContainer.style.cssText = `
            display:flex;flex-direction:column;height:100%;
        `;
        
        // 创建顶部区域：上传JSON + 校验按钮
        const topSection = document.createElement("div");
        topSection.style.cssText = `
            display:flex;flex-direction:column;gap:8px;padding:8px;
            border-bottom:1px solid ${COLORS.border};
        `;

        // 执行门提示条（常驻）：要求先建立 sha256 全局缓存
        const gateBanner = document.createElement("div");
        gateBanner.textContent = "⚠ 请确定所有 LoRA 都已有 sha256 缓存，否则不要执行（请先执行批量同步 / 离线缓存SHA256）";
        gateBanner.style.cssText = `
            padding:6px 10px;border-radius:5px;font-size:11px;line-height:1.4;
            background:rgba(210,153,34,0.15);border:1px solid #d29922;color:#d29922;
        `;
        topSection.appendChild(gateBanner);
        
        // 上传JSON区域
        const uploadRow = document.createElement("div");
        uploadRow.style.cssText = `
            display:flex;gap:8px;align-items:center;
        `;
        
        const uploadTitle = document.createElement("div");
        uploadTitle.textContent = "上传预设JSON校验";
        uploadTitle.style.cssText = `
            color:${COLORS.text};font-size:14px;font-weight:500;
        `;
        
        const uploadBtn = document.createElement("button");
        uploadBtn.textContent = "选择JSON文件";
        uploadBtn.style.cssText = `
            padding:8px 16px;background:${COLORS.accent};
            color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
        `;
        
        const uploadFileName = document.createElement("span");
        uploadFileName.textContent = "未选择文件";
        uploadFileName.style.cssText = `
            color:${COLORS.textDim};font-size:12px;
        `;
        
        // 隐藏的文件输入
        const fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.accept = ".json";
        fileInput.style.display = "none";
        
        uploadRow.appendChild(uploadTitle);
        uploadRow.appendChild(uploadBtn);
        uploadRow.appendChild(uploadFileName);
        uploadRow.appendChild(fileInput);
        
        // 校验按钮
        const verifyRow = document.createElement("div");
        verifyRow.style.cssText = `
            display:flex;gap:8px;align-items:center;
        `;
        
        const verifyBtn = document.createElement("button");
        verifyBtn.textContent = "开始校验（本地+Civitai）";
        verifyBtn.style.cssText = `
            padding:8px 16px;background:${COLORS.warning};
            color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
        `;
        
        const verifyStatus = document.createElement("span");
        verifyStatus.textContent = "先上传JSON文件，再点击校验";
        verifyStatus.style.cssText = `
            color:${COLORS.textDim};font-size:12px;
        `;
        
        // 调试按钮：列出本地所有LoRA
        const debugBtn = document.createElement("button");
        debugBtn.textContent = "调试:列出本地LoRA";
        debugBtn.style.cssText = `
            padding:8px 12px;background:${COLORS.inputBg};
            color:${COLORS.textDim};border:1px solid ${COLORS.border};
            border-radius:4px;cursor:pointer;font-size:11px;
        `;
        
        verifyRow.appendChild(verifyBtn);
        verifyRow.appendChild(verifyStatus);
        verifyRow.appendChild(debugBtn);

        // 校验进度条（默认隐藏，运行时显示实时进度）
        const verifyProgressWrap = document.createElement("div");
        verifyProgressWrap.style.cssText = `
            display:none;align-items:center;gap:8px;margin-top:8px;width:100%;
        `;
        const verifyProgressBarBg = document.createElement("div");
        verifyProgressBarBg.style.cssText = `
            flex:1;height:8px;background:${COLORS.inputBg};
            border:1px solid ${COLORS.border};border-radius:4px;overflow:hidden;
        `;
        const verifyProgressBar = document.createElement("div");
        verifyProgressBar.style.cssText = `
            height:100%;width:0%;background:${COLORS.warning};
            transition:width .15s ease;
        `;
        verifyProgressBarBg.appendChild(verifyProgressBar);
        const verifyProgressText = document.createElement("span");
        verifyProgressText.textContent = "0/0";
        verifyProgressText.style.cssText = `
            color:${COLORS.textDim};font-size:12px;min-width:46px;text-align:right;
        `;
        verifyProgressWrap.appendChild(verifyProgressBarBg);
        verifyProgressWrap.appendChild(verifyProgressText);

        function setVerifyProgress(done, total) {
            const t = Math.max(0, total || 0);
            const d = Math.max(0, Math.min(done || 0, t));
            const pct = t > 0 ? Math.round((d / t) * 100) : 0;
            verifyProgressBar.style.width = pct + "%";
            verifyProgressText.textContent = t > 0 ? `${d}/${t}` : "—";
            verifyProgressBar.style.background = pct >= 100 ? COLORS.success : COLORS.warning;
        }

        topSection.appendChild(uploadRow);
        topSection.appendChild(verifyRow);
        topSection.appendChild(verifyProgressWrap);
        
        // 创建内容区域：校验结果
        const contentArea = document.createElement("div");
        contentArea.style.cssText = `
            flex:1;display:flex;flex-direction:column;overflow:hidden;
        `;
        
        const verifyResultsTitle = document.createElement("div");
        verifyResultsTitle.textContent = "校验结果（上传JSON后显示）";
        verifyResultsTitle.style.cssText = `
            padding:8px;background:${COLORS.sidebarBg};
            color:${COLORS.text};font-size:12px;font-weight:500;
            border-bottom:1px solid ${COLORS.border};
        `;
        
        const verifyResultsContent = document.createElement("div");
        verifyResultsContent.style.cssText = `
            flex:1;overflow-y:auto;padding:8px;
        `;
        
        contentArea.appendChild(verifyResultsTitle);
        contentArea.appendChild(verifyResultsContent);
        
        // 底部：本地缺失预览框
        const missingSection = document.createElement("div");
        missingSection.style.cssText = `
            height:200px;border-top:1px solid ${COLORS.border};
            display:flex;flex-direction:column;
        `;
        
        const missingTitle = document.createElement("div");
        missingTitle.textContent = "本地缺失LoRA（文件不存在）";
        missingTitle.style.cssText = `
            padding:8px;background:${COLORS.sidebarBg};
            color:${COLORS.warning};font-size:12px;font-weight:500;
            border-bottom:1px solid ${COLORS.border};
        `;
        
        const missingContent = document.createElement("div");
        missingContent.style.cssText = `
            flex:1;overflow-y:auto;padding:8px;
            font-family:monospace;font-size:11px;
        `;
        
        missingSection.appendChild(missingTitle);
        missingSection.appendChild(missingContent);
        
        checkContainer.appendChild(topSection);
        checkContainer.appendChild(contentArea);
        checkVerifyResultsContent = verifyResultsContent;
        checkMissingContent = missingContent;
        checkMissingSection = missingSection;
        
        mainContent.appendChild(checkContainer);
        mainContent.appendChild(missingSection);
        
        // 绑定上传按钮事件
        uploadBtn.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (file) {
                uploadFileName.textContent = file.name;
                uploadFileName.style.color = COLORS.success;
            }
        });
        
        // 绑定校验按钮事件
        verifyBtn.addEventListener("click", () => startCivitaiVerifyFromUpload(fileInput, verifyStatus, gateBanner, verifyBtn, verifyProgressWrap, setVerifyProgress));
        
        // 绑定调试按钮事件（再次点击可隐藏列表）
        debugBtn.addEventListener("click", async () => {
            // 若当前已显示调试列表，则再次点击隐藏
            const existing = checkVerifyResultsContent.querySelector('[data-debug-list]');
            if (existing) {
                checkVerifyResultsContent.innerHTML = "";
                checkMissingContent.innerHTML = "";
                debugBtn.textContent = "调试:列出本地LoRA";
                return;
            }
            debugBtn.textContent = "加载中...";
            debugBtn.disabled = true;
            try {
                const resp = await fetch('/naiba/lora/list-all');
                const data = await resp.json();
                const loras = data.loras || [];
                const count = data.count || 0;
                
                // 显示结果
                checkVerifyResultsContent.innerHTML = "";
                checkMissingContent.innerHTML = "";
                
                const infoDiv = document.createElement("div");
                infoDiv.dataset.debugList = "1";
                infoDiv.style.cssText = `padding:12px;background:${COLORS.inputBg};border-radius:6px;margin-bottom:8px;`;
                infoDiv.innerHTML = `
                    <div style="color:${COLORS.success};font-size:13px;font-weight:bold;margin-bottom:8px;">
                        本地LoRA文件总数: ${count}
                    </div>
                    <div style="color:${COLORS.textDim};font-size:11px;max-height:300px;overflow-y:auto;word-break:break-all;">
                        ${loras.slice(0, 100).join('<br>')}
                        ${count > 100 ? '<br><em>...仅显示前100个</em>' : ''}
                    </div>
                `;
                checkVerifyResultsContent.appendChild(infoDiv);
                
                debugBtn.textContent = `调试:隐藏列表 (${count})`;
            } catch (e) {
                console.error("[LoraDataPreview] 调试查询失败:", e);
                debugBtn.textContent = "调试:失败";
            }
            debugBtn.disabled = false;
        });
    }
    
    // ========== Civitai校验功能 ==========
    let civitaiVerifyResults = [];
    let civitaiMissingResults = [];
    
    async function startCivitaiVerify() {
        // 获取lora_data
        if (!node) return;
        const loraDataWidget = node.widgets?.find(w => w.name === "lora_data");
        if (!loraDataWidget || !loraDataWidget.value) {
            checkVerifyResultsContent.innerHTML = `
                <div style="color:${COLORS.error};text-align:center;padding:20px;">
                    没有找到lora_data数据
                </div>
            `;
            return;
        }
        
        let loraData;
        try {
            loraData = JSON.parse(loraDataWidget.value);
        } catch (e) {
            checkVerifyResultsContent.innerHTML = `
                <div style="color:${COLORS.error};text-align:center;padding:20px;">
                    lora_data格式错误: ${e.message}
                </div>
            `;
            return;
        }
        
        if (!Array.isArray(loraData) || loraData.length === 0) {
            checkVerifyResultsContent.innerHTML = `
                <div style="color:${COLORS.textDim};text-align:center;padding:20px;">
                    lora_data为空或格式不正确
                </div>
            `;
            return;
        }
        
        // 过滤启用的lora
        const enabledLoras = loraData.filter(item => item.enabled !== false);
        if (enabledLoras.length === 0) {
            checkVerifyResultsContent.innerHTML = `
                <div style="color:${COLORS.textDim};text-align:center;padding:20px;">
                    没有启用的LoRA
                </div>
            `;
            return;
        }
        
        // 开始校验
        civitaiVerifyResults = [];
        civitaiMissingResults = [];
        checkVerifyResultsContent.innerHTML = "";
        checkMissingContent.innerHTML = "";
        
        const statusSpan = document.createElement("div");
        statusSpan.textContent = `开始校验 ${enabledLoras.length} 个LoRA...`;
        statusSpan.style.cssText = `
            color:${COLORS.text};font-size:12px;padding:8px;
            background:${COLORS.inputBg};border-radius:4px;margin-bottom:8px;
        `;
        checkVerifyResultsContent.appendChild(statusSpan);
        
        // 批量校验（每批4个）
        const batchSize = 4;
        for (let i = 0; i < enabledLoras.length; i += batchSize) {
            const batch = enabledLoras.slice(i, i + batchSize);
            statusSpan.textContent = `校验中... (${i + 1}-${Math.min(i + batchSize, enabledLoras.length)}/${enabledLoras.length})`;
            
            const promises = batch.map(lora => verifySingleLora(lora));
            await Promise.all(promises);
        }
        
        statusSpan.textContent = `校验完成！找到: ${civitaiVerifyResults.length}, 缺失: ${civitaiMissingResults.length}`;
        statusSpan.style.background = civitaiMissingResults.length > 0 ? COLORS.warningBg : COLORS.successBg;
    }
    
    // 旧版实现（已被下方四分类版本覆盖，保留以避免影响 lora_data 路径）
    async function startCivitaiVerifyFromUploadLegacy(fileInput, statusSpan) {
        // 1. 读取上传的JSON文件
        const file = fileInput.files[0];
        if (!file) {
            statusSpan.textContent = "请先选择JSON文件！";
            statusSpan.style.color = COLORS.error;
            return;
        }
        
        let fileContent;
        try {
            fileContent = await file.text();
        } catch (e) {
            statusSpan.textContent = `读取文件失败: ${e.message}`;
            statusSpan.style.color = COLORS.error;
            return;
        }
        
        // 2. 解析JSON
        let presetData;
        try {
            presetData = JSON.parse(fileContent);
        } catch (e) {
            statusSpan.textContent = `JSON解析失败: ${e.message}`;
            statusSpan.style.color = COLORS.error;
            return;
        }
        
        // 支持两种格式：直接数组 或 {lora_list: [...]}
        let loraList = [];
        if (Array.isArray(presetData)) {
            loraList = presetData;
        } else if (presetData.lora_list && Array.isArray(presetData.lora_list)) {
            loraList = presetData.lora_list;
        } else if (presetData.loras && Array.isArray(presetData.loras)) {
            loraList = presetData.loras;
        } else {
            statusSpan.textContent = "JSON格式不正确，需要数组或包含lora_list/loras字段";
            statusSpan.style.color = COLORS.error;
            return;
        }
        
        if (loraList.length === 0) {
            statusSpan.textContent = "JSON中没有LoRA数据";
            statusSpan.style.color = COLORS.warning;
            return;
        }
        
        // 3. 过滤启用的LoRA
        const enabledLoras = loraList.filter(item => item.enabled !== false);
        if (enabledLoras.length === 0) {
            statusSpan.textContent = "没有启用的LoRA";
            statusSpan.style.color = COLORS.textDim;
            return;
        }
        
        // 4. 清空结果区域
        civitaiVerifyResults = [];
        civitaiMissingResults = [];
        checkVerifyResultsContent.innerHTML = "";
        checkMissingContent.innerHTML = "";
        
        statusSpan.textContent = `正在检查 ${enabledLoras.length} 个LoRA的本地状态...`;
        statusSpan.style.color = COLORS.text;
        
        // 5. 批量检查本地存在性（基于SHA256匹配）
        let localResults = {};
        try {
            const localResponse = await fetch('/naiba/lora/check-local', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lora_list: enabledLoras })
            });
            const localData = await localResponse.json();
            localResults = localData.results || {};
            console.log("[LoraDataPreview] check-local API响应:", localData);
            console.log("[LoraDataPreview] 发送的enabledLoras:", enabledLoras);
            console.log("[LoraDataPreview] localResults:", localResults);
        } catch (e) {
            console.warn("[LoraDataPreview] 检查本地存在性失败:", e);
        }
        
        // 6. 显示本地存在的LoRA卡片
        let localFoundCount = 0;
        let localMissingCount = 0;
        let noHashCount = 0;
        
        for (const loraItem of enabledLoras) {
            const sha256 = (loraItem.sha256 || "").toLowerCase();
            const localInfo = sha256 ? localResults[sha256] : null;
            
            if (localInfo && localInfo.exists) {
                localFoundCount++;
                addLocalFoundCard(loraItem, localInfo);
            } else if (!sha256 || (localInfo && localInfo.no_hash)) {
                noHashCount++;
                addNoHashResult(loraItem);
            } else {
                localMissingCount++;
                addLocalMissingResult(loraItem);
            }
        }
        
        // 7. 批量查询Civitai（仅对本地存在的LoRA查Civitai）
        const localFoundLoras = enabledLoras.filter(item => {
            const sha256 = (item.sha256 || "").toLowerCase();
            return sha256 && localResults[sha256]?.exists;
        });
        
        statusSpan.textContent = `本地检查完成：存在 ${localFoundCount}，缺失 ${localMissingCount}${noHashCount > 0 ? '，无法匹配 ' + noHashCount : ''}。正在查询Civitai...`;
        
        // 批量查Civitai
        const batchSize = 4;
        for (let i = 0; i < localFoundLoras.length; i += batchSize) {
            const batch = localFoundLoras.slice(i, i + batchSize);
            statusSpan.textContent = `Civitai查询中... (${i + 1}-${Math.min(i + batchSize, localFoundLoras.length)}/${localFoundLoras.length})`;
            
            const promises = batch.map(lora => verifySingleLora(lora));
            await Promise.all(promises);
        }
        
        // 8. 更新状态
        statusSpan.textContent = `校验完成！本地存在: ${localFoundCount}, 本地缺失: ${localMissingCount}, Civitai找到: ${civitaiVerifyResults.length}`;
        statusSpan.style.background = localMissingCount > 0 || civitaiMissingResults.length > 0 ? COLORS.warningBg : COLORS.successBg;
    }
    
    // ========== 重做的上传预设校验（四分类卡片） ==========
    function updateGateBanner(bannerEl, ok, cacheData) {
        if (!bannerEl) return;
        if (ok) {
            const n = cacheData ? cacheData.cached_count : 0;
            bannerEl.textContent = `✓ 已建立 sha256 全局缓存（共 ${n} 个），可以执行校验`;
            bannerEl.style.background = 'rgba(63,185,80,0.15)';
            bannerEl.style.borderColor = COLORS.success;
            bannerEl.style.color = COLORS.success;
        } else {
            const n = cacheData && cacheData.success ? cacheData.cached_count : 0;
            const t = cacheData && cacheData.success ? cacheData.total_loras : 0;
            bannerEl.textContent = `⚠ 请确定所有 LoRA 都已有 sha256 缓存，否则不要执行（请先执行批量同步/离线缓存）` +
                (n > 0 ? `  [当前 ${n}/${t}]` : `  [当前 0]`);
            bannerEl.style.background = 'rgba(210,153,34,0.15)';
            bannerEl.style.borderColor = '#d29922';
            bannerEl.style.color = '#d29922';
        }
    }

    // 读取 SSE 流，逐条回调事件对象；返回未解析的原始文本（用于非 SSE 接口的 JSON 回退）
    async function readSSE(resp, onEvent) {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let idx;
            while ((idx = buffer.indexOf("\n\n")) !== -1) {
                const chunk = buffer.slice(0, idx);
                buffer = buffer.slice(idx + 2);
                const line = chunk.split("\n").find(l => l.startsWith("data: "));
                if (line) {
                    try {
                        onEvent(JSON.parse(line.slice(6)));
                    } catch (e) {
                        // 忽略非 JSON 行
                    }
                }
            }
        }
        return buffer;
    }

    async function startCivitaiVerifyFromUpload(fileInput, statusSpan, gateBanner, verifyBtn, verifyProgressWrap, setVerifyProgress) {
        const file = fileInput.files[0];
        if (!file) {
            statusSpan.textContent = "请先选择JSON文件！";
            statusSpan.style.color = COLORS.error;
            return;
        }

        let fileContent;
        try {
            fileContent = await file.text();
        } catch (e) {
            statusSpan.textContent = `读取文件失败: ${e.message}`;
            statusSpan.style.color = COLORS.error;
            return;
        }

        let presetData;
        try {
            presetData = JSON.parse(fileContent);
        } catch (e) {
            statusSpan.textContent = `JSON解析失败: ${e.message}`;
            statusSpan.style.color = COLORS.error;
            return;
        }

        let loraList = [];
        if (Array.isArray(presetData)) {
            loraList = presetData;
        } else if (presetData.lora_list && Array.isArray(presetData.lora_list)) {
            loraList = presetData.lora_list;
        } else if (presetData.loras && Array.isArray(presetData.loras)) {
            loraList = presetData.loras;
        } else {
            statusSpan.textContent = "JSON格式不正确，需要数组或包含lora_list/loras字段";
            statusSpan.style.color = COLORS.error;
            return;
        }

        if (loraList.length === 0) {
            statusSpan.textContent = "JSON中没有LoRA数据";
            statusSpan.style.color = COLORS.warning;
            return;
        }

        const enabledLoras = loraList.filter(item => item.enabled !== false);
        if (enabledLoras.length === 0) {
            statusSpan.textContent = "没有启用的LoRA";
            statusSpan.style.color = COLORS.textDim;
            return;
        }

        // ========== 执行门禁：检查全局 sha256 缓存 ==========
        let cacheData = null;
        try {
            const resp = await fetch('/naiba/lora/sha256-cache');
            cacheData = await resp.json();
        } catch (e) {
            console.warn("[LoraDataPreview] 读取缓存状态失败:", e);
        }

        if (!cacheData || !cacheData.success || cacheData.cached_count === 0) {
            updateGateBanner(gateBanner, false, cacheData);
            alert("⚠ 尚未建立 sha256 全局缓存！\n\n请先执行「批量同步所有」或「离线缓存SHA256」，\n否则无法准确判断预设中的 LoRA 是否存在于本地。\n\n（同步完成后重新点击校验）");
            statusSpan.textContent = "已阻止：请先建立 sha256 缓存";
            statusSpan.style.color = COLORS.warning;
            return;
        }
        if (!cacheData.all_cached) {
            updateGateBanner(gateBanner, false, cacheData);
            const ok = confirm(
                `当前仅缓存了 ${cacheData.cached_count}/${cacheData.total_loras} 个 LoRA 的 sha256（缺失 ${cacheData.missing_count} 个）。\n` +
                `未缓存的本地 LoRA 将无法被准确匹配，可能导致误判为「本地缺失」。\n\n仍要执行校验吗？（建议先完成同步）`
            );
            if (!ok) {
                statusSpan.textContent = "已取消：未完成全部缓存";
                statusSpan.style.color = COLORS.warning;
                return;
            }
        } else {
            updateGateBanner(gateBanner, true, cacheData);
        }

        // ========== 调用聚合校验接口（SSE 流式，实时进度） ==========
        // 即时按钮反馈：点下即变「校验中...」并置灰，让用户一眼看到按钮已响应
        verifyBtn.textContent = "校验中...";
        verifyBtn.disabled = true;
        statusSpan.textContent = `正在校验 ${enabledLoras.length} 个 LoRA（本地匹配 + Civitai 实时查询）...`;
        statusSpan.style.color = COLORS.text;
        checkVerifyResultsContent.innerHTML = "";
        checkMissingContent.innerHTML = "";
        verifyProgressWrap.style.display = "flex";
        setVerifyProgress(0, 0);

        const resetVerifyBtn = () => {
            verifyBtn.textContent = "开始校验（本地+Civitai）";
            verifyBtn.disabled = false;
            verifyProgressWrap.style.display = "none";
        };

        let finalResult = null;
        let streamError = null;
        try {
            const resp = await fetch('/naiba/lora/verify-preset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lora_list: enabledLoras, api_key: "" })
            });
            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.error || `HTTP ${resp.status}`);
            }
            // 读取流；raw 为未解析的原始响应体（旧 JSON 接口场景下等于整个 JSON）
            const raw = await readSSE(resp, (evt) => {
                if (evt.type === "progress") {
                    setVerifyProgress(evt.done, evt.total);
                    statusSpan.textContent = evt.msg || "校验中...";
                } else if (evt.type === "done") {
                    finalResult = evt;
                } else if (evt.type === "error") {
                    streamError = evt.message || "校验失败";
                }
            });
            if (streamError) {
                throw new Error(streamError);
            }
            // 兼容未重启 ComfyUI 时后端仍为旧 JSON 接口的情况：回退解析 JSON
            if (!finalResult && raw && raw.trim()) {
                try {
                    const j = JSON.parse(raw.trim());
                    if (j && j.success && j.green !== undefined) {
                        finalResult = j;
                    }
                } catch (e) {
                    // 非 JSON，忽略
                }
            }
            if (!finalResult) {
                throw new Error("未收到校验结果");
            }
        } catch (e) {
            statusSpan.textContent = `校验请求失败: ${e.message}`;
            statusSpan.style.color = COLORS.error;
            resetVerifyBtn();
            return;
        }

        resetVerifyBtn();
        renderVerifyPresetResult(finalResult, statusSpan);
    }

    function renderVerifyPresetResult(result, statusSpan) {
        const green = result.green || [];
        const gray = result.gray || [];
        const notFound = result.not_found || [];
        const noSha = result.no_sha256 || [];
        const s = result.summary || {};

        checkVerifyResultsContent.innerHTML = "";
        checkMissingContent.innerHTML = "";

        const header = document.createElement("div");
        header.style.cssText = `
            padding:8px 10px;border-radius:6px;margin-bottom:10px;
            background:${COLORS.inputBg};color:${COLORS.text};font-size:12px;
            display:flex;flex-wrap:wrap;gap:12px;align-items:center;
        `;
        header.innerHTML = `
            <span style="color:${COLORS.success};font-weight:600;">● 绿色(本地+C站) ${green.length}</span>
            <span style="color:${COLORS.textDim};font-weight:600;">● 灰色(需下载) ${gray.length}</span>
            <span style="color:${COLORS.error};font-weight:600;">● 找不到地址 ${notFound.length}</span>
            <span style="color:${COLORS.warning};font-weight:600;">● 预设内无sha256 ${noSha.length}</span>
            <span style="color:${COLORS.textDim};">共 ${s.total || 0} 条</span>
        `;
        checkVerifyResultsContent.appendChild(header);

        if (green.length) {
            checkVerifyResultsContent.appendChild(makeSectionTitle("✓ 本地存在且 C 站上也有（绿色卡片）", COLORS.success));
            green.forEach(item => checkVerifyResultsContent.appendChild(makeCard(item, "green")));
        }
        if (gray.length) {
            checkVerifyResultsContent.appendChild(makeSectionTitle("⬜ 本地不存在但 C 站有（灰色卡片，点击详情下载）", COLORS.textDim));
            gray.forEach(item => checkVerifyResultsContent.appendChild(makeCard(item, "gray")));
        }
        if (notFound.length) {
            checkVerifyResultsContent.appendChild(makeSectionTitle("✗ 本地不存在且 C 站也找不到（找不到地址）", COLORS.error));
            notFound.forEach(item => checkMissingContent.appendChild(makeBottomItem(item, "not_found")));
        }
        if (noSha.length) {
            checkVerifyResultsContent.appendChild(makeSectionTitle("? 预设条目无 sha256（无法匹配，请自行确认）", COLORS.warning));
            noSha.forEach(item => checkMissingContent.appendChild(makeBottomItem(item, "no_sha256")));
        }

        if (!green.length && !gray.length && !notFound.length && !noSha.length) {
            checkVerifyResultsContent.appendChild(makeSectionTitle("无结果", COLORS.textDim));
        }

        statusSpan.textContent = `校验完成！绿 ${green.length}・灰 ${gray.length}・找不到 ${notFound.length}・无sha256 ${noSha.length}`;
        statusSpan.style.color = COLORS.success;
    }

    function makeSectionTitle(text, color) {
        const d = document.createElement("div");
        d.textContent = text;
        d.style.cssText = `margin:10px 0 6px;padding:4px 8px;border-radius:4px;background:${COLORS.sidebarBg};color:${color};font-size:12px;font-weight:600;`;
        return d;
    }

    function makeCard(item, type) {
        const name = item.name || "Unknown";
        const info = item.civitai_info || {};
        const isGreen = type === "green";

        const card = document.createElement("div");
        const barColor = isGreen ? COLORS.success : COLORS.textDim;
        card.style.cssText = `
            display:flex;align-items:center;gap:10px;
            padding:8px;background:${COLORS.listItemBg};border-radius:6px;
            margin-bottom:6px;border-left:4px solid ${barColor};
            opacity:${isGreen ? "1" : "0.72"};
            transition:transform .12s ease, box-shadow .12s ease;
        `;
        card.addEventListener("mouseenter", () => { card.style.transform = "translateY(-1px)"; card.style.boxShadow = "0 2px 10px rgba(0,0,0,.35)"; });
        card.addEventListener("mouseleave", () => { card.style.transform = "none"; card.style.boxShadow = "none"; });

        const previewDiv = document.createElement("div");
        previewDiv.style.cssText = `width:52px;height:52px;border-radius:5px;overflow:hidden;background:${COLORS.inputBg};flex-shrink:0;`;
        const previewUrl = info.preview_url || "";
        if (previewUrl) {
            const img = document.createElement("img");
            img.src = previewUrl;
            img.style.cssText = "width:100%;height:100%;object-fit:cover;";
            img.onerror = () => { img.style.display = "none"; previewDiv.innerHTML = `<div style="color:${COLORS.textDim};font-size:10px;text-align:center;line-height:52px;">无图</div>`; };
            previewDiv.appendChild(img);
        } else if (isGreen && item.local_name) {
            const img = document.createElement("img");
            img.src = `/naiba/lora/preview?name=${encodeURIComponent(item.local_name)}&t=${Date.now()}`;
            img.style.cssText = "width:100%;height:100%;object-fit:cover;";
            img.onerror = () => { img.style.display = "none"; previewDiv.innerHTML = `<div style="color:${COLORS.textDim};font-size:10px;text-align:center;line-height:52px;">无图</div>`; };
            previewDiv.appendChild(img);
        } else {
            previewDiv.innerHTML = `<div style="color:${COLORS.textDim};font-size:10px;text-align:center;line-height:52px;">无图</div>`;
        }

        const infoDiv = document.createElement("div");
        infoDiv.style.cssText = "flex:1;min-width:0;";
        const modelName = info.model_name || name;
        const versionName = info.version_name || "";
        const nameDiv = document.createElement("div");
        nameDiv.textContent = modelName;
        nameDiv.style.cssText = `color:${COLORS.text};font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;`;
        const subDiv = document.createElement("div");
        subDiv.textContent = versionName || name;
        subDiv.style.cssText = `color:${COLORS.textDim};font-size:10px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;`;
        const strengthDiv = document.createElement("div");
        strengthDiv.textContent = `模型 ${item.strength_model ?? 1.0} | CLIP ${item.strength_clip ?? 1.0}`;
        strengthDiv.style.cssText = `color:${COLORS.textDim};font-size:10px;margin-top:2px;`;
        infoDiv.appendChild(nameDiv);
        infoDiv.appendChild(subDiv);
        infoDiv.appendChild(strengthDiv);

        const rightDiv = document.createElement("div");
        rightDiv.style.cssText = "display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;";
        if (!isGreen) {
            const tag = document.createElement("div");
            tag.textContent = "需下载";
            tag.style.cssText = `font-size:10px;padding:1px 6px;border-radius:3px;background:rgba(110,118,129,.3);color:${COLORS.textDim};`;
            rightDiv.appendChild(tag);
        }
        const url = info.model_page_url || info.download_url || "";
        if (url) {
            const btn = document.createElement("button");
            btn.textContent = isGreen ? "详情" : "详情/下载";
            btn.style.cssText = `padding:4px 10px;background:${isGreen ? COLORS.accent : COLORS.warning};color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;`;
            btn.addEventListener("click", () => window.open(url, "_blank"));
            rightDiv.appendChild(btn);
        }

        card.appendChild(previewDiv);
        card.appendChild(infoDiv);
        card.appendChild(rightDiv);
        return card;
    }

    function makeBottomItem(item, type) {
        const name = item.name || "Unknown";
        const sha = item.sha256 || "";
        const d = document.createElement("div");
        d.style.cssText = `padding:6px 8px;background:${COLORS.inputBg};border-radius:4px;margin-bottom:4px;border-left:3px solid ${type === "not_found" ? COLORS.error : COLORS.warning};`;
        d.innerHTML = `
            <div style="color:${COLORS.text};font-size:11px;word-break:break-all;">
                <strong>${type === "not_found" ? "✗ 找不到地址:" : "? 预设内无sha256:"}</strong> ${name}
            </div>
            ${sha ? `<div style="color:${COLORS.textDim};font-size:10px;margin-top:2px;word-break:break-all;">sha256: ${sha}</div>` : ""}
            <div style="color:${COLORS.textDim};font-size:10px;margin-top:2px;">强度: ${item.strength_model ?? 1.0} / ${item.strength_clip ?? 1.0}</div>
        `;
        return d;
    }

    function addLocalFoundCard(loraItem, localInfo) {
        const loraName = loraItem.name || "Unknown";
        const strengthModel = loraItem.strength_model ?? 1.0;
        const strengthClip = loraItem.strength_clip ?? 1.0;
        
        const card = document.createElement("div");
        card.style.cssText = `
            display:flex;align-items:center;gap:8px;
            padding:8px;background:${COLORS.listItemBg};border-radius:4px;
            margin-bottom:4px;border-left:3px solid ${COLORS.success};
        `;
        
        // 本地存在指示器
        const statusDot = document.createElement("div");
        statusDot.style.cssText = `
            width:8px;height:8px;border-radius:50%;
            background:${COLORS.success};
        `;
        
        // 预览图 - 使用本地实际文件名
        const localFileName = localInfo.local_name || loraName;
        const previewDiv = document.createElement("div");
        previewDiv.style.cssText = `
            width:48px;height:48px;border-radius:4px;overflow:hidden;
            background:${COLORS.inputBg};flex-shrink:0;
        `;
        
        if (localInfo.has_preview) {
            const previewImg = document.createElement("img");
            previewImg.src = `/naiba/lora/preview?name=${encodeURIComponent(localFileName)}&t=${Date.now()}`;
            previewImg.style.cssText = `width:100%;height:100%;object-fit:cover;`;
            previewImg.onerror = () => {
                previewImg.style.display = "none";
                previewDiv.innerHTML = `<div style="color:${COLORS.textDim};font-size:10px;text-align:center;line-height:48px;">无图</div>`;
            };
            previewDiv.appendChild(previewImg);
        } else {
            previewDiv.innerHTML = `<div style="color:${COLORS.textDim};font-size:10px;text-align:center;line-height:48px;">无图</div>`;
        }
        
        // LoRA信息
        const loraInfo = document.createElement("div");
        loraInfo.style.cssText = `flex:1;min-width:0;`;
        
        const nameDiv = document.createElement("div");
        nameDiv.textContent = loraName;
        nameDiv.style.cssText = `
            color:${COLORS.text};font-size:12px;font-weight:500;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
        `;
        
        const strengthDiv = document.createElement("div");
        strengthDiv.textContent = `模型强度: ${strengthModel} | CLIP强度: ${strengthClip}`;
        strengthDiv.style.cssText = `
            color:${COLORS.textDim};font-size:10px;margin-top:2px;
        `;
        
        const localStatus = document.createElement("div");
        localStatus.textContent = "✓ 本地存在";
        localStatus.style.cssText = `
            color:${COLORS.success};font-size:10px;margin-top:2px;
        `;
        
        loraInfo.appendChild(nameDiv);
        loraInfo.appendChild(strengthDiv);
        loraInfo.appendChild(localStatus);
        
        card.appendChild(statusDot);
        card.appendChild(previewDiv);
        card.appendChild(loraInfo);
        
        checkVerifyResultsContent.appendChild(card);
    }
    
    function addLocalMissingResult(loraItem) {
        const loraName = loraItem.name || "Unknown";
        
        const missingItem = document.createElement("div");
        missingItem.style.cssText = `
            padding:6px;background:${COLORS.inputBg};border-radius:3px;
            margin-bottom:4px;border-left:3px solid ${COLORS.error};
        `;
        
        missingItem.innerHTML = `
            <div style="color:${COLORS.error};font-size:11px;">
                <strong>✗ 缺失:</strong> ${loraName}
            </div>
            <div style="color:${COLORS.textDim};font-size:10px;margin-top:2px;">
                强度: ${loraItem.strength_model ?? 1.0} / ${loraItem.strength_clip ?? 1.0}
            </div>
        `;
        
        checkMissingContent.appendChild(missingItem);
    }
    
    function addNoHashResult(loraItem) {
        const loraName = loraItem.name || "Unknown";
        
        const noHashItem = document.createElement("div");
        noHashItem.style.cssText = `
            padding:6px;background:${COLORS.inputBg};border-radius:3px;
            margin-bottom:4px;border-left:3px solid ${COLORS.textDim};
        `;
        
        noHashItem.innerHTML = `
            <div style="color:${COLORS.textDim};font-size:11px;">
                <strong>? 无法匹配:</strong> ${loraName}
            </div>
            <div style="color:${COLORS.textDim};font-size:10px;margin-top:2px;">
                该预设没有sha256字段，请自行确认文件是否存在
            </div>
            <div style="color:${COLORS.textDim};font-size:10px;margin-top:2px;">
                强度: ${loraItem.strength_model ?? 1.0} / ${loraItem.strength_clip ?? 1.0}
            </div>
        `;
        
        checkMissingContent.appendChild(noHashItem);
    }
    
    async function verifySingleLora(loraItem) {
        const loraName = loraItem.name || "";
        let sha256 = loraItem.sha256;
        
        // sha256自动回退
        if (!sha256) {
            try {
                const response = await fetch(`/naiba/lora/resolve-sha256?name=${encodeURIComponent(loraName)}`);
                const result = await response.json();
                if (result.sha256) {
                    sha256 = result.sha256;
                }
            } catch (e) {
                console.warn(`[LoraDataPreview] 获取sha256失败: ${loraName}`, e);
            }
        }
        
        // 如果还是没有sha256，标记为无法校验
        if (!sha256) {
            addVerifyResult(loraItem, null, "无法校验（无sha256）", "unknown");
            return;
        }
        
        // 查询Civitai
        try {
            const response = await fetch(`/naiba/lora/civitai-by-hash?hash=${sha256}`);
            const result = await response.json();
            
            if (result.found) {
                addVerifyResult(loraItem, result.info, "已找到", "found");
            } else {
                addVerifyResult(loraItem, null, "未找到", "missing");
                addMissingResult(loraItem, sha256);
            }
        } catch (e) {
            console.warn(`[LoraDataPreview] Civitai查询失败: ${loraName}`, e);
            addVerifyResult(loraItem, null, `查询失败: ${e.message}`, "error");
        }
    }
    
    function addVerifyResult(loraItem, info, status, statusType) {
        civitaiVerifyResults.push({ loraItem, info, status, statusType });
        
        const resultCard = document.createElement("div");
        resultCard.style.cssText = `
            display:flex;align-items:center;gap:8px;
            padding:8px;background:${COLORS.listItemBg};border-radius:4px;
            margin-bottom:4px;opacity:${statusType === "found" ? "1" : "0.7"};
        `;
        
        // 状态指示器
        const statusDot = document.createElement("div");
        statusDot.style.cssText = `
            width:8px;height:8px;border-radius:50%;
            background:${statusType === "found" ? COLORS.success : 
                        statusType === "missing" ? COLORS.error : 
                        statusType === "unknown" ? COLORS.textDim : COLORS.warning};
        `;
        
        // LoRA信息
        const loraInfo = document.createElement("div");
        loraInfo.style.cssText = `flex:1;`;
        
        const loraName = document.createElement("div");
        loraName.textContent = loraItem.name || "Unknown";
        loraName.style.cssText = `
            color:${statusType === "found" ? COLORS.text : COLORS.textDim};
            font-size:12px;font-weight:500;
        `;
        
        const loraStatus = document.createElement("div");
        loraStatus.textContent = status;
        loraStatus.style.cssText = `
            color:${statusType === "found" ? COLORS.success : 
                   statusType === "missing" ? COLORS.error : COLORS.textDim};
            font-size:10px;margin-top:2px;
        `;
        
        loraInfo.appendChild(loraName);
        loraInfo.appendChild(loraStatus);
        
        // 操作按钮
        const actions = document.createElement("div");
        actions.style.cssText = `display:flex;gap:4px;`;
        
        if (statusType === "found" && info) {
            const detailBtn = document.createElement("button");
            detailBtn.textContent = "详情";
            detailBtn.style.cssText = `
                padding:4px 8px;background:${COLORS.accent};
                color:white;border:none;border-radius:3px;cursor:pointer;font-size:10px;
            `;
            detailBtn.addEventListener("click", () => {
                showCivitaiDetail(info);
            });
            actions.appendChild(detailBtn);
        }
        
        resultCard.appendChild(statusDot);
        resultCard.appendChild(loraInfo);
        resultCard.appendChild(actions);
        
        checkVerifyResultsContent.appendChild(resultCard);
    }
    
    function addMissingResult(loraItem, sha256) {
        civitaiMissingResults.push({ loraItem, sha256 });
        
        const missingItem = document.createElement("div");
        missingItem.style.cssText = `
            padding:6px;background:${COLORS.inputBg};border-radius:3px;
            margin-bottom:4px;border-left:3px solid ${COLORS.warning};
        `;
        
        missingItem.innerHTML = `
            <div style="color:${COLORS.text};font-size:11px;">
                <strong>文件名:</strong> ${loraItem.name || "Unknown"}
            </div>
            <div style="color:${COLORS.textDim};font-size:10px;margin-top:2px;">
                <strong>SHA256:</strong> 
                <span style="user-select:all;font-family:monospace;">${sha256}</span>
            </div>
        `;
        
        checkMissingContent.appendChild(missingItem);
    }
    
    function showCivitaiDetail(info) {
        const detailHtml = `
            <div style="background:${COLORS.inputBg};padding:12px;border-radius:6px;margin-top:8px;">
                <div style="display:flex;gap:8px;margin-bottom:8px;">
                    ${info.preview_url ? `
                        <img src="${info.preview_url}" style="width:80px;height:80px;object-fit:cover;border-radius:4px;" />
                    ` : ""}
                    <div>
                        <div style="color:${COLORS.text};font-size:13px;font-weight:500;">
                            ${info.model_name || "Unknown"}
                        </div>
                        <div style="color:${COLORS.textDim};font-size:11px;margin-top:2px;">
                            ${info.version_name || ""}
                        </div>
                        <div style="color:${COLORS.accent};font-size:10px;margin-top:4px;">
                            ${info.base_model || ""}
                        </div>
                    </div>
                </div>
                
                <div style="color:${COLORS.textDim};font-size:11px;margin-bottom:4px;">
                    <strong>下载地址:</strong>
                </div>
                <div style="color:${COLORS.accent};font-size:10px;word-break:break-all;
                    background:${COLORS.sidebarBg};padding:6px;border-radius:3px;
                    margin-bottom:8px;user-select:all;">
                    ${info.download_url || "无"}
                </div>
                
                <div style="color:${COLORS.textDim};font-size:11px;margin-bottom:4px;">
                    <strong>模型页面:</strong>
                </div>
                <div style="color:${COLORS.accent};font-size:10px;word-break:break-all;
                    background:${COLORS.sidebarBg};padding:6px;border-radius:3px;
                    margin-bottom:8px;">
                    <a href="${info.model_page_url || "#"}" target="_blank" 
                       style="color:${COLORS.accent};text-decoration:none;">
                        ${info.model_page_url || "无"}
                    </a>
                </div>
                
                ${info.trigger_words && info.trigger_words.length > 0 ? `
                    <div style="color:${COLORS.textDim};font-size:11px;margin-bottom:4px;">
                        <strong>触发词:</strong>
                    </div>
                    <div style="color:${COLORS.accent};font-size:10px;
                        background:${COLORS.sidebarBg};padding:6px;border-radius:3px;">
                        ${info.trigger_words.join(", ")}
                    </div>
                ` : ""}
                
                <div style="color:${COLORS.textDim};font-size:10px;margin-top:8px;">
                    下载次数: ${info.download_count || 0} | 评分: ${info.rating || 0} (${info.rating_count || 0}人)
                </div>
            </div>
        `;
        
        checkVerifyResultsContent.insertAdjacentHTML('afterbegin', detailHtml);
    }

    // ========== 同步单个LoRA ==========
    async function syncSingleLora(loraName, button) {
        button.disabled = true;
        button.textContent = "同步中...";
        button.style.background = COLORS.textDim;
        button.style.cursor = "wait";
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000);
            const response = await fetch(`/naiba/lora/civitai-sync?name=${encodeURIComponent(loraName)}`, { signal: controller.signal });
            clearTimeout(timeoutId);
            const result = await response.json();
            
            if (result.success) {
                // 成功：显示"已同步"绿色状态，保持3秒
                button.textContent = "✓ 已同步";
                button.style.background = COLORS.success;
                button.style.cursor = "default";
                
                // 刷新预览图 - 找到最近的卡片元素
                const card = button.closest("div[style*='background']");
                if (card) {
                    const previewImg = card.querySelector("img");
                    if (previewImg) {
                        // 添加时间戳强制刷新
                        previewImg.src = `/naiba/lora/preview?name=${encodeURIComponent(loraName)}&t=${Date.now()}`;
                    }
                    
                    // 给卡片加上同步成功的边框效果
                    card.style.borderColor = COLORS.success;
                    card.style.boxShadow = `0 0 0 1px ${COLORS.success}40`;
                }
                
                // 更新节点预览图
                if (node._updateLoraDataPreview) {
                    node._updateLoraDataPreview();
                }
                
                syncStatus.textContent = `同步成功: ${loraName}`;
                syncStatus.style.color = COLORS.success;
                
                // 3秒后恢复按钮和状态栏
                setTimeout(() => {
                    button.textContent = "同步";
                    button.style.background = COLORS.accent;
                    button.style.cursor = "pointer";
                    button.disabled = false;
                    syncStatus.style.color = COLORS.textDim;
                    syncStatus.textContent = "就绪";
                }, 3000);
                return; // 提前返回，不执行最后的 disabled=false
            } else {
                button.textContent = "失败";
                button.style.background = COLORS.danger;
                button.style.cursor = "pointer";
                syncStatus.textContent = `同步失败: ${result.error || "未知错误"}`;
                syncStatus.style.color = COLORS.danger;
                
                // 2秒后恢复
                setTimeout(() => {
                    button.textContent = "同步";
                    button.style.background = COLORS.accent;
                    syncStatus.style.color = COLORS.textDim;
                    syncStatus.textContent = "就绪";
                }, 2000);
            }
        } catch (error) {
            const isTimeout = error.name === 'AbortError';
            console.error("[LoraDataPreview] 同步失败:", error);
            button.textContent = isTimeout ? "超时" : "错误";
            button.style.background = COLORS.danger;
            button.style.cursor = "pointer";
            syncStatus.textContent = isTimeout ? "同步超时，请检查网络" : `同步错误: ${error.message}`;
            syncStatus.style.color = COLORS.danger;
            
            // 2秒后恢复
            setTimeout(() => {
                button.textContent = "同步";
                button.style.background = COLORS.accent;
                syncStatus.style.color = COLORS.textDim;
                syncStatus.textContent = "就绪";
            }, 2000);
        }
        
        button.disabled = false;
    }

    // ========== 批量同步（SSE 实时进度） ==========
    async function startBatchSync() {
        if (isSyncing) {
            alert("正在同步中，请稍候...");
            return;
        }

        // 检查收藏的LoRA数量
        // 选择同步模式
        const modeOptions = [
            { label: "同步未同步的", value: "sync_unsynced", desc: "跳过已有缓存的LoRA，只同步新的" },
            { label: "同步全部（强制更新）", value: "sync_all", desc: "重新同步所有LoRA，包括已同步的" }
        ];
        
        let modePrompt = "选择同步模式：\n\n" +
            "1 - 同步未同步的（跳过已有缓存，只同步新的）\n" +
            "2 - 同步全部（强制更新所有LoRA）\n\n" +
            "请输入 1 或 2:";
        
        const modeChoice = prompt(modePrompt, "1");
        
        if (modeChoice === null) return; // 用户取消
        
        const mode = modeChoice === "2" ? "sync_all" : "sync_unsynced";
        const modeName = mode === "sync_all" ? "全部（强制更新）" : "未同步的";
        
        let confirmMsg = `确定要${modeName}批量同步吗？\n这可能需要一些时间。`;
        
        if (!confirm(confirmMsg)) {
            return;
        }

        isSyncing = true;
        batchSyncBtn.disabled = true;
        batchSyncBtn.textContent = "同步中...";
        batchSyncBtn.style.background = COLORS.textDim;

        // 显示进度条
        progressBarContainer.style.display = "block";
        progressBarTitle.textContent = "批量同步进度";
        progressBarInner.style.width = "0%";
        progressBarStatus.textContent = "准备开始...";

        try {
            const response = await fetch('/naiba/lora/batch-sync', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    api_key: '',
                    nsfw_level: 'R',
                    mode: mode,
                    folder: ''
                })
            });
            
            // 检查响应状态
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            // 使用流式读取 SSE
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let finalResults = null;
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                
                // 解析 SSE 事件
                const lines = buffer.split('\n');
                buffer = lines.pop(); // 保留未完成的行
                
                let eventType = '';
                let eventData = '';
                
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.substring(7).trim();
                    } else if (line.startsWith('data: ')) {
                        eventData = line.substring(6).trim();
                    } else if (line === '' && eventType && eventData) {
                        // 处理完整的事件
                        try {
                            const data = JSON.parse(eventData);
                            
                            switch (eventType) {
                                case 'start':
                                    let startTitle = `批量同步进度 (共 ${data.to_sync} 个`;
                                    if (data.already_synced > 0) {
                                        startTitle += `，跳过 ${data.already_synced} 个`;
                                    }
                                    startTitle += ')';
                                    progressBarTitle.textContent = startTitle;
                                    progressBarStatus.textContent = `开始同步 ${data.to_sync} 个 LoRA...`;
                                    break;
                                    
                                case 'progress':
                                    // 正在同步某个 LoRA
                                    const percent = Math.round((data.current / data.total) * 100);
                                    progressBarInner.style.width = `${percent}%`;
                                    progressBarStatus.textContent = `[${data.current}/${data.total}] 正在同步: ${data.name.split('/').pop().split('\\').pop()}`;
                                    break;
                                    
                                case 'item_done':
                                    // 某个 LoRA 同步完成
                                    const donePercent = Math.round((data.current / data.total) * 100);
                                    progressBarInner.style.width = `${donePercent}%`;
                                    
                                    if (data.status === 'success') {
                                        progressBarStatus.textContent = `[${data.current}/${data.total}] ✓ ${data.name.split('/').pop().split('\\').pop()}`;
                                        progressBarStatus.style.color = COLORS.success;
                                    } else {
                                        progressBarStatus.textContent = `[${data.current}/${data.total}] ✗ ${data.name.split('/').pop().split('\\').pop()} - ${data.error || '失败'}`;
                                        progressBarStatus.style.color = COLORS.danger;
                                    }
                                    
                                    // 500ms 后恢复颜色
                                    setTimeout(() => {
                                        progressBarStatus.style.color = COLORS.textDim;
                                    }, 500);
                                    break;
                                    
                                case 'complete':
                                    finalResults = data.results;
                                    break;
                                    
                                case 'error':
                                    throw new Error(data.error || "同步过程中出错");
                            }
                        } catch (parseError) {
                            console.warn("[LoraDataPreview] SSE parse error:", parseError);
                        }
                        
                        eventType = '';
                        eventData = '';
                    }
                }
            }
            
            // 同步完成
            if (finalResults) {
                progressBarInner.style.width = "100%";
                progressBarStatus.style.color = COLORS.success;
                progressBarStatus.textContent = `完成: ${finalResults.success} 成功, ${finalResults.failed} 失败`;
                
                syncStatus.textContent = `批量同步完成: ${finalResults.success} 成功, ${finalResults.failed} 失败`;
                syncStatus.style.color = COLORS.success;

                // 刷新 sha256 全局缓存提示
                refreshSha256CacheHint();
                
                // 刷新列表
                renderLoraList();
                
                // 显示结果摘要
                let summaryMsg = `批量同步完成！\n\n总计: ${finalResults.total} 个LoRA\n`;
                summaryMsg += `本次同步: ${finalResults.to_sync} 个\n`;
                summaryMsg += `成功: ${finalResults.success}\n失败: ${finalResults.failed}`;
                if (finalResults.already_synced > 0) {
                    summaryMsg += `\n已有缓存跳过: ${finalResults.already_synced}`;
                }
                alert(summaryMsg);
            }
        } catch (error) {
            console.error("[LoraDataPreview] 批量同步失败:", error);
            progressBarStatus.style.color = COLORS.danger;
            progressBarStatus.textContent = `同步错误: ${error.message}`;
            syncStatus.textContent = "批量同步错误";
            syncStatus.style.color = COLORS.danger;
            alert(`批量同步错误: ${error.message}\n\n请检查浏览器控制台(F12)获取详细错误信息。`);
        }

        isSyncing = false;
        batchSyncBtn.disabled = false;
        batchSyncBtn.textContent = "批量同步所有";
        batchSyncBtn.style.background = COLORS.accent;
        
        // 5秒后恢复状态栏默认颜色
        setTimeout(() => {
            syncStatus.style.color = COLORS.textDim;
            syncStatus.textContent = "就绪";
            progressBarStatus.style.color = COLORS.textDim;
        }, 5000);
    }

    // ========== 离线仅计算 SHA256 缓存 ==========
    async function startCacheSha256Only() {
        if (isSyncing) return;

        if (!confirm("确定要离线扫描所有本地 LoRA 并计算 sha256 写入全局缓存吗？\n此操作完全不查询 Civitai，仅本地计算。")) {
            return;
        }

        isSyncing = true;
        cacheSha256Btn.disabled = true;
        cacheSha256Btn.textContent = "缓存中...";
        cacheSha256Btn.style.background = COLORS.textDim;
        cacheSha256Badge.textContent = "缓存中...";
        cacheSha256Badge.style.background = "transparent";
        cacheSha256Badge.style.color = COLORS.textDim;

        progressBarContainer.style.display = "block";
        progressBarTitle.textContent = "离线 SHA256 缓存进度";
        progressBarInner.style.width = "0%";
        progressBarStatus.textContent = "准备开始...";

        try {
            const response = await fetch('/naiba/lora/cache-sha256-only', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder: '' })
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let finalData = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                let eventType = '', eventData = '';
                for (const line of lines) {
                    if (line.startsWith('event: ')) eventType = line.substring(7).trim();
                    else if (line.startsWith('data: ')) eventData = line.substring(6).trim();
                    else if (line === '' && eventType && eventData) {
                        try {
                            const data = JSON.parse(eventData);
                            switch (eventType) {
                                case 'start':
                                    progressBarStatus.textContent = `开始计算 ${data.total} 个 LoRA 的 sha256...`;
                                    break;
                                case 'progress':
                                    const pct = Math.round((data.current / data.total) * 100);
                                    progressBarInner.style.width = `${pct}%`;
                                    progressBarStatus.textContent = `[${data.current}/${data.total}] 正在计算: ${data.name.split('/').pop().split('\\').pop()}`;
                                    break;
                                case 'item_done':
                                    const dp = Math.round((data.current / data.total) * 100);
                                    progressBarInner.style.width = `${dp}%`;
                                    const label = data.status === 'cached' ? '✓' : (data.status === 'skipped' ? '跳过' : '✗');
                                    progressBarStatus.textContent = `[${data.current}/${data.total}] ${label} ${data.name.split('/').pop().split('\\').pop()}`;
                                    progressBarStatus.style.color = data.status === 'failed' ? COLORS.danger : COLORS.textDim;
                                    break;
                                case 'complete':
                                    finalData = data;
                                    break;
                                case 'error':
                                    throw new Error(data.error || "缓存过程中出错");
                            }
                        } catch (parseError) {
                            console.warn("[LoraDataPreview] SHA256 cache SSE parse error:", parseError);
                        }
                        eventType = ''; eventData = '';
                    }
                }
            }

            if (finalData) {
                progressBarInner.style.width = "100%";
                progressBarStatus.style.color = COLORS.success;
                progressBarStatus.textContent = finalData.message || "SHA256 缓存完成";
                syncStatus.textContent = finalData.message || "SHA256 缓存完成";
                syncStatus.style.color = COLORS.success;
                refreshSha256CacheHint();
                alert(finalData.message || "SHA256 缓存完成");
            }
        } catch (error) {
            console.error("[LoraDataPreview] 离线缓存失败:", error);
            progressBarStatus.style.color = COLORS.danger;
            progressBarStatus.textContent = `缓存错误: ${error.message}`;
            syncStatus.textContent = "离线缓存错误";
            syncStatus.style.color = COLORS.danger;
            alert(`离线缓存错误: ${error.message}`);
        }

        isSyncing = false;
        cacheSha256Btn.disabled = false;
        cacheSha256Btn.textContent = "离线缓存SHA256";
        cacheSha256Btn.style.background = COLORS.accent2 || COLORS.accent;
        // 无论成功/失败，结束都重新拉取最新缓存状态刷新徽章
        refreshSha256CacheHint();

        setTimeout(() => {
            syncStatus.style.color = COLORS.textDim;
            syncStatus.textContent = "就绪";
            progressBarStatus.style.color = COLORS.textDim;
        }, 5000);
    }

    // ========== 显示收藏编辑面板 ==========
    async function showEditPanel(loraName) {
        // 加载自定义数据与 Civitai 元数据
        let customData = {};
        let hasMetadataPreview = false;
        let metadata = null;
        try {
            const detailController = new AbortController();
            const detailTimeoutId = setTimeout(() => detailController.abort(), 10000);
            const response = await fetch(`/naiba/lora/detail?name=${encodeURIComponent(loraName)}`, { signal: detailController.signal });
            clearTimeout(detailTimeoutId);
            const result = await response.json();
            if (result.success && result.custom_data) {
                customData = result.custom_data;
            }
            if (result.success && result.has_metadata_preview) {
                hasMetadataPreview = true;
            }
            if (result.success && result.metadata) {
                metadata = result.metadata;
            }
        } catch (e) {
            console.warn("[LoraDataPreview] 加载自定义数据失败:", e);
        }

        // 创建编辑面板
        const editOverlay = document.createElement("div");
        editOverlay.style.cssText = `
            position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.9);z-index:10001;
            display:flex;align-items:center;justify-content:center;
        `;

        const editModal = document.createElement("div");
        editModal.style.cssText = `
            width:500px;max-width:90vw;max-height:90vh;
            display:flex;flex-direction:column;
            background:${COLORS.modalBg};
            border-radius:8px;border:1px solid ${COLORS.border};
            overflow:hidden;
            box-shadow:0 10px 40px rgba(0,0,0,0.5);
        `;

        // 编辑面板标题栏
        const editHeader = document.createElement("div");
        editHeader.style.cssText = `
            display:flex;align-items:center;justify-content:space-between;
            padding:12px 16px;background:${COLORS.headerBg};
            border-bottom:1px solid ${COLORS.border};
            flex-shrink:0;
        `;

        const editTitle = document.createElement("div");
        editTitle.textContent = `编辑自定义数据: ${loraName.split('/').pop().split('\\').pop()}`;
        editTitle.style.cssText = `color:${COLORS.text};font-size:14px;font-weight:600;`;

        const editCloseBtn = document.createElement("div");
        editCloseBtn.textContent = "\u2715";
        editCloseBtn.style.cssText = `
            color:${COLORS.textDim};cursor:pointer;font-size:16px;
            padding:4px 8px;border-radius:4px;transition:all 0.15s;
        `;
        editCloseBtn.addEventListener("click", () => {
            document.body.removeChild(editOverlay);
        });

        editHeader.appendChild(editTitle);
        editHeader.appendChild(editCloseBtn);
        editModal.appendChild(editHeader);

        // 编辑面板内容
        const editContent = document.createElement("div");
        editContent.style.cssText = `
            padding:16px;
            background:${COLORS.contentBg};
            flex:1;overflow-y:auto;min-height:0;
        `;

        // 自定义提示词输入
        const promptLabel = document.createElement("div");
        promptLabel.textContent = "自定义提示词";
        promptLabel.style.cssText = `color:${COLORS.text};font-size:12px;margin-bottom:6px;`;

        const promptInput = document.createElement("textarea");
        promptInput.value = customData.custom_prompt || "";
        promptInput.placeholder = "输入自定义提示词，用于在使用此LoRA时自动添加...";
        promptInput.style.cssText = `
            width:100%;height:80px;padding:8px;
            background:${COLORS.inputBg};border:1px solid ${COLORS.border};
            border-radius:4px;color:${COLORS.text};font-size:12px;
            resize:vertical;outline:none;box-sizing:border-box;
        `;

        // 自定义图片上传区域
        const imageLabel = document.createElement("div");
        imageLabel.textContent = "自定义预览图片";
        imageLabel.style.cssText = `color:${COLORS.text};font-size:12px;margin:12px 0 6px;`;

        const imageUploadArea = document.createElement("div");
        imageUploadArea.style.cssText = `
            width:100%;height:120px;border:2px dashed ${COLORS.border};
            border-radius:4px;display:flex;align-items:center;justify-content:center;
            cursor:pointer;transition:all 0.2s;position:relative;
            overflow:hidden;
        `;

        // 显示当前自定义图片或上传提示
        let currentCustomImage = customData.custom_preview_image_path || "";
        const imagePreview = document.createElement("img");
        imagePreview.style.cssText = `width:100%;height:100%;object-fit:cover;display:none;`;

        const imagePlaceholder = document.createElement("div");
        imagePlaceholder.style.cssText = `color:${COLORS.textDim};font-size:12px;text-align:center;`;
        imagePlaceholder.innerHTML = "点击或拖拽上传图片<br><span style='font-size:10px;'>支持 JPG, PNG, WebP</span>";

        if (currentCustomImage) {
            imagePreview.src = `/naiba/lora/custom-data/image?name=${encodeURIComponent(loraName)}&t=${Date.now()}`;
            imagePreview.style.display = 'block';
            imagePlaceholder.style.display = 'none';
        }

        imageUploadArea.appendChild(imagePreview);
        imageUploadArea.appendChild(imagePlaceholder);

        // 删除图片按钮
        const removeImageBtn = document.createElement("div");
        removeImageBtn.textContent = "\u2715";
        removeImageBtn.style.cssText = `
            position:absolute;top:4px;right:4px;
            width:20px;height:20px;border-radius:50%;
            background:rgba(0,0,0,0.7);color:white;
            display:${currentCustomImage ? 'flex' : 'none'};
            align-items:center;justify-content:center;
            cursor:pointer;font-size:12px;
        `;
        removeImageBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            currentCustomImage = "";
            imagePreview.style.display = 'none';
            imagePlaceholder.style.display = 'block';
            removeImageBtn.style.display = 'none';
        });
        imageUploadArea.appendChild(removeImageBtn);

        // 文件上传处理
        const fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.accept = "image/*";
        fileInput.style.cssText = "display:none;";
        fileInput.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (file) {
                const uploadedPath = await uploadCustomImage(loraName, file, imagePreview, imagePlaceholder, removeImageBtn);
                if (uploadedPath) {
                    currentCustomImage = uploadedPath;
                }
            }
        });

        imageUploadArea.addEventListener("click", () => {
            fileInput.click();
        });

        // 拖拽上传
        imageUploadArea.addEventListener("dragover", (e) => {
            e.preventDefault();
            imageUploadArea.style.borderColor = COLORS.accent;
        });
        imageUploadArea.addEventListener("dragleave", () => {
            imageUploadArea.style.borderColor = COLORS.border;
        });
        imageUploadArea.addEventListener("drop", async (e) => {
            e.preventDefault();
            imageUploadArea.style.borderColor = COLORS.border;
            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                const uploadedPath = await uploadCustomImage(loraName, file, imagePreview, imagePlaceholder, removeImageBtn);
                if (uploadedPath) {
                    currentCustomImage = uploadedPath;
                }
            }
        });

        // ===== 元数据只读区（顶部） =====
        const metaReadOnly = document.createElement("div");
        metaReadOnly.style.cssText = `
            margin-bottom:12px;padding:12px;
            background:${COLORS.inputBg};border:1px solid ${COLORS.border};
            border-radius:6px;
        `;
        let metaHtml = `<div style="color:${COLORS.textDim};font-size:12px;margin-bottom:8px;">Civitai 元数据（只读）</div>`;
        if (metadata) {
            if (metadata.model_name) {
                metaHtml += `<div style="color:${COLORS.text};font-size:14px;font-weight:600;margin-bottom:4px;">${metadata.model_name}</div>`;
            }
            if (metadata.version_name) {
                metaHtml += `<div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">版本: ${metadata.version_name}</div>`;
            }
            if (metadata.base_model) {
                metaHtml += `<div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">基础模型: ${metadata.base_model}</div>`;
            }
            const tw = metadata.trigger_words || metadata.trained_words || [];
            if (tw.length > 0) {
                metaHtml += `<div style="color:${COLORS.accent};font-size:12px;margin-bottom:4px;">触发词: ${tw.join(', ')}</div>`;
            }
            if (metadata.description) {
                metaHtml += `<div style="color:${COLORS.text};font-size:12px;max-height:80px;overflow:auto;margin-bottom:4px;white-space:pre-wrap;">${metadata.description}</div>`;
            }
            if (metadata.tags && metadata.tags.length > 0) {
                metaHtml += `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">` +
                    metadata.tags.map(tag => `<span style="background:${COLORS.accent};color:white;padding:2px 8px;border-radius:12px;font-size:11px;">${tag}</span>`).join('') +
                    `</div>`;
            }
        } else {
            metaHtml += `<div style="color:${COLORS.textDim};font-size:12px;">暂无 Civitai 元数据，请先在详情页同步</div>`;
        }
        metaReadOnly.innerHTML = metaHtml;
        editContent.appendChild(metaReadOnly);

        editContent.appendChild(promptLabel);
        editContent.appendChild(promptInput);
        editContent.appendChild(imageLabel);
        editContent.appendChild(imageUploadArea);
        editContent.appendChild(fileInput);

        // 元数据预览图区域（Civitai 同步封面，支持删除，参考自定义封面）
        const metaImageLabel = document.createElement("div");
        metaImageLabel.textContent = "元数据预览图片 (Civitai)";
        metaImageLabel.style.cssText = `color:${COLORS.text};font-size:12px;margin:12px 0 6px;`;

        const metaImageArea = document.createElement("div");
        metaImageArea.style.cssText = `
            width:100%;height:120px;border:2px dashed ${COLORS.border};
            border-radius:4px;display:flex;align-items:center;justify-content:center;
            position:relative;overflow:hidden;background:${COLORS.inputBg};
        `;

        const metaImagePreview = document.createElement("img");
        metaImagePreview.style.cssText = `width:100%;height:100%;object-fit:cover;display:none;`;

        const metaImagePlaceholder = document.createElement("div");
        metaImagePlaceholder.style.cssText = `color:${COLORS.textDim};font-size:12px;text-align:center;`;
        metaImagePlaceholder.innerHTML = "尚无 Civitai 同步封面<br><span style='font-size:10px;'>同步后可在此删除</span>";

        if (hasMetadataPreview) {
            metaImagePreview.src = `/naiba/lora/metadata/preview?name=${encodeURIComponent(loraName)}&t=${Date.now()}`;
            metaImagePreview.style.display = 'block';
            metaImagePlaceholder.style.display = 'none';
        }

        metaImageArea.appendChild(metaImagePreview);
        metaImageArea.appendChild(metaImagePlaceholder);

        // 删除元数据封面按钮（与自定义封面的删除按钮一致）
        const removeMetaBtn = document.createElement("div");
        removeMetaBtn.textContent = "\u2715";
        removeMetaBtn.title = "删除 Civitai 元数据封面（不影响自定义封面）";
        removeMetaBtn.style.cssText = `
            position:absolute;top:4px;right:4px;
            width:20px;height:20px;border-radius:50%;
            background:rgba(0,0,0,0.7);color:white;
            display:${hasMetadataPreview ? 'flex' : 'none'};
            align-items:center;justify-content:center;
            cursor:pointer;font-size:12px;
        `;
        removeMetaBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            if (!confirm("确定删除 Civitai 元数据封面？自定义封面不受影响。")) return;
            try {
                const delResp = await api.fetchApi(`/naiba/lora/metadata/preview?name=${encodeURIComponent(loraName)}`, {
                    method: 'DELETE'
                });
                const delResult = await delResp.json();
                if (delResult.success) {
                    metaImagePreview.style.display = 'none';
                    metaImagePlaceholder.style.display = 'block';
                    removeMetaBtn.style.display = 'none';
                    // 刷新列表与节点封面（若无自定义封面则回退为无图）
                    modalTimestamp = Date.now();
                    renderLoraList();
                    if (node._updateLoraDataPreview) {
                        node._updateLoraDataPreview();
                    }
                } else {
                    alert("删除失败: " + (delResult.error || "未知错误"));
                }
            } catch (err) {
                console.error("[LoraDataPreview] 删除元数据封面失败:", err);
                alert("删除失败: " + err.message);
            }
        });
        metaImageArea.appendChild(removeMetaBtn);

        editContent.appendChild(metaImageLabel);
        editContent.appendChild(metaImageArea);

        // 自定义下载链接
        const downloadLinkLabel = document.createElement("div");
        downloadLinkLabel.textContent = "自定义下载链接";
        downloadLinkLabel.style.cssText = `color:${COLORS.text};font-size:12px;margin:12px 0 6px;`;

        const downloadLinkInput = document.createElement("input");
        downloadLinkInput.type = "url";
        downloadLinkInput.value = customData.custom_download_link || "";
        downloadLinkInput.placeholder = "https://...";
        downloadLinkInput.style.cssText = `
            width:100%;padding:8px;
            background:${COLORS.inputBg};border:1px solid ${COLORS.border};
            border-radius:4px;color:${COLORS.text};font-size:12px;
            outline:none;box-sizing:border-box;
        `;

        editContent.appendChild(downloadLinkLabel);
        editContent.appendChild(downloadLinkInput);

        // 自定义NSFW分级
        const nsfwLabel = document.createElement("div");
        nsfwLabel.textContent = "NSFW 分级";
        nsfwLabel.style.cssText = `color:${COLORS.text};font-size:12px;margin:12px 0 6px;`;

        const nsfwSelect = document.createElement("select");
        nsfwSelect.style.cssText = `
            width:100%;padding:8px;
            background:${COLORS.inputBg};border:1px solid ${COLORS.border};
            border-radius:4px;color:${COLORS.text};font-size:12px;
            outline:none;box-sizing:border-box;
        `;
        const nsfwOptions = [
            { value: 0, label: "安全" },
            { value: 1, label: "温和" },
            { value: 2, label: "中等" },
            { value: 3, label: "敏感" },
            { value: 4, label: "成人" }
        ];
        nsfwOptions.forEach(opt => {
            const option = document.createElement("option");
            option.value = opt.value;
            option.textContent = opt.label;
            if (opt.value === (customData.custom_nsfw_level || 0)) {
                option.selected = true;
            }
            nsfwSelect.appendChild(option);
        });

        editContent.appendChild(nsfwLabel);
        editContent.appendChild(nsfwSelect);

        // 自定义模型介绍
        const descriptionLabel = document.createElement("div");
        descriptionLabel.textContent = "模型介绍";
        descriptionLabel.style.cssText = `color:${COLORS.text};font-size:12px;margin:12px 0 6px;`;

        const descriptionInput = document.createElement("textarea");
        descriptionInput.value = customData.custom_model_description || "";
        descriptionInput.placeholder = "输入模型介绍...";
        descriptionInput.style.cssText = `
            width:100%;height:100px;padding:8px;
            background:${COLORS.inputBg};border:1px solid ${COLORS.border};
            border-radius:4px;color:${COLORS.text};font-size:12px;
            resize:vertical;outline:none;box-sizing:border-box;
        `;

        editContent.appendChild(descriptionLabel);
        editContent.appendChild(descriptionInput);

        editModal.appendChild(editContent);

        // 底部按钮
        const editFooter = document.createElement("div");
        editFooter.style.cssText = `
            display:flex;justify-content:flex-end;gap:8px;
            padding:12px 16px;background:${COLORS.headerBg};
            border-top:1px solid ${COLORS.border};
            flex-shrink:0;
        `;

        const cancelBtn = document.createElement("button");
        cancelBtn.textContent = "取消";
        cancelBtn.style.cssText = `
            padding:8px 16px;background:transparent;
            color:${COLORS.textDim};border:1px solid ${COLORS.border};
            border-radius:4px;cursor:pointer;font-size:12px;
        `;
        cancelBtn.addEventListener("click", () => {
            document.body.removeChild(editOverlay);
        });

        const saveBtn = document.createElement("button");
        saveBtn.textContent = "保存";
        saveBtn.style.cssText = `
            padding:8px 16px;background:${COLORS.accent};
            color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
        `;
        saveBtn.addEventListener("click", async () => {
            const newCustomData = {
                custom_prompt: promptInput.value,
                custom_preview_image_path: currentCustomImage,
                custom_download_link: downloadLinkInput.value,
                custom_nsfw_level: parseInt(nsfwSelect.value),
                custom_model_description: descriptionInput.value
            };
            await saveCustomDataEdit(loraName, newCustomData);
            document.body.removeChild(editOverlay);
        });

        editFooter.appendChild(cancelBtn);
        editFooter.appendChild(saveBtn);
        editModal.appendChild(editFooter);

        editOverlay.appendChild(editModal);
        document.body.appendChild(editOverlay);

        // ESC 关闭
        const editEscHandler = (e) => {
            if (e.key === "Escape") {
                document.body.removeChild(editOverlay);
                document.removeEventListener("keydown", editEscHandler);
            }
        };
        document.addEventListener("keydown", editEscHandler);
    }

    // ========== 上传自定义图片 ==========
    async function uploadCustomImage(loraName, file, imagePreview, imagePlaceholder, removeImageBtn) {
        try {
            const formData = new FormData();
            formData.append('name', loraName);
            formData.append('file', file);

            const response = await api.fetchApi('/naiba/lora/custom-data/upload-image', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (result.success && result.image_path) {
                imagePreview.src = `/naiba/lora/custom-data/image?name=${encodeURIComponent(loraName)}&t=${Date.now()}`;
                imagePreview.style.display = 'block';
                imagePlaceholder.style.display = 'none';
                removeImageBtn.style.display = 'flex';
                return result.image_path;
            } else {
                alert("上传失败: " + (result.error || "未知错误"));
                return null;
            }
        } catch (e) {
            console.error("[LoraDataPreview] 上传图片失败:", e);
            alert("上传失败: " + e.message);
            return null;
        }
    }

    // ========== 保存自定义数据编辑 ==========
    async function saveCustomDataEdit(loraName, customData) {
        try {
            const response = await api.fetchApi('/naiba/lora/custom-data/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: loraName,
                    custom_data: customData
                })
            });
            const result = await response.json();

            if (result.success) {
                // 保存成功，更新时间戳并刷新列表
                modalTimestamp = Date.now();
                renderLoraList();
            } else {
                alert("保存失败: " + (result.error || "未知错误"));
            }
        } catch (e) {
            console.error("[LoraDataPreview] 保存自定义数据失败:", e);
            alert("保存失败: " + e.message);
        }
    }

    // ========== 显示LoRA详情 ==========
    async function showLoraDetail(loraName) {
        // 创建详情模态框
        const detailOverlay = document.createElement("div");
        detailOverlay.style.cssText = `
            position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.9);z-index:10001;
            display:flex;align-items:center;justify-content:center;
        `;

        const detailModal = document.createElement("div");
        detailModal.style.cssText = `
            width:80vw;max-width:800px;height:80vh;
            background:${COLORS.modalBg};
            border-radius:8px;border:1px solid ${COLORS.border};
            display:flex;flex-direction:column;overflow:hidden;
            box-shadow:0 10px 40px rgba(0,0,0,0.5);
        `;

        // 详情标题栏
        const detailHeader = document.createElement("div");
        detailHeader.style.cssText = `
            display:flex;align-items:center;justify-content:space-between;
            padding:12px 16px;background:${COLORS.headerBg};
            border-bottom:1px solid ${COLORS.border};
        `;

        const detailTitle = document.createElement("div");
        detailTitle.textContent = `LoRA 详情: ${loraName.split('/').pop().split('\\').pop()}`;
        detailTitle.style.cssText = `color:${COLORS.text};font-size:16px;font-weight:600;`;

        const detailCloseBtn = document.createElement("div");
        detailCloseBtn.textContent = "\u2715";
        detailCloseBtn.style.cssText = `
            color:${COLORS.textDim};cursor:pointer;font-size:16px;
            padding:4px 8px;border-radius:4px;transition:all 0.15s;
        `;
        detailCloseBtn.addEventListener("click", () => {
            document.body.removeChild(detailOverlay);
        });

        detailHeader.appendChild(detailTitle);
        detailHeader.appendChild(detailCloseBtn);
        detailModal.appendChild(detailHeader);

        // 详情内容
        const detailContent = document.createElement("div");
        detailContent.style.cssText = `
            flex:1;overflow-y:auto;padding:16px;
            background:${COLORS.contentBg};
        `;
        detailContent.innerHTML = `<div style="color:${COLORS.textDim};text-align:center;padding:40px;">加载中...</div>`;
        detailModal.appendChild(detailContent);

        detailOverlay.appendChild(detailModal);
        document.body.appendChild(detailOverlay);

        // 加载详情数据
        try {
            const detailController = new AbortController();
            const detailTimeoutId = setTimeout(() => detailController.abort(), 10000);
            const response = await fetch(`/naiba/lora/detail?name=${encodeURIComponent(loraName)}`, { signal: detailController.signal });
            clearTimeout(detailTimeoutId);
            const result = await response.json();
            
            // 清空“加载中...”占位，避免真实内容被追加在其下方形成常驻加载框
            detailContent.innerHTML = "";
            
            // 解析响应数据
            const metadata = result.metadata;
            const customData = result.custom_data;
            const hasMetadata = result.has_cached_metadata;
            const hasCustomData = result.has_custom_data;
            
            // 创建标签页容器
            const tabsContainer = document.createElement("div");
            tabsContainer.style.cssText = `
                display:flex;gap:2px;background:${COLORS.inputBg};border-radius:4px;padding:2px;margin-bottom:16px;
            `;
            
            const tabMetadata = document.createElement("div");
            tabMetadata.textContent = "元数据";
            tabMetadata.style.cssText = `
                padding:6px 16px;border-radius:3px;cursor:pointer;font-size:13px;
                background:${COLORS.accent};color:white;transition:all 0.2s;
            `;
            
            const tabCustom = document.createElement("div");
            tabCustom.textContent = "自定义";
            tabCustom.style.cssText = `
                padding:6px 16px;border-radius:3px;cursor:pointer;font-size:13px;
                background:transparent;color:${COLORS.textDim};transition:all 0.2s;
            `;
            
            tabsContainer.appendChild(tabMetadata);
            tabsContainer.appendChild(tabCustom);
            detailContent.appendChild(tabsContainer);
            
            // 创建内容容器
            const metadataContent = document.createElement("div");
            metadataContent.style.cssText = `display:block;`;
            
            const customContent = document.createElement("div");
            customContent.style.cssText = `display:none;`;
            
            detailContent.appendChild(metadataContent);
            detailContent.appendChild(customContent);
            
            // 标签切换逻辑
            let currentTab = "metadata";
            const switchTab = (tab) => {
                currentTab = tab;
                if (tab === "metadata") {
                    tabMetadata.style.background = COLORS.accent;
                    tabMetadata.style.color = "white";
                    tabCustom.style.background = "transparent";
                    tabCustom.style.color = COLORS.textDim;
                    metadataContent.style.display = "block";
                    customContent.style.display = "none";
                } else {
                    tabMetadata.style.background = "transparent";
                    tabMetadata.style.color = COLORS.textDim;
                    tabCustom.style.background = COLORS.accent;
                    tabCustom.style.color = "white";
                    metadataContent.style.display = "none";
                    customContent.style.display = "block";
                }
            };
            
            tabMetadata.addEventListener("click", () => switchTab("metadata"));
            tabCustom.addEventListener("click", () => switchTab("custom"));
            
            // 渲染元数据标签页内容
            if (hasMetadata && metadata) {
                let metadataHtml = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">`;
                
                // 左侧：预览图
                metadataHtml += `<div>`;
                metadataHtml += `<div style="background:${COLORS.inputBg};border-radius:6px;overflow:hidden;margin-bottom:12px;">`;
                metadataHtml += `<img src="/naiba/lora/preview?name=${encodeURIComponent(loraName)}&t=${Date.now()}" 
                         style="width:100%;height:auto;display:block;" 
                         onerror="this.style.display='none';this.parentElement.innerHTML='<div style=\\'padding:40px;text-align:center;color:${COLORS.textDim}\\'>无预览图</div>';">`;
                metadataHtml += `</div>`;
                
                // 同步按钮（15秒超时）
                metadataHtml += `<button id="detail-sync-btn" onclick="
                    var btn=this;btn.disabled=true;btn.textContent='同步中...';btn.style.background='#555';btn.style.cursor='wait';
                    var c=new AbortController();var tid=setTimeout(function(){c.abort();},15000);
                    fetch('/naiba/lora/civitai-sync?name=${encodeURIComponent(loraName)}',{signal:c.signal}).then(function(r){clearTimeout(tid);return r.json();}).then(function(r){
                        if(r.success){btn.textContent='✓ 已同步';btn.style.background='${COLORS.success}';btn.style.cursor='default';
                            setTimeout(function(){btn.textContent='从 Civitai 同步';btn.style.background='${COLORS.accent}';btn.style.cursor='pointer';btn.disabled=false;},3000);}
                        else{btn.textContent='失败: '+(r.error||'未知');btn.style.background='${COLORS.danger}';btn.style.cursor='pointer';
                            setTimeout(function(){btn.textContent='从 Civitai 同步';btn.style.background='${COLORS.accent}';btn.disabled=false;},2000);}
                    }).catch(function(e){clearTimeout(tid);btn.textContent=e.name==='AbortError'?'超时':'错误';btn.style.background='${COLORS.danger}';btn.style.cursor='pointer';
                        setTimeout(function(){btn.textContent='从 Civitai 同步';btn.style.background='${COLORS.accent}';btn.disabled=false;},2000);})
                " style="width:100%;padding:8px;background:${COLORS.accent};color:white;border:none;border-radius:4px;cursor:pointer;">
                         从 Civitai 同步</button>`;
                metadataHtml += `</div>`;
                
                // 右侧：元数据
                metadataHtml += `<div>`;
                
                if (metadata.model_name) {
                    metadataHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">模型名称</div>
                        <div style="color:${COLORS.text};font-size:14px;">${metadata.model_name}</div>
                    </div>`;
                }
                
                if (metadata.version_name) {
                    metadataHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">版本</div>
                        <div style="color:${COLORS.text};font-size:14px;">${metadata.version_name}</div>
                    </div>`;
                }
                
                if (metadata.base_model) {
                    metadataHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">基础模型</div>
                        <div style="color:${COLORS.text};font-size:14px;">${metadata.base_model}</div>
                    </div>`;
                }
                
                const detailTriggerWords = metadata.trigger_words || metadata.trained_words || [];
                if (detailTriggerWords.length > 0) {
                    metadataHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">触发词</div>
                        <div style="color:${COLORS.accent};font-size:14px;">${detailTriggerWords.join(', ')}</div>
                    </div>`;
                }
                
                if (metadata.description) {
                    metadataHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">描述</div>
                        <div style="color:${COLORS.text};font-size:13px;max-height:100px;overflow-y:auto;">${metadata.description}</div>
                    </div>`;
                }
                
                if (metadata.tags && metadata.tags.length > 0) {
                    metadataHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">标签</div>
                        <div style="display:flex;flex-wrap:wrap;gap:4px;">
                            ${metadata.tags.map(tag => `<span style="background:${COLORS.accent};color:white;padding:2px 8px;border-radius:12px;font-size:11px;">${tag}</span>`).join('')}
                        </div>
                    </div>`;
                }
                
                metadataHtml += `</div>`;
                metadataHtml += `</div>`;
                
                metadataContent.innerHTML = metadataHtml;
            } else {
                metadataContent.innerHTML = `<div style="color:${COLORS.textDim};text-align:center;padding:40px;">未找到元数据，请先同步</div>`;
            }
            
            // 渲染自定义标签页内容
            if (hasCustomData && customData) {
                let customHtml = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">`;
                
                // 左侧：自定义预览图
                customHtml += `<div>`;
                customHtml += `<div style="background:${COLORS.inputBg};border-radius:6px;overflow:hidden;margin-bottom:12px;">`;
                if (customData.custom_preview_image_path) {
                    customHtml += `<img src="/naiba/lora/custom-data/image?name=${encodeURIComponent(loraName)}&t=${Date.now()}" 
                             style="width:100%;height:auto;display:block;" 
                             onerror="this.style.display='none';this.parentElement.innerHTML='<div style=\\'padding:40px;text-align:center;color:${COLORS.textDim}\\'>无自定义预览图</div>';">`;
                } else {
                    customHtml += `<div style="padding:40px;text-align:center;color:${COLORS.textDim};">无自定义预览图</div>`;
                }
                customHtml += `</div>`;
                customHtml += `</div>`;
                
                // 右侧：自定义数据
                customHtml += `<div>`;
                
                if (customData.custom_prompt) {
                    customHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">自定义提示词</div>
                        <div style="color:${COLORS.text};font-size:13px;max-height:100px;overflow-y:auto;white-space:pre-wrap;">${customData.custom_prompt}</div>
                    </div>`;
                }
                
                if (customData.custom_download_link) {
                    customHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">下载链接</div>
                        <div style="color:${COLORS.accent};font-size:13px;word-break:break-all;">
                            <a href="${customData.custom_download_link}" target="_blank" style="color:${COLORS.accent};text-decoration:none;">${customData.custom_download_link}</a>
                        </div>
                    </div>`;
                }
                
                if (customData.custom_nsfw_level !== undefined) {
                    const nsfwLabels = { 0: "安全", 1: "温和", 2: "中等", 3: "敏感", 4: "成人" };
                    const nsfwLabel = nsfwLabels[customData.custom_nsfw_level] || `级别 ${customData.custom_nsfw_level}`;
                    customHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">NSFW 级别</div>
                        <div style="color:${COLORS.text};font-size:14px;">${nsfwLabel}</div>
                    </div>`;
                }
                
                if (customData.custom_model_description) {
                    customHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">模型介绍</div>
                        <div style="color:${COLORS.text};font-size:13px;max-height:100px;overflow-y:auto;white-space:pre-wrap;">${customData.custom_model_description}</div>
                    </div>`;
                }
                
                if (customData.updated_at) {
                    customHtml += `<div style="margin-bottom:12px;">
                        <div style="color:${COLORS.textDim};font-size:12px;margin-bottom:4px;">最后更新</div>
                        <div style="color:${COLORS.textDim};font-size:12px;">${new Date(customData.updated_at).toLocaleString()}</div>
                    </div>`;
                }
                
                customHtml += `</div>`;
                customHtml += `</div>`;
                
                customContent.innerHTML = customHtml;

                // 自定义标签页底部：删除全部自定义数据按钮
                const deleteBar = document.createElement("div");
                deleteBar.style.cssText = `
                    margin-top:16px;padding-top:16px;border-top:1px solid ${COLORS.border};
                    display:flex;justify-content:flex-end;
                `;
                const deleteCustomBtn = document.createElement("button");
                deleteCustomBtn.textContent = "删除自定义数据";
                deleteCustomBtn.title = "删除该 LoRA 的全部自定义数据（含自定义封面），不影响 Civitai 元数据";
                deleteCustomBtn.style.cssText = `
                    padding:8px 16px;background:${COLORS.danger};
                    color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
                `;
                deleteCustomBtn.addEventListener("mouseenter", () => {
                    deleteCustomBtn.style.background = COLORS.dangerHover;
                });
                deleteCustomBtn.addEventListener("mouseleave", () => {
                    deleteCustomBtn.style.background = COLORS.danger;
                });
                deleteCustomBtn.addEventListener("click", async () => {
                    if (!confirm("确定删除该 LoRA 的全部自定义数据（含自定义封面）？此操作不可撤销，且不影响 Civitai 元数据。")) return;
                    deleteCustomBtn.disabled = true;
                    deleteCustomBtn.textContent = "删除中...";
                    try {
                        const delResp = await api.fetchApi(`/naiba/lora/custom-data?name=${encodeURIComponent(loraName)}`, {
                            method: 'DELETE'
                        });
                        const delResult = await delResp.json();
                        if (delResult.success) {
                            // 更新视图：自定义标签页回到空态
                            customContent.innerHTML = `<div style="color:${COLORS.textDim};text-align:center;padding:40px;">暂无自定义数据，点击编辑按钮添加</div>`;
                            // 刷新主列表与节点封面（回退到元数据封面/无图）
                            modalTimestamp = Date.now();
                            renderLoraList();
                            if (node._updateLoraDataPreview) {
                                node._updateLoraDataPreview();
                            }
                        } else {
                            alert("删除失败: " + (delResult.error || "未知错误"));
                            deleteCustomBtn.disabled = false;
                            deleteCustomBtn.textContent = "删除自定义数据";
                        }
                    } catch (err) {
                        console.error("[LoraDataPreview] 删除自定义数据失败:", err);
                        alert("删除失败: " + err.message);
                        deleteCustomBtn.disabled = false;
                        deleteCustomBtn.textContent = "删除自定义数据";
                    }
                });
                deleteBar.appendChild(deleteCustomBtn);
                customContent.appendChild(deleteBar);
            } else {
                customContent.innerHTML = `<div style="color:${COLORS.textDim};text-align:center;padding:40px;">暂无自定义数据，点击编辑按钮添加</div>`;
            }
        } catch (error) {
            const isTimeout = error.name === 'AbortError';
            console.error("[LoraDataPreview] 加载详情失败:", error);
            detailContent.innerHTML = isTimeout 
                ? `<div style="color:${COLORS.danger};text-align:center;padding:40px;">加载超时，请检查网络连接</div>`
                : `<div style="color:${COLORS.danger};text-align:center;padding:40px;">加载失败: ${error.message}</div>`;
        }

        // ESC 关闭详情
        const detailEscHandler = (e) => {
            if (e.key === "Escape") {
                document.body.removeChild(detailOverlay);
                document.removeEventListener("keydown", detailEscHandler);
            }
        };
        document.addEventListener("keydown", detailEscHandler);
    }

    // ========== 初始化 ==========
    // 加载收藏数据后渲染列表
    loadFavorites().then(() => {
        renderFolderTree();
        renderLoraList();
    });

    // 设置单例
    currentModal = modal;
    modal.focus = () => {
        overlay.style.display = "flex";
    };
}

// ========== 注册扩展 ==========

app.registerExtension({
    name: "naiba.LoraDataPreview",

    async setup(appInstance) {
        // 通过 app.menu.element 注入顶部工具栏按钮
        if (app.menu && app.menu.element) {
            // 检查是否已注入，避免重复
            if (document.getElementById("naiba-toolbar-btn")) return;

            const wrap = document.createElement("div");
            wrap.id = "naiba-toolbar-btn";
            wrap.style.cssText = "display:flex;gap:6px;margin:4px 0;";

            const btn = document.createElement("button");
            btn.className = "comfy-button";
            btn.textContent = "NAIBA";
            btn.title = "打开 NAIBA LoRA 浏览器";
            btn.style.cssText = `
                background: linear-gradient(180deg, #6366f1, #4f46e5);
                color: #fff;
                border: 1px solid #4338ca;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.2);
                padding: 5px 16px;
                font-weight: 600;
                font-size: 13px;
                border-radius: 4px;
                cursor: pointer;
                transition: all 0.15s ease;
            `;
            btn.addEventListener("mouseenter", () => {
                btn.style.background = "linear-gradient(180deg, #7c3aed, #6366f1)";
                btn.style.transform = "translateY(-1px)";
                btn.style.boxShadow = "0 3px 6px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.25)";
            });
            btn.addEventListener("mouseleave", () => {
                btn.style.background = "linear-gradient(180deg, #6366f1, #4f46e5)";
                btn.style.transform = "";
                btn.style.boxShadow = "0 2px 4px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.2)";
            });
            btn.addEventListener("click", async () => {
                let loras = [];
                try {
                    const resp = await api.fetchApi("/naiba/lora/list-all");
                    const data = await resp.json();
                    if (data.loras) {
                        loras = data.loras;
                    }
                } catch (e) {
                    console.warn("[NAIBA] Cannot fetch Lora list:", e);
                }
                createLoraDataPreviewModal(null, loras);
            });

            wrap.append(btn);
            try { app.menu.element.prepend(wrap); } catch (_) {}
        }
    },

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "LoraDataPreview") return;

        // 获取Lora文件列表
        let loraList = [];
        try {
            const resp = await api.fetchApi("/object_info/LoraLoader");
            const info = await resp.json();
            if (info.LoraLoader?.input?.required?.lora_name) {
                loraList = info.LoraLoader.input.required.lora_name[0] || [];
            }
        } catch (e) {
            console.warn("[LoraDataPreview] Cannot fetch Lora list:", e);
        }

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            const node = this;

            // 隐藏lora_data控件
            const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
            if (loraDataWidget) {
                loraDataWidget.hidden = true;
                if (loraDataWidget.inputEl) loraDataWidget.inputEl.style.display = "none";
                if (loraDataWidget.element) loraDataWidget.element.style.display = "none";
            }

            // 创建已选LoRA列表预览区域
            const previewArea = document.createElement("div");
            previewArea.style.cssText = `
                width:100%;min-height:60px;max-height:140px;background:${COLORS.inputBg};
                border:1px solid ${COLORS.border};border-radius:4px;
                margin:8px 0;padding:6px;overflow-y:auto;
                font-size:11px;color:${COLORS.text};
            `;
            previewArea.innerHTML = `<div style="color:${COLORS.textDim};text-align:center;padding:16px;">点击下方按钮选择LoRA</div>`;

            // 更新已选LoRA列表显示（带删除按钮）
            const updatePreview = () => {
                const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
                if (!loraDataWidget) return;
                
                try {
                    const data = JSON.parse(loraDataWidget.value || "[]");
                    if (data.length === 0) {
                        previewArea.innerHTML = `<div style="color:${COLORS.textDim};text-align:center;padding:16px;">点击下方按钮选择LoRA</div>`;
                        return;
                    }
                    
                    let html = `<div style="display:flex;flex-direction:column;gap:2px;">`;
                    data.forEach((item, index) => {
                        if (item.name) {
                            const displayName = item.name.split('/').pop().split('\\').pop();
                            html += `<div style="display:flex;align-items:center;justify-content:space-between;padding:2px 4px;border-radius:3px;" onmouseenter="this.style.background='rgba(255,255,255,0.05)'" onmouseleave="this.style.background='transparent'">
                                <span style="color:${COLORS.accent};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">${displayName}</span>
                                <span data-remove="${index}" style="color:${COLORS.danger};cursor:pointer;font-size:14px;padding:0 4px;opacity:0.6;" onmouseenter="this.style.opacity='1'" onmouseleave="this.style.opacity='0.6'">×</span>
                            </div>`;
                        }
                    });
                    html += `</div>`;
                    previewArea.innerHTML = html;
                    
                    // 绑定删除事件
                    previewArea.querySelectorAll('[data-remove]').forEach(btn => {
                        btn.addEventListener('click', (e) => {
                            e.stopPropagation();
                            const removeIndex = parseInt(btn.dataset.remove);
                            const currentData = JSON.parse(loraDataWidget.value || "[]");
                            currentData.splice(removeIndex, 1);
                            loraDataWidget.value = JSON.stringify(currentData);
                            updatePreview();
                        });
                    });
                } catch (e) {
                    previewArea.innerHTML = `<div style="color:${COLORS.textDim};text-align:center;padding:16px;">点击下方按钮选择LoRA</div>`;
                }
            };

            // 初始化预览图
            updatePreview();

            // 创建打开弹窗的按钮
            const openBtn = document.createElement("button");
            openBtn.textContent = "打开 LoRA 数据预览";
            openBtn.style.cssText = `
                width:100%;padding:10px;margin:8px 0;
                background:${COLORS.accent};color:white;
                border:none;border-radius:6px;cursor:pointer;
                font-size:13px;font-weight:500;
                transition:background 0.2s;
            `;
            openBtn.addEventListener("mouseenter", () => {
                openBtn.style.background = COLORS.accentHover;
            });
            openBtn.addEventListener("mouseleave", () => {
                openBtn.style.background = COLORS.accent;
            });
            openBtn.addEventListener("click", () => {
                createLoraDataPreviewModal(node, loraList);
            });

            // 创建容器
            const container = document.createElement("div");
            container.style.cssText = "display:flex;flex-direction:column;gap:4px;width:100%;box-sizing:border-box;";
            container.appendChild(previewArea);
            container.appendChild(openBtn);

            // 注册DOM控件
            node.addDOMWidget("lora_data_preview_container", "LORA_DATA_PREVIEW_CONTAINER", container, {
                getValue() { return ""; },
                setValue() {},
            });

            // 将updatePreview函数附加到节点上，以便在弹窗中调用
            node._updateLoraDataPreview = updatePreview;

            node.minWidth = 220;
            node.minHeight = 180;
        };
    },
});