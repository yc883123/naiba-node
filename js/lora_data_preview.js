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
    warning: "#ffa502",
    favorite: "#ff9f43",      // 收藏按钮颜色（橙色）
    favoriteActive: "#ff6b6b", // 已收藏颜色（红色）
    text: "#e0e0e0",
    textDim: "#888",
    border: "#2a3a5c",
    inputBg: "#0a0f1e",
    cardBg: "#16213e",
    cardBorder: "#2a3a5c",
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
    header.appendChild(headerRight);
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // ========== 工具栏 ==========
    const toolbar = document.createElement("div");
    toolbar.style.cssText = `
        display:flex;align-items:center;gap:12px;padding:8px 16px;
        background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};
    `;

    // 视图切换标签
    let currentView = "all"; // "all", "selected", 或 "favorite"
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

    const updateTabStyle = () => {
        // 重置所有标签样式
        tabAll.style.background = "transparent";
        tabAll.style.color = COLORS.textDim;
        tabSelected.style.background = "transparent";
        tabSelected.style.color = COLORS.textDim;
        tabFavorite.style.background = "transparent";
        tabFavorite.style.color = COLORS.textDim;
        
        // 设置当前活动标签样式
        if (currentView === "all") {
            tabAll.style.background = COLORS.accent;
            tabAll.style.color = "white";
        } else if (currentView === "selected") {
            tabSelected.style.background = COLORS.accent;
            tabSelected.style.color = "white";
        } else if (currentView === "favorite") {
            tabFavorite.style.background = COLORS.favorite;
            tabFavorite.style.color = "white";
        }
    };

    const updateStatusDisplay = () => {
        const searchTerm = searchInput.value.toLowerCase();
        let baseLoras = searchTerm 
            ? loraList.filter(lora => lora.toLowerCase().includes(searchTerm))
            : loraList;
        
        if (currentView === "selected") {
            const selectedCount = baseLoras.filter(l => selectedLoras.has(l)).length;
            statusDisplay.textContent = searchTerm 
                ? `已选择: ${selectedCount} 个结果` 
                : `已选择: ${selectedCount} 个LoRA`;
        } else if (currentView === "favorite") {
            const favCount = baseLoras.filter(l => favoriteLoras.has(l)).length;
            statusDisplay.textContent = searchTerm 
                ? `收藏: ${favCount} 个结果` 
                : `收藏: ${favCount} 个LoRA`;
        } else {
            statusDisplay.textContent = searchTerm 
                ? `搜索: ${baseLoras.length} 个结果` 
                : `全部: ${baseLoras.length} 个LoRA`;
        }
    };

    tabAll.addEventListener("click", () => {
        currentView = "all";
        updateTabStyle();
        updateStatusDisplay();
        renderLoraList();
    });

    tabSelected.addEventListener("click", () => {
        currentView = "selected";
        updateTabStyle();
        updateStatusDisplay();
        renderLoraList();
    });

    tabFavorite.addEventListener("click", () => {
        currentView = "favorite";
        updateTabStyle();
        updateStatusDisplay();
        renderLoraList();
    });

    tabGroup.appendChild(tabAll);
    tabGroup.appendChild(tabSelected);
    tabGroup.appendChild(tabFavorite);

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

    // ========== 内容区域 ==========
    const content = document.createElement("div");
    content.style.cssText = `
        flex:1;overflow-y:auto;padding:16px;
        background:${COLORS.contentBg};
    `;

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
    content.appendChild(progressBarContainer);

    // ========== LoRA网格 ==========
    const grid = document.createElement("div");
    grid.style.cssText = `
        display:grid;grid-template-columns:repeat(auto-fill, minmax(280px, 1fr));
        gap:12px;
    `;
    content.appendChild(grid);

    modal.appendChild(content);

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
                filteredLoras = [...loraList];
                statusDisplay.textContent = `共 ${loraList.length} 个LoRA文件`;
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
        filteredLoras.forEach(lora => selectedLoras.add(lora));
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

    // 应用按钮
    const applyBtn = document.createElement("button");
    applyBtn.textContent = "应用选中 (0)";
    applyBtn.style.cssText = `
        padding:6px 12px;background:${COLORS.success};
        color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;
    `;
    applyBtn.addEventListener("click", () => {
        applySelectedLora();
    });

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
    buttonGroup.appendChild(applyBtn);
    buttonGroup.appendChild(closeFooterBtn);

    statusBar.appendChild(syncStatus);
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

    // 从节点widget中恢复已选中的LoRA，确保重新打开弹窗时"已选择"标签能正确显示
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
        grid.innerHTML = "";
        
        // 更新应用按钮文本显示选中数量
        applyBtn.textContent = `应用选中 (${selectedLoras.size})`;
        
        // 根据视图模式过滤列表
        let displayLoras = filteredLoras;
        if (currentView === "selected") {
            displayLoras = filteredLoras.filter(lora => selectedLoras.has(lora));
        } else if (currentView === "favorite") {
            displayLoras = filteredLoras.filter(lora => favoriteLoras.has(lora));
        }
        
        if (displayLoras.length === 0) {
            const emptyMsg = document.createElement("div");
            if (currentView === "selected") {
                emptyMsg.textContent = "尚未选择任何LoRA";
            } else if (currentView === "favorite") {
                emptyMsg.textContent = "尚未收藏任何LoRA";
            } else {
                emptyMsg.textContent = "没有找到LoRA文件";
            }
            emptyMsg.style.cssText = `
                color:${COLORS.textDim};text-align:center;padding:40px;font-size:14px;
                grid-column:1/-1;
            `;
            grid.appendChild(emptyMsg);
            return;
        }

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

            // 预览图：优先使用Civitai预览图，自定义图作为fallback
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

    // ========== 显示收藏编辑面板 ==========
    async function showEditPanel(loraName) {
        // 加载自定义数据
        let customData = {};
        try {
            const detailController = new AbortController();
            const detailTimeoutId = setTimeout(() => detailController.abort(), 10000);
            const response = await fetch(`/naiba/lora/detail?name=${encodeURIComponent(loraName)}`, { signal: detailController.signal });
            clearTimeout(detailTimeoutId);
            const result = await response.json();
            if (result.success && result.custom_data) {
                customData = result.custom_data;
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
            width:500px;max-width:90vw;
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

        editContent.appendChild(promptLabel);
        editContent.appendChild(promptInput);
        editContent.appendChild(imageLabel);
        editContent.appendChild(imageUploadArea);
        editContent.appendChild(fileInput);

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