/**
 * Anima Prompt Node - 前端扩展
 * 交互式提示词选择器，支持分类选择、搜索和扭蛋功能
 * UI风格参考naiba_tag_picker.js
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ========== 配置 ==========
const COLORS = {
    modalBg: "#1a1a2e",
    headerBg: "#16213e",
    panelBg: "#0f3460",
    inputBg: "#1a1a2e",
    text: "#e0e0e0",
    textDim: "#a0a0a0",
    accent: "#e94560",
    accentDim: "#e9456088",
    border: "#333",
    tagBg: "#2a2a4a",
    tagBgHover: "#3a3a5a",
    tagSelected: "#4a3a6a",
    success: "#4CAF50",
    warning: "#FF9800",
    error: "#f44336",
};

const PAGE_SIZE = 20;
const MAX_SELECTED = 50;

// ========== 状态 ==========
let currentModal = null;
let nodeRef = null;
let currentTab = "全库标签";
let searchQuery = "";
let currentPage = 1;
let selectionData = {};
let gachaData = {};
let categories = [];
let tagsData = {};
let lastUsedTag = null;

// ========== 工具函数 ==========
function el(tag, props = {}, ...children) {
    const e = document.createElement(tag);
    for (const k in props) {
        if (k === "style") e.style.cssText = props[k];
        else if (k === "class") e.className = props[k];
        else if (k.startsWith("on") && typeof props[k] === "function") e.addEventListener(k.slice(2), props[k]);
        else if (k === "html") e.innerHTML = props[k];
        else e.setAttribute(k, props[k]);
    }
    for (const c of children) {
        if (c == null) continue;
        e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return e;
}

function getWidget(node, name, def) {
    const w = node?.widgets?.find((x) => x.name === name);
    return w ? w.value : def;
}

function setWidget(node, name, value) {
    const w = node?.widgets?.find((x) => x.name === name);
    if (w) w.value = value;
}

// ========== API调用 ==========
async function fetchCategories() {
    try {
        const response = await api.fetchApi("/anima/prompt/categories");
        if (response.ok) {
            const data = await response.json();
            categories = data.categories || [];
            return categories;
        }
    } catch (error) {
        console.error("获取分类失败:", error);
    }
    return [];
}

async function fetchTags(category, query = "", page = 1) {
    try {
        const params = new URLSearchParams({
            category: category,
            query: query,
            page: page.toString()
        });
        const response = await api.fetchApi(`/anima/prompt/tags?${params}`);
        if (response.ok) {
            const data = await response.json();
            return data;
        }
    } catch (error) {
        console.error("获取标签失败:", error);
    }
    return { items: [], total: 0, page: 1, total_pages: 1 };
}

async function fetchGacha(category, count = 1) {
    try {
        const params = new URLSearchParams({
            category: category,
            count: count.toString()
        });
        const response = await api.fetchApi(`/anima/prompt/gacha?${params}`);
        if (response.ok) {
            const data = await response.json();
            return data.tags || [];
        }
    } catch (error) {
        console.error("扭蛋失败:", error);
    }
    return [];
}

// ========== 状态管理 ==========
function parseSelectionData(raw) {
    try {
        const v = JSON.parse(raw);
        if (v && typeof v === "object") return v;
    } catch (e) {}
    return {};
}

function parseGachaData(raw) {
    try {
        const v = JSON.parse(raw);
        if (v && typeof v === "object") return v;
    } catch (e) {}
    return {};
}

function serializeSelectionData() {
    setWidget(nodeRef, "selection_data", JSON.stringify(selectionData));
}

function serializeGachaData() {
    setWidget(nodeRef, "gacha_data", JSON.stringify(gachaData));
}

function selectTag(tagItem) {
    if (!tagItem || !tagItem.raw_en) return;
    const key = tagItem.raw_en;
    const category = currentTab;
    
    if (!selectionData[category]) {
        selectionData[category] = [];
    }
    
    const index = selectionData[category].findIndex(item => item.tag === key);
    if (index >= 0) {
        // 已选中，移除
        selectionData[category].splice(index, 1);
        if (selectionData[category].length === 0) {
            delete selectionData[category];
        }
    } else {
        // 未选中，添加
        if (Object.values(selectionData).flat().length >= MAX_SELECTED) {
            showToast("已达上限 " + MAX_SELECTED);
            return;
        }
        selectionData[category].push({ tag: key, category: category });
    }
    
    lastUsedTag = key;
    serializeSelectionData();
    renderSelectedTags();
    renderTagList();
    renderOutputPreview();
}

function removeSelectedTag(category, tag) {
    if (selectionData[category]) {
        selectionData[category] = selectionData[category].filter(item => item.tag !== tag);
        if (selectionData[category].length === 0) {
            delete selectionData[category];
        }
        serializeSelectionData();
        renderSelectedTags();
        renderTagList();
        renderOutputPreview();
    }
}

function clearAllSelections() {
    selectionData = {};
    gachaData = {};
    serializeSelectionData();
    serializeGachaData();
    renderSelectedTags();
    renderTagList();
    renderOutputPreview();
    renderGachaResults();
    showToast("已清空所有选择");
}

function showToast(message) {
    if (!currentModal) return;
    let toast = currentModal.querySelector(".ap-toast");
    if (!toast) {
        toast = el("div", { class: "ap-toast" });
        currentModal.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2000);
}

// ========== 渲染函数 ==========
async function renderTagList() {
    const mainContent = currentModal?.querySelector(".ap-main-content");
    if (!mainContent) return;
    
    mainContent.innerHTML = "";
    
    // 加载标签
    const data = await fetchTags(currentTab, searchQuery, currentPage);
    const tags = data.items || [];
    
    if (tags.length === 0) {
        mainContent.innerHTML = `<div class="ap-empty">暂无标签</div>`;
        return;
    }
    
    const grid = el("div", { class: "ap-grid" });
    
    tags.forEach(tagItem => {
        const isSelected = selectionData[currentTab]?.some(item => item.tag === tagItem.raw_en) || false;
        const card = el("div", { 
            class: `ap-card ${isSelected ? "selected" : ""}`,
            onclick: () => selectTag(tagItem)
        },
            el("div", { class: "ap-card-header" },
                el("div", { class: "ap-card-en" }, tagItem.raw_en),
                el("div", { class: `ap-card-check ${isSelected ? "active" : ""}` }, "✓")
            ),
            el("div", { class: "ap-card-cn" }, tagItem.cn_description || ""),
            el("div", { class: "ap-card-raw" }, tagItem.raw_en || "")
        );
        grid.appendChild(card);
    });
    
    mainContent.appendChild(grid);
    
    // 渲染分页
    renderPagination(data.total_pages || 1);
}

function renderPagination(totalPages) {
    const pagination = currentModal?.querySelector(".ap-pagination");
    if (!pagination) return;
    
    pagination.innerHTML = "";
    
    if (totalPages <= 1) return;
    
    // 上一页
    const prevBtn = el("button", { 
        class: `ap-page-btn ${currentPage <= 1 ? "disabled" : ""}`,
        onclick: () => { if (currentPage > 1) { currentPage--; renderTagList(); } }
    }, "‹");
    pagination.appendChild(prevBtn);
    
    // 页码
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
            const pageBtn = el("button", {
                class: `ap-page-btn ${i === currentPage ? "active" : ""}`,
                onclick: () => { currentPage = i; renderTagList(); }
            }, i.toString());
            pagination.appendChild(pageBtn);
        } else if (i === currentPage - 3 || i === currentPage + 3) {
            pagination.appendChild(el("span", { class: "ap-page-ellipsis" }, "..."));
        }
    }
    
    // 下一页
    const nextBtn = el("button", {
        class: `ap-page-btn ${currentPage >= totalPages ? "disabled" : ""}`,
        onclick: () => { if (currentPage < totalPages) { currentPage++; renderTagList(); } }
    }, "›");
    pagination.appendChild(nextBtn);
}

function renderSelectedTags() {
    const selectedArea = currentModal?.querySelector(".ap-selected-area");
    if (!selectedArea) return;
    
    selectedArea.innerHTML = "";
    
    const allSelected = Object.entries(selectionData).flatMap(([category, tags]) => 
        tags.map(item => ({ ...item, category }))
    );
    
    if (allSelected.length === 0) {
        selectedArea.innerHTML = `<div class="ap-empty">未选择标签</div>`;
        return;
    }
    
    allSelected.forEach(item => {
        const tag = el("div", { class: "ap-selected-tag" },
            el("span", { class: "ap-selected-tag-text" }, item.tag),
            el("span", { 
                class: "ap-selected-tag-remove",
                onclick: (e) => { e.stopPropagation(); removeSelectedTag(item.category, item.tag); }
            }, "×")
        );
        selectedArea.appendChild(tag);
    });
}

function renderGachaResults() {
    const gachaArea = currentModal?.querySelector(".ap-gacha-area");
    if (!gachaArea) return;
    
    gachaArea.innerHTML = "";
    
    const allGacha = Object.entries(gachaData).flatMap(([category, tags]) => 
        tags.map(item => ({ ...item, category }))
    );
    
    if (allGacha.length === 0) {
        gachaArea.innerHTML = `<div class="ap-empty">未扭蛋</div>`;
        return;
    }
    
    allGacha.forEach(item => {
        const tag = el("div", { class: "ap-gacha-tag" },
            el("span", { class: "ap-gacha-tag-text" }, item.raw_en || item.tag),
            el("span", { class: "ap-gacha-tag-cat" }, item.category)
        );
        gachaArea.appendChild(tag);
    });
}

function renderOutputPreview() {
    const outputPreview = currentModal?.querySelector(".ap-output-preview");
    if (!outputPreview) return;
    
    const allTags = Object.values(selectionData).flat().map(item => item.tag);
    const allGacha = Object.values(gachaData).flat().map(item => item.raw_en || item.tag);
    const allUnique = [...new Set([...allTags, ...allGacha])];
    
    if (allUnique.length === 0) {
        outputPreview.innerHTML = `<div class="ap-empty">暂无输出</div>`;
        return;
    }
    
    outputPreview.innerHTML = `<div class="ap-output-text">${allUnique.join(", ")}</div>`;
}

// ========== 扭蛋功能 ==========
async function handleGacha() {
    const gachaCount = currentModal?.querySelector(".ap-gacha-count")?.value || 3;
    const count = Math.max(1, Math.min(10, parseInt(gachaCount) || 3));
    
    showToast(`扭蛋中... (${count}个)`);
    
    const gachaTags = await fetchGacha(currentTab, count);
    
    if (gachaTags.length > 0) {
        gachaData[currentTab] = gachaTags;
        serializeGachaData();
        renderGachaResults();
        renderOutputPreview();
        showToast(`扭蛋成功！获得 ${gachaTags.length} 个标签`);
    } else {
        showToast("扭蛋失败，请重试");
    }
}

// ========== 模态框创建 ==========
function createAnimaPromptModal(node) {
    if (currentModal) { currentModal.focus(); return; }
    
    const overlay = el("div", { class: "ap-overlay" });
    const modal = el("div", { class: "ap-modal" });
    
    // 标题栏
    const header = el("div", { class: "ap-header" },
        el("div", { class: "ap-title" }, "⚓ Anima Prompt Selector"),
        el("div", { class: "ap-close", onclick: () => closeModal() }, "✕"),
    );
    
    // 主体：左侧选择区 + 右侧预览区
    const body = el("div", { class: "ap-body" });
    
    // 左侧：选择区
    const leftPanel = el("div", { class: "ap-left" });
    
    // 分类标签页
    const tabBar = el("div", { class: "ap-tabs" });
    leftPanel.appendChild(tabBar);
    
    // 工具栏
    const toolbar = el("div", { class: "ap-toolbar" },
        el("input", { 
            class: "ap-search", 
            type: "text", 
            placeholder: "搜索标签...",
            onkeydown: (e) => { if (e.key === "Enter") handleSearch(); }
        }),
        el("button", { class: "ap-btn", onclick: handleSearch }, "搜索"),
        el("button", { class: "ap-btn", onclick: () => { searchQuery = ""; currentModal.querySelector(".ap-search").value = ""; currentPage = 1; renderTagList(); } }, "重置"),
        el("div", { class: "ap-gacha-group" },
            el("input", { 
                class: "ap-gacha-count", 
                type: "number", 
                min: "1", 
                max: "10", 
                value: "3",
                title: "扭蛋数量"
            }),
            el("button", { class: "ap-btn ap-gacha-btn", onclick: handleGacha }, "🎰 扭蛋")
        )
    );
    leftPanel.appendChild(toolbar);
    
    // 主内容区
    const mainContent = el("div", { class: "ap-main-content" });
    leftPanel.appendChild(mainContent);
    
    // 分页
    const pagination = el("div", { class: "ap-pagination" });
    leftPanel.appendChild(pagination);
    
    // 右侧：预览区
    const rightPanel = el("div", { class: "ap-right" });
    
    // 已选标签区
    const selectedSection = el("div", { class: "ap-section" },
        el("div", { class: "ap-section-header" },
            el("div", { class: "ap-section-title" }, "已选标签"),
            el("button", { class: "ap-btn ap-btn-sm", onclick: clearAllSelections }, "清空")
        ),
        el("div", { class: "ap-selected-area ap-scrollable" })
    );
    rightPanel.appendChild(selectedSection);
    
    // 扭蛋结果区
    const gachaSection = el("div", { class: "ap-section" },
        el("div", { class: "ap-section-header" },
            el("div", { class: "ap-section-title" }, "扭蛋结果")
        ),
        el("div", { class: "ap-gacha-area ap-scrollable" })
    );
    rightPanel.appendChild(gachaSection);
    
    // 输出预览区
    const outputSection = el("div", { class: "ap-section" },
        el("div", { class: "ap-section-header" },
            el("div", { class: "ap-section-title" }, "输出预览")
        ),
        el("div", { class: "ap-output-preview ap-scrollable" })
    );
    rightPanel.appendChild(outputSection);
    
    body.append(leftPanel, rightPanel);
    
    // 底部按钮
    const footer = el("div", { class: "ap-footer" },
        el("button", { class: "ap-btn ap-btn-primary", onclick: () => { 
            serializeSelectionData(); 
            serializeGachaData(); 
            closeModal(); 
            showToast("已应用选择");
        } }, "应用"),
        el("button", { class: "ap-btn", onclick: closeModal }, "取消")
    );
    
    modal.append(header, body, footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    currentModal = overlay;
    
    // 初始化分类标签
    initCategories(tabBar);
    
    // 恢复状态
    restoreFromNode(node);
    
    // 注入样式
    injectStyle();
    
    // 渲染初始内容
    renderSelectedTags();
    renderGachaResults();
    renderOutputPreview();
}

async function initCategories(tabBar) {
    if (categories.length === 0) {
        await fetchCategories();
    }
    
    tabBar.innerHTML = "";
    categories.forEach(cat => {
        const tab = el("div", { 
            class: `ap-tab ${cat === currentTab ? "active" : ""}`,
            onclick: () => switchTab(cat, tabBar)
        }, cat);
        tabBar.appendChild(tab);
    });
}

function switchTab(tab, tabBar) {
    currentTab = tab;
    currentPage = 1;
    searchQuery = "";
    
    // 更新标签页状态
    if (tabBar) {
        tabBar.querySelectorAll(".ap-tab").forEach(t => {
            t.classList.toggle("active", t.textContent === tab);
        });
    }
    
    // 更新搜索框
    const searchInput = currentModal?.querySelector(".ap-search");
    if (searchInput) searchInput.value = "";
    
    // 渲染标签列表
    renderTagList();
}

function handleSearch() {
    const searchInput = currentModal?.querySelector(".ap-search");
    if (searchInput) {
        searchQuery = searchInput.value.trim();
        currentPage = 1;
        renderTagList();
    }
}

function restoreFromNode(node) {
    const selData = getWidget(node, "selection_data", "{}");
    const gachaDataStr = getWidget(node, "gacha_data", "{}");
    
    selectionData = parseSelectionData(selData);
    gachaData = parseGachaData(gachaDataStr);
}

function closeModal() {
    if (currentModal) {
        currentModal.remove();
        currentModal = null;
    }
}

// ========== 样式注入 ==========
function injectStyle() {
    if (document.getElementById("ap-style")) return;
    const css = `
.ap-overlay{position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:10000;display:flex;align-items:center;justify-content:center;}
.ap-modal{width:95vw;max-width:1400px;height:90vh;background:${COLORS.modalBg};border-radius:12px;border:1px solid ${COLORS.border};display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.7);}
.ap-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};}
.ap-title{color:${COLORS.text};font-size:18px;font-weight:700;}
.ap-close{color:${COLORS.textDim};cursor:pointer;font-size:20px;padding:6px 10px;border-radius:6px;transition:.2s;}
.ap-close:hover{color:${COLORS.text};background:rgba(255,255,255,.15);}
.ap-body{display:flex;flex:1;overflow:hidden;}
.ap-left{flex:3;display:flex;flex-direction:column;border-right:1px solid ${COLORS.border};}
.ap-right{flex:1;display:flex;flex-direction:column;padding:12px;background:${COLORS.panelBg};}
.ap-tabs{display:flex;gap:2px;padding:12px 16px 0;background:${COLORS.headerBg};flex-wrap:wrap;}
.ap-tab{padding:8px 16px;border-radius:6px 6px 0 0;cursor:pointer;font-size:13px;color:${COLORS.textDim};transition:.2s;background:${COLORS.inputBg};}
.ap-tab:hover{color:${COLORS.text};background:${COLORS.panelBg};}
.ap-tab.active{color:${COLORS.text};background:${COLORS.accent};font-weight:600;}
.ap-toolbar{display:flex;align-items:center;gap:8px;padding:12px 16px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};border-bottom:1px solid ${COLORS.border};flex-wrap:wrap;}
.ap-search{flex:1;min-width:200px;padding:8px 12px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:6px;color:${COLORS.text};font-size:13px;}
.ap-search:focus{outline:none;border-color:${COLORS.accent};}
.ap-btn{padding:8px 16px;background:${COLORS.panelBg};border:1px solid ${COLORS.border};border-radius:6px;color:${COLORS.text};cursor:pointer;font-size:13px;transition:.2s;}
.ap-btn:hover{background:${COLORS.headerBg};border-color:${COLORS.accent};}
.ap-btn-primary{background:${COLORS.accent};border-color:${COLORS.accent};font-weight:600;}
.ap-btn-primary:hover{background:#d63851;}
.ap-btn-sm{padding:4px 10px;font-size:12px;}
.ap-gacha-group{display:flex;align-items:center;gap:6px;}
.ap-gacha-count{width:50px;padding:8px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:6px;color:${COLORS.text};font-size:13px;text-align:center;}
.ap-gacha-btn{background:${COLORS.accent};border-color:${COLORS.accent};font-weight:600;}
.ap-gacha-btn:hover{background:#d63851;}
.ap-main-content{flex:1;overflow-y:auto;padding:12px;}
.ap-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;}
.ap-card{background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:8px;padding:12px;cursor:pointer;transition:.2s;}
.ap-card:hover{background:${COLORS.tagBgHover};border-color:${COLORS.accentDim};transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.3);}
.ap-card.selected{background:${COLORS.tagSelected};border-color:${COLORS.accent};}
.ap-card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;}
.ap-card-en{font-size:14px;font-weight:600;color:${COLORS.text};word-break:break-word;}
.ap-card-check{width:20px;height:20px;border-radius:50%;border:2px solid ${COLORS.border};display:flex;align-items:center;justify-content:center;font-size:12px;color:transparent;transition:.2s;}
.ap-card-check.active{background:${COLORS.accent};border-color:${COLORS.accent};color:white;}
.ap-card-cn{font-size:12px;color:${COLORS.textDim};margin-bottom:6px;line-height:1.4;}
.ap-card-raw{font-size:11px;color:${COLORS.textDim};opacity:.7;font-family:monospace;}
.ap-pagination{display:flex;justify-content:center;align-items:center;gap:6px;padding:12px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};}
.ap-page-btn{padding:6px 12px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:4px;color:${COLORS.text};cursor:pointer;font-size:12px;transition:.2s;}
.ap-page-btn:hover:not(.disabled){background:${COLORS.panelBg};border-color:${COLORS.accent};}
.ap-page-btn.active{background:${COLORS.accent};border-color:${COLORS.accent};font-weight:600;}
.ap-page-btn.disabled{opacity:.5;cursor:not-allowed;}
.ap-page-ellipsis{color:${COLORS.textDim};font-size:12px;}
.ap-section{margin-bottom:12px;}
.ap-section-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
.ap-section-title{font-size:14px;font-weight:600;color:${COLORS.text};}
.ap-scrollable{max-height:200px;overflow-y:auto;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:6px;padding:8px;}
.ap-selected-area,.ap-gacha-area{display:flex;flex-wrap:wrap;gap:6px;}
.ap-selected-tag{display:flex;align-items:center;gap:4px;background:${COLORS.tagBg};border:1px solid ${COLORS.border};border-radius:4px;padding:4px 8px;font-size:12px;color:${COLORS.text};}
.ap-selected-tag-text{max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.ap-selected-tag-remove{color:${COLORS.textDim};cursor:pointer;font-size:14px;padding:0 2px;transition:.2s;}
.ap-selected-tag-remove:hover{color:${COLORS.error};}
.ap-gacha-tag{display:flex;flex-direction:column;background:${COLORS.tagBg};border:1px solid ${COLORS.border};border-radius:4px;padding:4px 8px;font-size:12px;color:${COLORS.text};}
.ap-gacha-tag-cat{font-size:10px;color:${COLORS.textDim};}
.ap-output-preview{background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:6px;padding:10px;min-height:60px;}
.ap-output-text{font-size:13px;color:${COLORS.text};line-height:1.5;word-break:break-word;}
.ap-empty{color:${COLORS.textDim};font-size:13px;text-align:center;padding:20px;font-style:italic;}
.ap-footer{display:flex;justify-content:flex-end;gap:10px;padding:16px 20px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};}
.ap-toast{position:absolute;top:20px;left:50%;transform:translateX(-50%);background:${COLORS.accent};color:white;padding:10px 20px;border-radius:6px;font-size:13px;font-weight:600;z-index:10001;opacity:0;transition:opacity .3s;pointer-events:none;}
.ap-toast.show{opacity:1;}
`;
    
    const style = document.createElement("style");
    style.id = "ap-style";
    style.textContent = css;
    document.head.appendChild(style);
}

// ========== 节点注册 ==========
app.registerExtension({
    name: "Comfy.AnimaPromptNode",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "AnimaPromptNode") {
            // 保存原始的onNodeCreated
            const origOnNodeCreated = nodeType.prototype.onNodeCreated;
            
            nodeType.prototype.onNodeCreated = function () {
                origOnNodeCreated?.apply(this, arguments);
                const node = this;
                
                // 创建打开按钮
                const openBtn = el("button", { 
                    class: "ap-open-btn",
                    onclick: () => {
                        nodeRef = node;
                        createAnimaPromptModal(node);
                    }
                }, "⚓ 打开选择器");
                
                // 添加按钮到节点
                node.addDOMWidget("ap_open_button", "button", openBtn);
                
                // 清除按钮
                const clearBtn = el("button", {
                    class: "ap-clear-btn",
                    onclick: () => {
                        nodeRef = node;
                        clearAllSelections();
                    }
                }, "清空选择");
                
                node.addDOMWidget("ap_clear_button", "button", clearBtn);
                
                // 输出预览
                const previewWidget = node.addDOMWidget("ap_output_preview", "preview", el("div", { class: "ap-node-preview" }));
                
                // 更新预览函数
                node._updateOutputPreview = function() {
                    const selData = getWidget(node, "selection_data", "{}");
                    const gachaDataStr = getWidget(node, "gacha_data", "{}");
                    
                    const sel = parseSelectionData(selData);
                    const gacha = parseGachaData(gachaDataStr);
                    
                    const allTags = Object.values(sel).flat().map(item => item.tag);
                    const allGacha = Object.values(gacha).flat().map(item => item.raw_en || item.tag);
                    const allUnique = [...new Set([...allTags, ...allGacha])];
                    
                    if (allUnique.length === 0) {
                        previewWidget.value = "<div class='ap-empty'>暂无选择</div>";
                    } else {
                        previewWidget.value = `<div class="ap-preview-text">${allUnique.join(", ")}</div>`;
                    }
                };
                
                // 监听widget变化
                const origOnWidgetChanged = node.onWidgetChanged;
                node.onWidgetChanged = function(name, value, old_value) {
                    origOnWidgetChanged?.apply(this, arguments);
                    if (name === "selection_data" || name === "gacha_data") {
                        this._updateOutputPreview();
                    }
                };
                
                // 初始更新
                setTimeout(() => node._updateOutputPreview(), 100);
            };
        }
    }
});

// ========== 节点样式 ==========
const nodeStyle = document.createElement("style");
nodeStyle.textContent = `
.ap-open-btn {
    width: 100%;
    padding: 8px 12px;
    background: #e94560;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    transition: background 0.2s;
    margin-bottom: 6px;
}
.ap-open-btn:hover {
    background: #d63851;
}
.ap-clear-btn {
    width: 100%;
    padding: 6px 12px;
    background: #1a1a2e;
    color: #a0a0a0;
    border: 1px solid #333;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    transition: all 0.2s;
    margin-bottom: 6px;
}
.ap-clear-btn:hover {
    background: #2a2a4a;
    color: #e0e0e0;
    border-color: #e94560;
}
.ap-node-preview {
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 8px;
    min-height: 40px;
    max-height: 100px;
    overflow-y: auto;
    font-size: 12px;
    color: #e0e0e0;
    line-height: 1.4;
}
.ap-node-preview .ap-empty {
    color: #a0a0a0;
    font-style: italic;
    text-align: center;
}
.ap-node-preview .ap-preview-text {
    word-break: break-word;
}
`;
document.head.appendChild(nodeStyle);
