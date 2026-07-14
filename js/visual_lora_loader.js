/**
 * Visual LoRA Loader - 前端UI扩展
 * 提供全屏模态弹窗选择LoRA，支持图片预览、搜索导航、文件夹浏览、网格/列表视图切换
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { createPresetsModal } from "./naiba_preset_utils.js";

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
    favorite: "#ff9f43",      // 收藏按钮颜色（橙色）
    favoriteActive: "#ff6b6b", // 已收藏颜色（红色）
    text: "#e0e0e0",
    textDim: "#888",
    border: "#2a3a5c",
    inputBg: "#0a0f1e",
    listItemBg: "#16213e",
    listItemHover: "#1e2a4a",
    listItemActive: "#2a3a6a",
    cardBg: "#16213e",
    cardBorder: "#2a3a5c",
    favoriteBorder: "#ff9f43", // 收藏卡片边框颜色
    disabled: "#555555",       // 禁用状态颜色（灰色）
};

// ========== 单例模态框管理 ==========
let currentModal = null;

/**
 * 创建Visual LoRA Loader模态框
 * @param {Object} node - ComfyUI 节点实例
 * @param {Array} loraList - LoRA文件列表
 */
function createVisualLoraModal(node, loraList) {
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
    title.textContent = "Visual LoRA Loader";
    title.style.cssText = `color:${COLORS.text};font-size:16px;font-weight:600;`;

    const headerRight = document.createElement("div");
    headerRight.style.cssText = "display:flex;align-items:center;gap:12px;";

    // 视图切换按钮
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
    header.appendChild(headerRight);
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // ========== 工具栏 ==========
    const toolbar = document.createElement("div");
    toolbar.style.cssText = `
        display:flex;align-items:center;gap:12px;padding:8px 16px;
        background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};
    `;

    // 搜索框
    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "搜索LoRA...";
    searchInput.style.cssText = `
        flex:1;max-width:300px;padding:6px 10px;
        background:${COLORS.inputBg};border:1px solid ${COLORS.border};
        border-radius:4px;color:${COLORS.text};font-size:12px;outline:none;
    `;

    // 文件夹导航
    const folderNav = document.createElement("div");
    folderNav.style.cssText = `
        display:flex;align-items:center;gap:4px;flex:1;
    `;

    const currentPath = document.createElement("span");
    currentPath.textContent = "/";
    currentPath.style.cssText = `color:${COLORS.textDim};font-size:12px;`;

    folderNav.appendChild(currentPath);

    // 预设按钮
    const presetBtn = document.createElement("button");
    presetBtn.textContent = "预设";
    presetBtn.style.cssText = `
        padding:6px 12px;background:${COLORS.accent};
        color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
    `;
    presetBtn.addEventListener("click", () => {
        openPresetsModal(node);
    });

    toolbar.appendChild(searchInput);
    toolbar.appendChild(folderNav);
    toolbar.appendChild(presetBtn);
    
    // 刷新列表按钮
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
                filteredLoras = [...loraList];
                // 更新文件夹结构
                folderStructure = buildFolderStructure(loraList);
                // 重新渲染列表
                renderLoraList();
            }
        } catch (e) {
            console.warn("[VisualLoRALoader] 刷新列表失败:", e);
        }
        refreshBtn.textContent = "刷新列表";
        refreshBtn.disabled = false;
    });
    toolbar.appendChild(refreshBtn);
    
    modal.appendChild(toolbar);

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

    // ========== 底部状态栏 ==========
    const statusBar = document.createElement("div");
    statusBar.style.cssText = `
        display:flex;align-items:center;justify-content:space-between;
        padding:8px 16px;background:${COLORS.headerBg};
        border-top:1px solid ${COLORS.border};
    `;

    const selectedCount = document.createElement("span");
    selectedCount.textContent = "已选择: 0 个LoRA";
    selectedCount.style.cssText = `color:${COLORS.textDim};font-size:12px;`;

    const buttonGroup = document.createElement("div");
    buttonGroup.style.cssText = "display:flex;gap:8px;";

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "取消";
    cancelBtn.style.cssText = `
        padding:8px 16px;background:transparent;
        color:${COLORS.textDim};border:1px solid ${COLORS.border};
        border-radius:4px;cursor:pointer;font-size:12px;
    `;
    cancelBtn.addEventListener("click", () => closeModal());

    const applyBtn = document.createElement("button");
    applyBtn.textContent = "应用";
    applyBtn.style.cssText = `
        padding:8px 16px;background:${COLORS.accent};
        color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
    `;
    applyBtn.addEventListener("click", () => {
        applySelectedLoras();
        closeModal();
    });

    buttonGroup.appendChild(cancelBtn);
    buttonGroup.appendChild(applyBtn);

    statusBar.appendChild(selectedCount);
    statusBar.appendChild(buttonGroup);
    modal.appendChild(statusBar);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // ========== 内部状态 ==========
    let currentView = "grid"; // "grid" or "list"
    let currentFolder = "/";
    let currentCategory = "all"; // "all", "selected", 或 "favorite"
    let selectedLoras = new Map(); // name -> {strength_model, strength_clip, enabled}
    let favoriteLoras = new Map(); // name -> {custom_prompt, custom_image_path, favorited_at}
    let filteredLoras = [...loraList];
    let folderStructure = buildFolderStructure(loraList);

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
            console.warn("[VisualLoRALoader] 加载收藏数据失败:", e);
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
                    renderFolderTree();
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
                    renderFolderTree();
                    renderLoraList();
                }
            }
        } catch (e) {
            console.warn("[VisualLoRALoader] 收藏操作失败:", e);
        }
    }

    // 从节点加载现有选择
    function loadExistingSelection() {
        const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
        if (!loraDataWidget) return;
        try {
            const data = JSON.parse(loraDataWidget.value || "[]");
            data.forEach(item => {
                if (item.name) {
                    selectedLoras.set(item.name, {
                        strength_model: item.strength_model || 1.0,
                        strength_clip: item.strength_clip || 1.0,
                        enabled: item.enabled !== undefined ? item.enabled : true
                    });
                }
            });
        } catch (e) {
            console.warn("[VisualLoraLoader] 加载现有选择失败:", e);
        }
    }
    loadExistingSelection();

    // ========== 关闭模态框 ==========
    function closeModal() {
        document.body.removeChild(overlay);
        currentModal = null;
        document.removeEventListener("keydown", escHandler);
    }

    // ESC 关闭
    const escHandler = (e) => {
        if (e.key === "Escape") closeModal();
    };
    document.addEventListener("keydown", escHandler);

    // ========== 构建文件夹结构 ==========
    function buildFolderStructure(loraList) {
        const structure = { "/": [] };
        
        loraList.forEach(lora => {
            const parts = lora.split(/[\\/]/);
            if (parts.length === 1) {
                // 根目录文件
                structure["/"].push(lora);
            } else {
                // 子目录文件
                let currentPath = "/";
                for (let i = 0; i < parts.length - 1; i++) {
                    const folder = parts[i];
                    const parentPath = currentPath;
                    currentPath = currentPath === "/" ? `/${folder}` : `${currentPath}/${folder}`;
                    
                    if (!structure[currentPath]) {
                        structure[currentPath] = [];
                        // 确保父目录存在
                        if (!structure[parentPath]) {
                            structure[parentPath] = [];
                        }
                        // 添加子目录引用
                        if (!structure[parentPath].includes(folder + "/")) {
                            structure[parentPath].push(folder + "/");
                        }
                    }
                }
                // 添加文件到最终目录
                if (!structure[currentPath]) {
                    structure[currentPath] = [];
                }
                structure[currentPath].push(parts[parts.length - 1]);
            }
        });
        
        return structure;
    }

    // ========== 视图切换 ==========
    gridViewBtn.addEventListener("click", () => {
        currentView = "grid";
        gridViewBtn.style.background = COLORS.accent;
        gridViewBtn.style.color = "white";
        listViewBtn.style.background = "transparent";
        listViewBtn.style.color = COLORS.textDim;
        renderLoraList();
    });

    listViewBtn.addEventListener("click", () => {
        currentView = "list";
        listViewBtn.style.background = COLORS.accent;
        listViewBtn.style.color = "white";
        gridViewBtn.style.background = "transparent";
        gridViewBtn.style.color = COLORS.textDim;
        renderLoraList();
    });

    // ========== 搜索功能 ==========
    searchInput.addEventListener("input", () => {
        const searchTerm = searchInput.value.toLowerCase();
        if (searchTerm) {
            // 搜索所有LoRA，忽略文件夹结构
            filteredLoras = loraList.filter(lora => 
                lora.toLowerCase().includes(searchTerm)
            );
            currentPath.textContent = `/搜索: ${searchTerm}`;
        } else {
            // 恢复当前文件夹视图
            filteredLoras = getLorasInFolder(currentFolder);
            currentPath.textContent = currentFolder;
        }
        renderLoraList();
    });

    // ========== 获取文件夹中的LoRA ==========
    function getLorasInFolder(folder) {
        const items = folderStructure[folder] || [];
        const loras = [];
        
        items.forEach(item => {
            if (item.endsWith("/")) {
                // 这是子文件夹，递归获取所有LoRA
                const subFolder = folder === "/" ? `/${item.slice(0, -1)}` : `${folder}/${item.slice(0, -1)}`;
                loras.push(...getLorasInFolder(subFolder));
            } else {
                // 这是LoRA文件
                const fullPath = folder === "/" ? item : `${folder}/${item}`;
                loras.push(fullPath);
            }
        });
        
        return loras;
    }

    // ========== 渲染文件夹树 ==========
    function renderFolderTree() {
        sidebar.innerHTML = "";
        
        // 类别选项卡
        const categoryTabs = document.createElement("div");
        categoryTabs.style.cssText = `
            display:flex;gap:2px;margin-bottom:8px;
            background:${COLORS.inputBg};border-radius:4px;padding:2px;
        `;
        
        const allTab = document.createElement("button");
        allTab.textContent = "全部";
        allTab.style.cssText = `
            flex:1;padding:6px 8px;border:none;
            background:${currentCategory === "all" ? COLORS.accent : "transparent"};
            color:${currentCategory === "all" ? "white" : COLORS.textDim};
            border-radius:3px;cursor:pointer;font-size:11px;
        `;
        allTab.addEventListener("click", () => {
            currentCategory = "all";
            // 恢复当前文件夹视图
            filteredLoras = getLorasInFolder(currentFolder);
            renderFolderTree();
            renderLoraList();
        });
        
        const selectedTab = document.createElement("button");
        selectedTab.textContent = "已选择";
        selectedTab.style.cssText = `
            flex:1;padding:6px 8px;border:none;
            background:${currentCategory === "selected" ? COLORS.accent : "transparent"};
            color:${currentCategory === "selected" ? "white" : COLORS.textDim};
            border-radius:3px;cursor:pointer;font-size:11px;
        `;
        selectedTab.addEventListener("click", () => {
            currentCategory = "selected";
            // 只显示已选择的LoRA
            filteredLoras = Array.from(selectedLoras.keys());
            renderFolderTree();
            renderLoraList();
        });
        
        const favoriteTab = document.createElement("button");
        favoriteTab.textContent = "收藏";
        favoriteTab.style.cssText = `
            flex:1;padding:6px 8px;border:none;
            background:${currentCategory === "favorite" ? COLORS.favorite : "transparent"};
            color:${currentCategory === "favorite" ? "white" : COLORS.textDim};
            border-radius:3px;cursor:pointer;font-size:11px;
        `;
        favoriteTab.addEventListener("click", () => {
            currentCategory = "favorite";
            // 只显示收藏的LoRA
            filteredLoras = Array.from(favoriteLoras.keys());
            renderFolderTree();
            renderLoraList();
        });
        
        categoryTabs.appendChild(allTab);
        categoryTabs.appendChild(selectedTab);
        categoryTabs.appendChild(favoriteTab);
        sidebar.appendChild(categoryTabs);
        
        // 根目录（仅在"全部"类别下显示）
        if (currentCategory === "all") {
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
                filteredLoras = getLorasInFolder("/");
                renderFolderTree();
                renderLoraList();
            });
            sidebar.appendChild(rootItem);
            
            // 渲染文件夹树
            renderFolderLevel("/", sidebar, 0);
        } else if (currentCategory === "selected") {
            // 已选择类别下，显示提示信息
            const info = document.createElement("div");
            info.style.cssText = `
                padding:8px;font-size:11px;color:${COLORS.textDim};
                text-align:center;
            `;
            info.textContent = `已选择 ${selectedLoras.size} 个LoRA`;
            sidebar.appendChild(info);
        } else if (currentCategory === "favorite") {
            // 收藏类别下，显示提示信息
            const info = document.createElement("div");
            info.style.cssText = `
                padding:8px;font-size:11px;color:${COLORS.textDim};
                text-align:center;
            `;
            info.textContent = `收藏 ${favoriteLoras.size} 个LoRA`;
            sidebar.appendChild(info);
        }
    }

    // ========== 递归渲染文件夹层级 ==========
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
                filteredLoras = getLorasInFolder(fullPath);
                renderFolderTree();
                renderLoraList();
            });
            
            container.appendChild(folderElement);
            
            // 递归渲染子文件夹
            renderFolderLevel(fullPath, container, depth + 1);
        });
    }

    // ========== 渲染LoRA列表 ==========
    function renderLoraList() {
        mainContent.innerHTML = "";
        
        // 根据当前类别确定要渲染的LoRA列表
        let lorasToRender = filteredLoras;
        if (currentCategory === "selected") {
            lorasToRender = Array.from(selectedLoras.keys());
        } else if (currentCategory === "favorite") {
            lorasToRender = Array.from(favoriteLoras.keys());
        }
        
        // 搜索过滤：对当前类别的数据源应用搜索词过滤
        const currentSearchTerm = searchInput.value.toLowerCase().trim();
        if (currentSearchTerm) {
            lorasToRender = lorasToRender.filter(lora =>
                lora.toLowerCase().includes(currentSearchTerm)
            );
        }
        
        if (lorasToRender.length === 0) {
            const emptyMsg = document.createElement("div");
            if (currentCategory === "selected") {
                emptyMsg.textContent = "未选择任何LoRA";
            } else if (currentCategory === "favorite") {
                emptyMsg.textContent = "尚未收藏任何LoRA";
            } else {
                emptyMsg.textContent = "没有找到LoRA文件";
            }
            emptyMsg.style.cssText = `
                color:${COLORS.textDim};text-align:center;padding:40px;font-size:14px;
            `;
            mainContent.appendChild(emptyMsg);
            return;
        }

        if (currentView === "grid") {
            // 网格视图
            const grid = document.createElement("div");
            grid.style.cssText = `
                display:grid;grid-template-columns:repeat(auto-fill, minmax(200px, 1fr));
                gap:12px;padding:8px;
            `;

            lorasToRender.forEach(lora => {
                const isSelected = selectedLoras.has(lora);
                const isFavorited = favoriteLoras.has(lora);
                const isEnabled = isSelected ? (selectedLoras.get(lora).enabled !== false) : true;
                const card = document.createElement("div");
                
                // 卡片边框样式：选中=绿色，收藏=橙色，普通=默认，禁用=灰色
                let borderColor = COLORS.cardBorder;
                let boxShadow = '';
                if (!isEnabled) {
                    borderColor = COLORS.disabled;
                    boxShadow = `box-shadow:0 0 0 1px ${COLORS.disabled}40;`;
                } else if (isSelected) {
                    borderColor = COLORS.accent;
                    boxShadow = `box-shadow:0 0 0 2px ${COLORS.accent}40;`;
                } else if (isFavorited) {
                    borderColor = COLORS.favoriteBorder;
                    boxShadow = `box-shadow:0 0 0 2px ${COLORS.favoriteBorder}40;`;
                }
                
                card.style.cssText = `
                    background:${COLORS.cardBg};border:1px solid ${borderColor};
                    border-radius:6px;padding:12px;cursor:pointer;
                    transition:all 0.2s;position:relative;
                    ${boxShadow}
                    ${!isEnabled ? "opacity:0.5;filter:grayscale(0.6);" : ""}
                `;

                // 图片预览区域
                const preview = document.createElement("div");
                preview.style.cssText = `
                    width:100%;height:120px;background:${COLORS.inputBg};
                    border-radius:4px;margin-bottom:8px;display:flex;
                    align-items:center;justify-content:center;
                    color:${COLORS.textDim};font-size:12px;overflow:hidden;
                    position:relative;
                `;
                
                // 尝试加载预览图 - 使用本地匹配 API
                const previewImg = document.createElement("img");
                previewImg.style.cssText = `
                    width:100%;height:100%;object-fit:cover;
                `;
                
                // 图片加载失败时显示文字提示，但保留其他元素（收藏按钮、红叉按钮）
                previewImg.onerror = () => {
                    // 隐藏图片
                    previewImg.style.display = "none";
                    // 创建文字提示
                    const noPreviewText = document.createElement("div");
                    noPreviewText.style.cssText = `
                        color:${COLORS.textDim};font-size:11px;
                        position:absolute;top:50%;left:50%;
                        transform:translate(-50%,-50%);
                        pointer-events:none;
                    `;
                    noPreviewText.textContent = "无预览图";
                    // 插入到 preview 开头，不影响其他子元素
                    preview.insertBefore(noPreviewText, preview.firstChild);
                };
                
                // 使用本地匹配 API 获取预览图
                // 传递完整的 LoRA 路径（包括子目录），而不是只传文件名
                const previewUrl = `/naiba/lora/preview?name=${encodeURIComponent(lora)}`;
                previewImg.src = previewUrl;
                preview.appendChild(previewImg);

                // 收藏按钮（右下角）
                const favBtn = document.createElement("div");
                favBtn.style.cssText = `
                    position:absolute;bottom:8px;right:8px;z-index:10;
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

                // LoRA名称
                const name = document.createElement("div");
                name.textContent = lora.split('/').pop().split('\\').pop();
                name.style.cssText = `
                    color:${COLORS.text};font-size:12px;
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

                // 选中状态
                const checkmark = document.createElement("div");
                checkmark.textContent = selectedLoras.has(lora) ? "✓" : "";
                checkmark.style.cssText = `
                    position:absolute;top:8px;right:8px;
                    width:20px;height:20px;background:${COLORS.accent};
                    border-radius:50%;display:flex;align-items:center;
                    justify-content:center;color:white;font-size:12px;
                `;

                card.appendChild(preview);
                card.appendChild(name);
                card.appendChild(path);
                card.appendChild(checkmark);

                // 权重控制区域（初始隐藏，选中时显示）
                const weightControls = document.createElement("div");
                weightControls.style.cssText = `
                    display:${selectedLoras.has(lora) ? "flex" : "none"};
                    align-items:center;gap:6px;margin-top:8px;
                    padding-top:8px;border-top:1px solid ${COLORS.border};
                `;

                const mLabel = document.createElement("span");
                mLabel.textContent = "M:";
                mLabel.style.cssText = `color:${COLORS.textDim};font-size:10px;`;

                const mInput = document.createElement("input");
                mInput.type = "number";
                mInput.value = selectedLoras.has(lora) ? selectedLoras.get(lora).strength_model : 1.0;
                mInput.min = -10;
                mInput.max = 10;
                mInput.step = 0.1;
                mInput.style.cssText = `
                    width:45px;padding:2px 4px;background:${COLORS.inputBg};
                    border:1px solid ${COLORS.border};border-radius:3px;
                    color:${COLORS.text};font-size:10px;text-align:center;
                `;
                mInput.addEventListener("change", (e) => {
                    e.stopPropagation();
                    if (selectedLoras.has(lora)) {
                        selectedLoras.get(lora).strength_model = parseFloat(mInput.value);
                    }
                });
                mInput.addEventListener("click", (e) => e.stopPropagation());

                const cLabel = document.createElement("span");
                cLabel.textContent = "C:";
                cLabel.style.cssText = `color:${COLORS.textDim};font-size:10px;`;

                const cInput = document.createElement("input");
                cInput.type = "number";
                cInput.value = selectedLoras.has(lora) ? selectedLoras.get(lora).strength_clip : 1.0;
                cInput.min = -10;
                cInput.max = 10;
                cInput.step = 0.1;
                cInput.style.cssText = `
                    width:45px;padding:2px 4px;background:${COLORS.inputBg};
                    border:1px solid ${COLORS.border};border-radius:3px;
                    color:${COLORS.text};font-size:10px;text-align:center;
                `;
                cInput.addEventListener("change", (e) => {
                    e.stopPropagation();
                    if (selectedLoras.has(lora)) {
                        selectedLoras.get(lora).strength_clip = parseFloat(cInput.value);
                    }
                });
                cInput.addEventListener("click", (e) => e.stopPropagation());

                weightControls.appendChild(mLabel);
                weightControls.appendChild(mInput);
                weightControls.appendChild(cLabel);
                weightControls.appendChild(cInput);

                card.appendChild(weightControls);

                // 已选中时显示删除按钮和启用开关
                if (isSelected) {
                    // 删除按钮（左上角）
                    const deleteBtn = document.createElement("div");
                    deleteBtn.style.cssText = `
                        position:absolute;top:8px;left:8px;z-index:10;
                        width:24px;height:24px;border-radius:50%;
                        display:flex;align-items:center;justify-content:center;
                        cursor:pointer;font-size:14px;font-weight:bold;
                        background:rgba(255,107,107,0.8);backdrop-filter:blur(4px);
                        color:white;transition:all 0.2s;
                    `;
                    deleteBtn.textContent = "×";
                    deleteBtn.title = "移除选中";
                    deleteBtn.addEventListener("click", (e) => {
                        e.stopPropagation();
                        selectedLoras.delete(lora);
                        updateSelectedCount();
                        renderLoraList();
                    });
                    deleteBtn.addEventListener("mouseenter", () => {
                        deleteBtn.style.transform = "scale(1.1)";
                        deleteBtn.style.background = "rgba(255,107,107,1)";
                    });
                    deleteBtn.addEventListener("mouseleave", () => {
                        deleteBtn.style.transform = "scale(1)";
                        deleteBtn.style.background = "rgba(255,107,107,0.8)";
                    });
                    preview.appendChild(deleteBtn);

                    // 启用/禁用开关（预览区底部）
                    const toggleRow = document.createElement("div");
                    toggleRow.style.cssText = `
                        display:flex;align-items:center;justify-content:space-between;
                        margin-top:6px;padding:4px 6px;
                        background:${COLORS.inputBg};border-radius:4px;
                    `;

                    const toggleLabel = document.createElement("span");
                    toggleLabel.textContent = isEnabled ? "已启用" : "已禁用";
                    toggleLabel.style.cssText = `
                        font-size:10px;color:${isEnabled ? COLORS.success : COLORS.disabled};
                    `;

                    const toggleSwitch = document.createElement("div");
                    toggleSwitch.style.cssText = `
                        width:32px;height:16px;border-radius:8px;
                        background:${isEnabled ? COLORS.success : COLORS.disabled};
                        position:relative;cursor:pointer;transition:all 0.2s;
                    `;
                    const toggleDot = document.createElement("div");
                    toggleDot.style.cssText = `
                        width:12px;height:12px;border-radius:50%;
                        background:white;position:absolute;top:2px;
                        transition:all 0.2s;
                        ${isEnabled ? "left:18px;" : "left:2px;"}
                    `;
                    toggleSwitch.appendChild(toggleDot);

                    toggleSwitch.addEventListener("click", (e) => {
                        e.stopPropagation();
                        const config = selectedLoras.get(lora);
                        if (config) {
                            config.enabled = !config.enabled;
                            renderLoraList();
                        }
                    });

                    toggleRow.appendChild(toggleLabel);
                    toggleRow.appendChild(toggleSwitch);
                    card.appendChild(toggleRow);
                }

                card.addEventListener("click", () => {
                    if (!selectedLoras.has(lora)) {
                        selectedLoras.set(lora, {
                            strength_model: parseFloat(mInput.value) || 1.0,
                            strength_clip: parseFloat(cInput.value) || 1.0,
                            enabled: true
                        });
                        weightControls.style.display = "flex";
                    }
                    updateSelectedCount();
                    renderLoraList();
                });

                grid.appendChild(card);
            });

            mainContent.appendChild(grid);
        } else {
            // 列表视图
            const list = document.createElement("div");
            list.style.cssText = `
                display:flex;flex-direction:column;gap:4px;padding:8px;
            `;

            lorasToRender.forEach(lora => {
                const isSelected = selectedLoras.has(lora);
                const isFavorited = favoriteLoras.has(lora);
                const isEnabled = isSelected ? (selectedLoras.get(lora).enabled !== false) : true;
                const item = document.createElement("div");

                // 列表项边框样式：禁用=灰色，选中=绿色，收藏=橙色
                let borderColor = "transparent";
                let borderStyle = "";
                if (!isEnabled) {
                    borderColor = COLORS.disabled;
                    borderStyle = `border:1px solid ${borderColor};box-shadow:0 0 0 1px ${COLORS.disabled}40;`;
                } else if (isSelected) {
                    borderColor = COLORS.accent;
                    borderStyle = `border:1px solid ${borderColor};box-shadow:0 0 0 1px ${COLORS.accent}40;`;
                } else if (isFavorited) {
                    borderColor = COLORS.favoriteBorder;
                    borderStyle = `border:1px solid ${borderColor};box-shadow:0 0 0 1px ${COLORS.favoriteBorder}40;`;
                } else {
                    borderStyle = `border:1px solid transparent;`;
                }

                item.style.cssText = `
                    display:flex;align-items:center;gap:12px;
                    padding:8px 12px;background:${COLORS.listItemBg};
                    border-radius:4px;cursor:pointer;
                    transition:all 0.2s;position:relative;
                    ${!isEnabled ? "opacity:0.6;filter:grayscale(0.5);" : ""}
                    ${isSelected && isEnabled ? `background:${COLORS.listItemActive};` : ""}
                    ${borderStyle}
                `;

                // 复选框
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.checked = selectedLoras.has(lora);
                checkbox.style.cssText = "accent-color: #6c5ce7;";

                // LoRA名称
                const name = document.createElement("span");
                name.textContent = lora.split('/').pop().split('\\').pop();
                name.style.cssText = `color:${COLORS.text};font-size:12px;flex:1;`;

                // 文件路径
                const path = document.createElement("span");
                path.textContent = lora;
                path.style.cssText = `color:${COLORS.textDim};font-size:11px;flex:2;`;

                // 收藏按钮
                const favBtn = document.createElement("div");
                favBtn.style.cssText = `
                    width:24px;height:24px;border-radius:50%;
                    display:flex;align-items:center;justify-content:center;
                    cursor:pointer;font-size:14px;
                    transition:all 0.2s;flex-shrink:0;
                    color:${isFavorited ? COLORS.favoriteActive : COLORS.textDim};
                    background:${isFavorited ? "rgba(255,107,107,0.1)" : "transparent"};
                `;
                favBtn.textContent = isFavorited ? "♥" : "♡";
                favBtn.title = isFavorited ? "取消收藏" : "收藏";
                favBtn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    await toggleFavorite(lora);
                });
                favBtn.addEventListener("mouseenter", () => {
                    favBtn.style.transform = "scale(1.15)";
                });
                favBtn.addEventListener("mouseleave", () => {
                    favBtn.style.transform = "scale(1)";
                });

                // 权重控制（如果已选中）
                let weightControls = null;
                if (selectedLoras.has(lora)) {
                    weightControls = document.createElement("div");
                    weightControls.style.cssText = "display:flex;align-items:center;gap:8px;";

                    const mLabel = document.createElement("span");
                    mLabel.textContent = "M:";
                    mLabel.style.cssText = `color:${COLORS.textDim};font-size:11px;`;

                    const mInput = document.createElement("input");
                    mInput.type = "number";
                    mInput.value = selectedLoras.get(lora).strength_model;
                    mInput.min = -10;
                    mInput.max = 10;
                    mInput.step = 0.1;
                    mInput.style.cssText = `
                        width:50px;padding:2px 4px;background:${COLORS.inputBg};
                        border:1px solid ${COLORS.border};border-radius:3px;
                        color:${COLORS.text};font-size:11px;text-align:center;
                    `;
                    mInput.addEventListener("change", () => {
                        selectedLoras.get(lora).strength_model = parseFloat(mInput.value);
                    });

                    const cLabel = document.createElement("span");
                    cLabel.textContent = "C:";
                    cLabel.style.cssText = `color:${COLORS.textDim};font-size:11px;`;

                    const cInput = document.createElement("input");
                    cInput.type = "number";
                    cInput.value = selectedLoras.get(lora).strength_clip;
                    cInput.min = -10;
                    cInput.max = 10;
                    cInput.step = 0.1;
                    cInput.style.cssText = `
                        width:50px;padding:2px 4px;background:${COLORS.inputBg};
                        border:1px solid ${COLORS.border};border-radius:3px;
                        color:${COLORS.text};font-size:11px;text-align:center;
                    `;
                    cInput.addEventListener("change", () => {
                        selectedLoras.get(lora).strength_clip = parseFloat(cInput.value);
                    });

                    weightControls.appendChild(mLabel);
                    weightControls.appendChild(mInput);
                    weightControls.appendChild(cLabel);
                    weightControls.appendChild(cInput);
                }

                item.appendChild(checkbox);
                item.appendChild(name);
                item.appendChild(path);
                item.appendChild(favBtn);

                // 已选中时显示删除按钮和启用开关
                if (isSelected) {
                    // 启用/禁用开关
                    const toggleSwitch = document.createElement("div");
                    toggleSwitch.style.cssText = `
                        width:32px;height:16px;border-radius:8px;flex-shrink:0;
                        background:${isEnabled ? COLORS.success : COLORS.disabled};
                        position:relative;cursor:pointer;transition:all 0.2s;
                    `;
                    const toggleDot = document.createElement("div");
                    toggleDot.style.cssText = `
                        width:12px;height:12px;border-radius:50%;
                        background:white;position:absolute;top:2px;
                        transition:all 0.2s;
                        ${isEnabled ? "left:18px;" : "left:2px;"}
                    `;
                    toggleSwitch.appendChild(toggleDot);
                    toggleSwitch.title = isEnabled ? "点击禁用" : "点击启用";
                    toggleSwitch.addEventListener("click", (e) => {
                        e.stopPropagation();
                        const config = selectedLoras.get(lora);
                        if (config) {
                            config.enabled = !config.enabled;
                            renderLoraList();
                        }
                    });
                    item.appendChild(toggleSwitch);

                    // 删除按钮
                    const deleteBtn = document.createElement("div");
                    deleteBtn.style.cssText = `
                        width:20px;height:20px;border-radius:50%;flex-shrink:0;
                        display:flex;align-items:center;justify-content:center;
                        cursor:pointer;font-size:12px;font-weight:bold;
                        background:rgba(255,107,107,0.7);
                        color:white;transition:all 0.2s;
                    `;
                    deleteBtn.textContent = "×";
                    deleteBtn.title = "移除选中";
                    deleteBtn.addEventListener("click", (e) => {
                        e.stopPropagation();
                        selectedLoras.delete(lora);
                        updateSelectedCount();
                        renderLoraList();
                    });
                    deleteBtn.addEventListener("mouseenter", () => {
                        deleteBtn.style.background = "rgba(255,107,107,1)";
                    });
                    deleteBtn.addEventListener("mouseleave", () => {
                        deleteBtn.style.background = "rgba(255,107,107,0.7)";
                    });
                    item.appendChild(deleteBtn);
                }

                if (weightControls) item.appendChild(weightControls);

                item.addEventListener("click", (e) => {
                    if (e.target.tagName === "INPUT") return;
                    if (!selectedLoras.has(lora)) {
                        selectedLoras.set(lora, {
                            strength_model: 1.0,
                            strength_clip: 1.0,
                            enabled: true
                        });
                    }
                    updateSelectedCount();
                    renderLoraList();
                });

                list.appendChild(item);
            });

            mainContent.appendChild(list);
        }
    }

    // ========== 更新选中计数 ==========
    function updateSelectedCount() {
        selectedCount.textContent = `已选择: ${selectedLoras.size} 个LoRA`;
    }

    // ========== 应用选中的LoRA ==========
    function applySelectedLoras() {
        const data = [];
        selectedLoras.forEach((config, name) => {
            data.push({
                name: name,
                strength_model: config.strength_model,
                strength_clip: config.strength_clip,
                enabled: config.enabled
            });
        });

        // 更新节点数据
        const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
        if (loraDataWidget) {
            loraDataWidget.value = JSON.stringify(data);
        }

        // 更新显示区域
        if (node._updateVisualLoraDisplay) {
            node._updateVisualLoraDisplay();
        }
        
        // 触发节点重绘
        if (node._triggerVisualLoraResize) {
            node._triggerVisualLoraResize();
        }
    }

    // ========== 预设管理 ==========
    function openPresetsModal(node) {
        // 传递回调函数，在导入预设后关闭主模态框
        createPresetsModal(node, () => {
            closeModal();
        });
    }

    // ========== 初始化 ==========
    loadFavorites().then(() => {
        renderFolderTree();
        filteredLoras = getLorasInFolder("/");
        renderLoraList();
        updateSelectedCount();
    });

    // 设置单例
    currentModal = modal;
    modal.focus = () => {
        overlay.style.display = "flex";
    };
}

// ========== 注册扩展 ==========

app.registerExtension({
    name: "naiba.VisualLoraLoader",

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "VisualLoRALoader") return;

        // 获取Lora文件列表
        let loraList = [];
        try {
            const resp = await api.fetchApi("/object_info/LoraLoader");
            const info = await resp.json();
            if (info.LoraLoader?.input?.required?.lora_name) {
                loraList = info.LoraLoader.input.required.lora_name[0] || [];
            }
        } catch (e) {
            console.warn("[VisualLoraLoader] Cannot fetch Lora list:", e);
        }

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            const node = this;
            node._visualLoraUIInitialized = false;

            // 查找 lora_data 控件
            const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
            
            // 如果找到了，确保隐藏它
            if (loraDataWidget) {
                loraDataWidget.hidden = true;
                if (loraDataWidget.inputEl) loraDataWidget.inputEl.style.display = "none";
                if (loraDataWidget.element) loraDataWidget.element.style.display = "none";
            }

            // 序列化
            node._serializeVisualLoraData = function () {
                // 这个函数在模态框中调用时会更新lora_data
            };

            // 反序列化
            node._deserializeVisualLoraData = function () {
                if (!loraDataWidget) return [];
                try { return JSON.parse(loraDataWidget.value || "[]"); }
                catch { return []; }
            };

            // 创建按钮行
            const buttonRow = document.createElement("div");
            buttonRow.style.cssText = "display:flex;gap:8px;width:100%;";

            // 创建打开弹窗的按钮
            const openBtn = document.createElement("button");
            openBtn.textContent = "打开 LoRA 选择器";
            openBtn.style.cssText = `
                flex:1;padding:10px;margin:8px 0;
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
                createVisualLoraModal(node, loraList);
            });

            // 创建一键清除按钮
            const clearBtn = document.createElement("button");
            clearBtn.textContent = "清除";
            clearBtn.style.cssText = `
                padding:10px 16px;margin:8px 0;
                background:${COLORS.danger};color:white;
                border:none;border-radius:6px;cursor:pointer;
                font-size:13px;font-weight:500;
                transition:background 0.2s;
            `;
            clearBtn.addEventListener("mouseenter", () => {
                clearBtn.style.background = COLORS.dangerHover;
            });
            clearBtn.addEventListener("mouseleave", () => {
                clearBtn.style.background = COLORS.danger;
            });
            clearBtn.addEventListener("click", () => {
                // 清除所有选择
                const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
                if (loraDataWidget) {
                    loraDataWidget.value = "[]";
                }
                // 更新显示区域
                if (node._updateVisualLoraDisplay) {
                    node._updateVisualLoraDisplay();
                }
                // 触发节点重绘
                if (node._triggerVisualLoraResize) {
                    node._triggerVisualLoraResize();
                }
            });

            buttonRow.appendChild(openBtn);
            buttonRow.appendChild(clearBtn);

            // 创建显示区域，显示已选择的LoRA信息
            const displayArea = document.createElement("div");
            displayArea.style.cssText = `
                width:100%;padding:8px;margin:4px 0;
                background:${COLORS.inputBg};border:1px solid ${COLORS.border};
                border-radius:4px;font-size:12px;color:${COLORS.text};
                min-height:40px;max-height:200px;overflow-y:auto;box-sizing:border-box;
                overflow-x:hidden;flex-shrink:1;
            `;
            displayArea.innerHTML = "<div style='color:#888;'>未选择任何LoRA</div>";

            // 更新显示区域的函数 - 附加到节点对象上，以便在模态框中调用
            const updateDisplayArea = () => {
                const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
                if (!loraDataWidget) return;
                
                try {
                    const data = JSON.parse(loraDataWidget.value || "[]");
                    if (data.length === 0) {
                        displayArea.innerHTML = "<div style='color:#888;'>未选择任何LoRA</div>";
                    } else {
                        let html = `<div style="margin-bottom:4px;font-weight:600;">已选择 ${data.length} 个LoRA:</div>`;
                        data.forEach((lora, index) => {
                            const isEnabled = lora.enabled !== false;
                            const textColor = isEnabled ? "#e0e0e0" : "#666";
                            html += `<div style="margin:2px 0;font-size:11px;color:${textColor};">
                                ${lora.name} 
                                <span style="color:#888;">(M:${lora.strength_model} C:${lora.strength_clip})</span>
                            </div>`;
                        });
                        displayArea.innerHTML = html;
                    }
                } catch (e) {
                    displayArea.innerHTML = "<div style='color:#888;'>解析中...</div>";
                }
            };
            
            // 将updateDisplayArea附加到节点对象上，以便在模态框中调用
            node._updateVisualLoraDisplay = updateDisplayArea;

            // 创建容器
            const container = document.createElement("div");
            container.style.cssText = "display:flex;flex-direction:column;gap:4px;width:100%;box-sizing:border-box;overflow:hidden;";
            container.appendChild(buttonRow);
            container.appendChild(displayArea);

            // 节点尺寸自适应
            node.onResize = function () {
                let [w, h] = node.size;
                
                // 更新容器宽度以适应节点宽度
                const nodePadding = 10;
                const containerWidth = Math.max(200, w - nodePadding * 2);
                container.style.width = containerWidth + "px";
                container.style.maxWidth = containerWidth + "px";
                
                // 计算其他widget的总高度
                let otherWidgetsHeight = 0;
                if (node.widgets) {
                    for (const widget of node.widgets) {
                        if (widget.name === "visual_lora_container") continue;
                        otherWidgetsHeight += (widget.computeSize ? widget.computeSize(w)[1] : 26) + 4;
                    }
                }
                
                // 计算可用高度，确保容器不会超出节点边界
                const availableHeight = Math.max(120, h - otherWidgetsHeight - 20);
                container.style.height = availableHeight + "px";
                
                // 计算 displayArea 的最大高度
                // buttonRow 大约 60px 高度，加上间距
                const buttonRowHeight = 60;
                const gapHeight = 8;
                const maxDisplayHeight = Math.max(40, availableHeight - buttonRowHeight - gapHeight);
                displayArea.style.maxHeight = maxDisplayHeight + "px";
            };

            // 触发节点重绘 - 附加到节点对象上
            const triggerResize = () => {
                setTimeout(() => {
                    node.onResize?.();
                    node.graph?.setDirtyCanvas(true, true);
                }, 50);
            };
            node._triggerVisualLoraResize = triggerResize;

            // 注册DOM控件
            node.addDOMWidget("visual_lora_container", "VISUAL_LORA_CONTAINER", container, {
                getValue() { return ""; },
                setValue() {},
            });

            node.minWidth = 250;
            node.minHeight = 100;

            // ========== 初始化恢复数据 ==========
            setTimeout(() => {
                if (node._visualLoraUIInitialized) return;
                node._visualLoraUIInitialized = true;

                const saved = node._deserializeVisualLoraData();
                updateDisplayArea();
                triggerResize();
            }, 150);
        };
    },
});