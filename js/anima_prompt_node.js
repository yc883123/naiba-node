/**
 * Anima Prompt Node - 前端画廊扩展（按 naiba_tag_picker.js 风格重写）
 * 统一状态层 + 左右分栏（左画廊 / 右结果）+ 多标签页（动态分类 + 扭蛋）
 * 数据源：本地 anima_prompts.json（分类 -> [{en_tags, cn_description, raw_en}]）
 * 序列化契约（与后端 anima_prompt_node.py 严格对齐）：
 *   selection_data = {"selected":[{tag, raw_en, category, cn}]}
 *   gacha_data     = {"tags":[{tag, raw_en, category, cn}]}
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ========== 颜色常量 ==========
const COLORS = {
    modalBg: "#1a1a2e",
    headerBg: "#16213e",
    contentBg: "#0f1729",
    accent: "#e94560",
    accentHover: "#ff5d75",
    danger: "#ff6b6b",
    success: "#2ed573",
    warning: "#ffa502",
    text: "#e0e0e0",
    textDim: "#888",
    border: "#2a3a5c",
    inputBg: "#0a0f1e",
    cardBg: "#16213e",
    cardBorder: "#2a3a5c",
};

const PAGE_SIZE = 20;
const MAX_TOTAL_SELECTED = 100;
const GACHA_TAB = "__gacha__";

let currentModal = null;

// ========== 统一状态层 ==========
const state = {
    selectedMap: new Map(),   // key(raw_en) -> {tag, raw_en, category, cn}
    categories: [],           // 动态分类
    tabState: {},             // category -> {items, page, totalPages, loading, seq, query}
    currentTab: null,
};
const gachaState = { resultTags: [], count: 3, checkedCats: [], catCounts: {} };  // [{tag, raw_en, category, cn}], count: 扭蛋数量, checkedCats: 勾选参与扭蛋的分类, catCounts: 每个分类的抽取数量 {category: number}
// 多节点状态存储：nodeId -> { state, gachaState }
const nodeStates = new Map();
let nodeRef = null;

// ========== DOM 引用 ==========
let mainScroll = null;
let pagerBar = null;
let resultPanel = null;
let tabGroupEl = null;
let tabEls = {};
let toolbarEl = null;
let searchInputEl = null;

// ========== 工具 ==========
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
function getNodeState(nodeId) {
    if (!nodeStates.has(nodeId)) {
        nodeStates.set(nodeId, {
            state: {
                selectedMap: new Map(),
                tabState: {},
                currentTab: null,
                _pendingTabPages: null,
            },
            gachaState: { resultTags: [], count: 3, checkedCats: [], catCounts: {} },
        });
    }
    return nodeStates.get(nodeId);
}

function itemKey(it) { return String(it?.raw_en || it?.tag || ""); }
function itemText(it) { return String(it?.raw_en || it?.tag || ""); }

// ========== 序列化 ==========
function serializeSelection() {
    setWidget(nodeRef, "selection_data", JSON.stringify({ selected: [...state.selectedMap.values()] }));
    serializeUIState();
}
function serializeGacha() {
    setWidget(nodeRef, "gacha_data", JSON.stringify({ tags: gachaState.resultTags }));
    serializeUIState();
}
function serializeUIState() {
    const tabPages = {};
    for (const cat in state.tabState) {
        tabPages[cat] = { page: state.tabState[cat].page || 1 };
    }
    setWidget(nodeRef, "ui_state", JSON.stringify({
        currentTab: state.currentTab,
        tabPages,
        gachaCount: gachaState.count || 3,
        gachaCats: gachaState.checkedCats || [],
        gachaCatCounts: gachaState.catCounts || {},
    }));
}

function parseSelection(raw) {
    try {
        const v = JSON.parse(raw);
        if (v && Array.isArray(v.selected)) {
            return v.selected.filter((x) => x && (x.raw_en || x.tag))
                .map((x) => ({ tag: x.tag || x.raw_en, raw_en: x.raw_en || x.tag, category: x.category || "", cn: x.cn || x.cn_description || "" }));
        }
        // 兼容旧的按分类分组结构
        if (v && typeof v === "object") {
            const out = [];
            for (const cat of Object.keys(v)) {
                (v[cat] || []).forEach((it) => {
                    if (it && (it.raw_en || it.tag)) out.push({ tag: it.tag || it.raw_en, raw_en: it.raw_en || it.tag, category: it.category || cat, cn: it.cn || it.cn_description || "" });
                });
            }
            return out;
        }
    } catch (e) { /* ignore */ }
    return [];
}
function parseGacha(raw) {
    try {
        const v = JSON.parse(raw);
        if (v && Array.isArray(v.tags)) {
            return v.tags.filter((x) => x && (x.raw_en || x.tag))
                .map((x) => ({ tag: x.tag || x.raw_en, raw_en: x.raw_en || x.tag, category: x.category || "", cn: x.cn || x.cn_description || "" }));
        }
    } catch (e) { /* ignore */ }
    return [];
}
function parseUIState(raw) {
    try {
        const v = JSON.parse(raw);
        if (v && typeof v === "object") {
            return {
                currentTab: v.currentTab || null,
                tabPages: v.tabPages || {},
                gachaCount: v.gachaCount || 3,
                gachaCats: Array.isArray(v.gachaCats) ? v.gachaCats : [],
                gachaCatCounts: (v.gachaCatCounts && typeof v.gachaCatCounts === "object") ? v.gachaCatCounts : {},
            };
        }
    } catch (e) { /* ignore */ }
    return { currentTab: null, tabPages: {}, gachaCount: 3, gachaCatCounts: {} };
}

// ========== 状态更新入口 ==========
function normItem(raw, category) {
    return {
        tag: raw.raw_en || raw.tag,
        raw_en: raw.raw_en || raw.tag,
        category: raw.category || category || "",
        cn: raw.cn_description || raw.cn || "",
    };
}
function selectTag(raw, category) {
    const it = normItem(raw, category);
    const key = itemKey(it);
    if (!key) return;
    if (state.selectedMap.has(key)) state.selectedMap.delete(key);
    else {
        if (state.selectedMap.size >= MAX_TOTAL_SELECTED) { flashStatus("已达上限 " + MAX_TOTAL_SELECTED); return; }
        state.selectedMap.set(key, it);
    }
    serializeSelection();
    renderGallerySelectionStates();
    renderResult();
}
function removeSelected(key) {
    state.selectedMap.delete(key);
    serializeSelection();
    renderGallerySelectionStates();
    renderResult();
}
function removeGacha(key) {
    gachaState.resultTags = gachaState.resultTags.filter((t) => itemKey(t) !== key);
    serializeGacha();
    renderResult();
}
function clearAll() {
    state.selectedMap.clear();
    gachaState.resultTags = [];
    serializeSelection();
    serializeGacha();
    renderGallerySelectionStates();
    renderResult();
    flashStatus("已清空所有选择");
}

// ========== 网络 ==========
async function apiGetJson(path) {
    const resp = await api.fetchApi(path);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return await resp.json();
}
const _EXCLUDED_CATEGORIES = new Set(["全库标签"]);
async function loadCategories() {
    if (state.categories.length) return state.categories;
    try {
        const data = await apiGetJson("/anima/prompt/categories");
        state.categories = (data.categories || []).filter((c) => !_EXCLUDED_CATEGORIES.has(c));
    } catch (e) {
        state.categories = [];
        flashStatus("加载分类失败：" + e.message);
    }
    return state.categories;
}
function ensureTabState(cat) {
    if (!state.tabState[cat]) state.tabState[cat] = { items: [], page: 1, totalPages: 1, loading: false, seq: 0, query: "" };
    return state.tabState[cat];
}
async function doSearch(cat) {
    const ts = ensureTabState(cat);
    ts.loading = true;
    if (state.currentTab === cat) renderGallery();
    const seq = ++ts.seq;
    const path = `/anima/prompt/tags?category=${encodeURIComponent(cat)}&query=${encodeURIComponent(ts.query)}&page=${ts.page}&page_size=${PAGE_SIZE}`;
    try {
        const data = await apiGetJson(path);
        if (seq !== ts.seq) return;
        ts.items = data.items || [];
        ts.totalPages = data.total_pages || 1;
    } catch (e) {
        if (seq !== ts.seq) return;
        ts.items = [];
        ts.totalPages = 1;
        flashStatus("加载失败：" + e.message);
    } finally {
        ts.loading = false;
        if (seq === ts.seq && state.currentTab === cat) renderGallery();
    }
}

// ========== 卡片构建 ==========
function buildGalleryCard(it, cat) {
    const key = itemKey(it);
    const isSel = state.selectedMap.has(key);
    const card = el("div", {
        class: "ap-card" + (isSel ? " selected" : ""),
        tabindex: "0",
        title: it.raw_en || "",
    });
    const header = el("div", { class: "ap-card-header" },
        el("div", { class: "ap-card-en" }, it.raw_en || ""),
        el("div", { class: "ap-card-check" + (isSel ? " active" : "") }, "✓"),
    );
    const cn = el("div", { class: "ap-card-cn" }, it.cn_description || "");
    card.append(header, cn);
    card.dataset.key = key;
    card.addEventListener("click", () => selectTag(it, cat));
    return card;
}

function buildResultCard(it, isGacha) {
    const key = itemKey(it);
    const card = el("div", { class: "ap-res-card" });
    const info = el("div", { class: "ap-res-info" },
        el("div", { class: "ap-res-name", title: it.raw_en || it.tag }, it.raw_en || it.tag),
        el("div", { class: "ap-res-cat" }, (it.cn ? it.cn + " · " : "") + (it.category || "")),
    );
    const del = el("button", {
        class: "ap-res-del", title: "移除",
        onclick: (e) => { e.stopPropagation(); isGacha ? removeGacha(key) : removeSelected(key); },
    }, "✕");
    card.append(info, del);
    return card;
}

// ========== 渲染 ==========
function renderGallery() {
    if (!mainScroll) return;
    const cat = state.currentTab;
    if (cat === GACHA_TAB) { renderGachaPanel(); return; }
    const ts = ensureTabState(cat);
    mainScroll.innerHTML = "";
    if (ts.loading) { mainScroll.appendChild(el("div", { class: "ap-empty" }, "加载中…")); updatePager(); return; }
    const items = ts.items || [];
    if (!items.length) {
        mainScroll.appendChild(el("div", { class: "ap-empty" }, ts.query ? `未找到「${ts.query}」相关标签` : "该分类暂无数据"));
        updatePager();
        return;
    }
    const grid = el("div", { class: "ap-grid" });
    items.forEach((it) => grid.appendChild(buildGalleryCard(it, cat)));
    mainScroll.appendChild(grid);
    updatePager();
}
function renderGallerySelectionStates() {
    if (!mainScroll) return;
    mainScroll.querySelectorAll(".ap-card").forEach((card) => {
        const key = card.dataset.key;
        if (key == null) return;
        const sel = state.selectedMap.has(key);
        card.classList.toggle("selected", sel);
        const chk = card.querySelector(".ap-card-check");
        if (chk) chk.classList.toggle("active", sel);
    });
}

// ========== 一键重置（分页 + 搜索，保留扭蛋） ==========
function resetAllTabs() {
    for (const cat in state.tabState) {
        const ts = state.tabState[cat];
        ts.page = 1;
        ts.totalPages = 1;
        ts.items = [];
        ts.query = "";
        ts.loading = false;
        ts.seq = 0;
    }
    if (searchInputEl) searchInputEl.value = "";
    const cur = state.currentTab;
    if (cur && cur !== GACHA_TAB) {
        doSearch(cur);
    }
    updatePager();
    flashStatus("已重置全部分页");
}

function renderGachaPanel() {
    if (!mainScroll) return;
    mainScroll.innerHTML = "";
    const wrap = el("div", { class: "ap-gacha" });
    wrap.appendChild(el("div", { class: "ap-gacha-hint", html: "为每个分类设置抽取数量。<br>· 每个分类可设置不同数量（如 A 抽 2、B 抽 3、C 抽 0）<br>· 数量为 0 表示不抽取该分类，直接输入数字即可<br>· 点击「清零」可将所有分类数量归零<br>· 点击「默认值」可将所有分类数量设为 3" }));

    // 默认值 / 清零按钮
    const defaultBtn = el("button", { class: "ap-btn small", onclick: () => {
        for (const cat of state.categories) {
            gachaState.catCounts[cat] = 3;
        }
        serializeGacha();
        renderGachaPanel();
    } }, "默认值");
    const clearBtn = el("button", { class: "ap-btn small", onclick: () => {
        for (const cat of state.categories) {
            gachaState.catCounts[cat] = 0;
        }
        serializeGacha();
        renderGachaPanel();
    } }, "清零");
    wrap.appendChild(el("div", { class: "ap-gacha-row" },
        el("div", { class: "ap-gacha-rowlabel" }, "快速操作"), defaultBtn, clearBtn,
    ));

    // 每个分类的数量输入框
    const list = el("div", { class: "ap-cat-list" });
    state.categories.forEach((c) => {
        // 数量输入框（使用 text + inputmode=numeric 保证可键盘输入）
        const cnt = el("input", { class: "ap-mini-num", type: "text", inputmode: "numeric", pattern: "[0-9]*", value: String(gachaState.catCounts[c] ?? 0) });
        cnt.style.width = "50px";
        cnt.style.marginLeft = "8px";
        cnt.addEventListener("input", () => {
            const v = cnt.value.replace(/[^0-9]/g, "");
            cnt.value = v;
            gachaState.catCounts[c] = parseInt(v, 10) || 0;
            serializeGacha();
        });
        list.appendChild(el("label", { class: "ap-cat-item" }, el("span", {}, c), cnt));
    });
    wrap.appendChild(list);

    // 扭蛋生成 / 清空
    const genBtn = el("button", { class: "ap-btn primary", onclick: () => runGacha() }, "🎰 扭蛋生成");
    const clrBtn = el("button", { class: "ap-btn", onclick: () => { gachaState.resultTags = []; serializeGacha(); renderResult(); renderGachaPanel(); } }, "清空扭蛋");
    wrap.appendChild(el("div", { class: "ap-gacha-row" },
        genBtn, clrBtn,
    ));

    // 弹窗内随机抽取（与节点级共用 gacha_across 接口，结果共享 gacha_data）
    wrap.appendChild(buildQuickRandomRow(2));

    const cur = el("div", { class: "ap-gacha-current" });
    cur.appendChild(el("div", { class: "ap-gacha-sub" }, `当前扭蛋结果（${gachaState.resultTags.length}）`));
    const grid = el("div", { class: "ap-res-grid" });
    gachaState.resultTags.forEach((t) => grid.appendChild(buildResultCard(t, true)));
    if (!gachaState.resultTags.length) grid.appendChild(el("div", { class: "ap-empty small" }, "尚无扭蛋结果"));
    cur.appendChild(grid);
    wrap.appendChild(cur);

    mainScroll.appendChild(wrap);
    updatePager();
}

function renderResult() {
    if (!resultPanel) return;
    resultPanel.innerHTML = "";
    resultPanel.appendChild(el("div", { class: "ap-res-title" }, "结果"));

    const selSec = el("div", { class: "ap-res-section" });
    selSec.appendChild(el("div", { class: "ap-res-sub" }, `已选（${state.selectedMap.size}）`));
    const selGrid = el("div", { class: "ap-res-grid" });
    [...state.selectedMap.values()].forEach((t) => selGrid.appendChild(buildResultCard(t, false)));
    if (!state.selectedMap.size) selGrid.appendChild(el("div", { class: "ap-empty small" }, "点击画廊卡片选择"));
    selSec.appendChild(selGrid);
    resultPanel.appendChild(selSec);

    const gSec = el("div", { class: "ap-res-section" });
    gSec.appendChild(el("div", { class: "ap-res-sub" }, `扭蛋（${gachaState.resultTags.length}）`));
    const gGrid = el("div", { class: "ap-res-grid" });
    gachaState.resultTags.forEach((t) => gGrid.appendChild(buildResultCard(t, true)));
    if (!gachaState.resultTags.length) gGrid.appendChild(el("div", { class: "ap-empty small" }, "扭蛋结果将显示在此"));
    gSec.appendChild(gGrid);
    resultPanel.appendChild(gSec);

    // 输出预览
    const outSec = el("div", { class: "ap-res-section" });
    outSec.appendChild(el("div", { class: "ap-res-sub" }, "输出预览"));
    const merged = mergedOutput();
    outSec.appendChild(el("div", { class: "ap-output" }, merged || "（空）"));
    resultPanel.appendChild(outSec);
}

function mergedOutput() {
    const seen = new Set();
    const out = [];
    for (const it of state.selectedMap.values()) { const t = itemText(it); if (t && !seen.has(t)) { seen.add(t); out.push(t); } }
    for (const it of gachaState.resultTags) { const t = itemText(it); if (t && !seen.has(t)) { seen.add(t); out.push(t); } }
    return out.join(", ");
}

// ========== 扭蛋 ==========
async function runGacha() {
    // 从 catCounts 中读取数量 > 0 的分类
    const category_counts = {};
    for (const cat of state.categories) {
        const cnt = parseInt(gachaState.catCounts[cat], 10) || 0;
        if (cnt > 0) category_counts[cat] = Math.min(30, cnt);
    }
    if (!Object.keys(category_counts).length) { flashStatus("所有分类的数量为0，请先设置抽取数量"); return; }
    try {
        const path = `/anima/prompt/gacha?category_counts=${encodeURIComponent(JSON.stringify(category_counts))}`;
        const data = await apiGetJson(path);
        const tags = (data.tags || []).map((t) => normItem(t, t.category || ""));
        // 合并进现有扭蛋结果（去重）
        const seen = new Set(gachaState.resultTags.map((t) => itemKey(t)));
        tags.forEach((t) => { const k = itemKey(t); if (k && !seen.has(k)) { seen.add(k); gachaState.resultTags.push(t); } });
        serializeGacha();
        renderResult();
        renderGachaPanel();
        flashStatus(`扭蛋成功，获得 ${tags.length} 个`);
    } catch (e) {
        flashStatus("扭蛋失败：" + e.message);
    }
}

// 跨不同分类随机抽取：每个分类最多 1 个，总数恰为 count（替换现有扭蛋结果）
async function quickAcross(count) {
    count = Math.max(1, count | 0);
    try {
        const data = await apiGetJson(`/anima/prompt/gacha_across?count=${count}`);
        const tags = (data.tags || []).map((t) => normItem(t, t.category || ""));
        gachaState.resultTags = tags;
        serializeGacha();
        renderResult();
        if (mainScroll) renderGachaPanel();
        flashStatus(`随机抽取 ${tags.length} 个标签（来自 ${tags.length} 个不同分类）`);
    } catch (e) {
        flashStatus("随机抽取失败：" + e.message);
    }
}

// 构建「随机抽取 + 总数」控件行（用于弹窗扭蛋页）
function buildQuickRandomRow(defaultCount) {
    const num = el("input", { class: "ap-mini-num", type: "text", inputmode: "numeric", pattern: "[0-9]*", value: String(defaultCount || 2) });
    num.addEventListener("input", () => { num.value = num.value.replace(/[^0-9]/g, ""); });
    const btn = el("button", { class: "ap-btn", onclick: async () => {
        await quickAcross(parseInt(num.value, 10) || 2);
        if (nodeRef && nodeRef._updateAnimaPreview) nodeRef._updateAnimaPreview();
    } }, "🎲 随机抽取");
    return el("div", { class: "ap-gacha-row" },
        el("div", { class: "ap-gacha-rowlabel" }, "随机标签总数"), num, btn,
    );
}

// ========== 标签页 ==========
function buildTabs() {
    if (!tabGroupEl) return;
    tabGroupEl.innerHTML = "";
    tabEls = {};
    const all = [...state.categories, GACHA_TAB];
    all.forEach((cat) => {
        const label = cat === GACHA_TAB ? "🎰 扭蛋" : cat;
        const t = el("div", { class: "ap-tab", onclick: () => switchTab(cat) }, label);
        tabEls[cat] = t;
        tabGroupEl.appendChild(t);
    });
}
function updateTabStyle() {
    for (const cat in tabEls) {
        const active = cat === state.currentTab;
        const t = tabEls[cat];
        t.style.background = active ? COLORS.accent : "transparent";
        t.style.color = active ? "#fff" : COLORS.textDim;
        t.style.fontWeight = active ? "600" : "400";
    }
    if (pagerBar) pagerBar.style.display = state.currentTab === GACHA_TAB ? "none" : "flex";
    if (toolbarEl) toolbarEl.style.display = state.currentTab === GACHA_TAB ? "none" : "flex";
}
function switchTab(cat) {
    state.currentTab = cat;
    updateTabStyle();
    if (searchInputEl && cat !== GACHA_TAB) searchInputEl.value = ensureTabState(cat).query || "";
    if (cat === GACHA_TAB) { renderGachaPanel(); return; }
    const ts = ensureTabState(cat);
    if (!ts.items.length) doSearch(cat);
    else renderGallery();
}

function updatePager() {
    if (!pagerBar) return;
    const cat = state.currentTab;
    if (cat === GACHA_TAB) { pagerBar.innerHTML = ""; return; }
    const ts = ensureTabState(cat);
    pagerBar.innerHTML = "";
    const prev = el("button", { class: "ap-page-btn", onclick: () => { if (ts.page > 1) { ts.page--; doSearch(cat); } } }, "‹ 上一页");
    const info = el("div", { class: "ap-page-info" }, `第 ${ts.page} / ${ts.totalPages} 页`);
    const next = el("button", { class: "ap-page-btn", onclick: () => { if (ts.page < ts.totalPages) { ts.page++; doSearch(cat); } } }, "下一页 ›");
    pagerBar.append(prev, info, next);
}

let _flashTimer = null;
function flashStatus(msg) {
    if (!currentModal) return;
    let t = currentModal.querySelector(".ap-toast");
    if (!t) { t = el("div", { class: "ap-toast" }); currentModal.appendChild(t); }
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(_flashTimer);
    _flashTimer = setTimeout(() => { if (t) t.classList.remove("show"); }, 2200);
}

// ========== 恢复 ==========
function restoreFromNode(node) {
    const nodeId = node.id;
    const ns = getNodeState(nodeId);
    // 从节点存储加载状态
    state.selectedMap = new Map(parseSelection(getWidget(node, "selection_data", "{}")).map((s) => [itemKey(s), s]));
    gachaState.resultTags = parseGacha(getWidget(node, "gacha_data", "{}"));
    const uiState = parseUIState(getWidget(node, "ui_state", "{}"));
    state.currentTab = uiState.currentTab;
    gachaState.count = uiState.gachaCount || 3;
    gachaState.checkedCats = Array.isArray(uiState.gachaCats) ? [...uiState.gachaCats] : [];
    gachaState.catCounts = (uiState.gachaCatCounts && typeof uiState.gachaCatCounts === "object") ? { ...uiState.gachaCatCounts } : {};
    // ★ 关键修复：清空旧节点的 tabState，防止节点间状态串扰
    state.tabState = {};
    // 恢复各分类页码（延迟到分类加载后应用）
    state._pendingTabPages = uiState.tabPages;
    // 将解析后的状态保存到节点存储（覆盖）
    ns.state.selectedMap = new Map(state.selectedMap);
    ns.state.tabState = state.tabState;
    ns.state.currentTab = state.currentTab;
    ns.state._pendingTabPages = state._pendingTabPages;
    ns.gachaState.resultTags = [...gachaState.resultTags];
    ns.gachaState.count = gachaState.count;
}

// ========== 模态框 ==========
async function createAnimaModal(node) {
    if (currentModal) { currentModal.focus(); return; }
    nodeRef = node;

    const overlay = el("div", { class: "ap-overlay" });
    const modal = el("div", { class: "ap-modal" });

    const header = el("div", { class: "ap-header" },
        el("div", { class: "ap-title" }, "⚓ Anima Prompt Selector"),
        el("div", { style: "display:flex;gap:6px;align-items:center;" },
            el("div", { class: "ap-btn small", title: "重置全部分页（保留扭蛋）", onclick: () => resetAllTabs(), style: "background:#2a3a5c;color:#ffa502;border:1px solid #ffa502;font-size:11px;padding:4px 10px;cursor:pointer;border-radius:4px;" }, "↻ 重置分页"),
            el("div", { class: "ap-close", onclick: () => closeModal() }, "✕"),
        ),
    );

    tabGroupEl = el("div", { class: "ap-tabs" });

    const toolbar = el("div", { class: "ap-toolbar" });
    const searchInput = el("input", { class: "ap-search", type: "text", placeholder: "搜索标签（英文/中文，回车搜索）" });
    const searchBtn = el("button", { class: "ap-btn small", onclick: () => {
        const cat = state.currentTab;
        if (cat === GACHA_TAB) return;
        const ts = ensureTabState(cat);
        ts.query = searchInput.value.trim(); ts.page = 1; doSearch(cat);
    } }, "搜索");
    searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") searchBtn.click(); });
    const defaultBtn = el("button", { class: "ap-btn small", title: "清空搜索", onclick: () => {
        const cat = state.currentTab;
        if (cat === GACHA_TAB) return;
        const ts = ensureTabState(cat);
        searchInput.value = ""; ts.query = ""; ts.page = 1; doSearch(cat);
    } }, "重置");
    toolbar.append(searchInput, searchBtn, defaultBtn);
    toolbarEl = toolbar;
    searchInputEl = searchInput;

    const body = el("div", { class: "ap-body" });
    mainScroll = el("div", { class: "ap-main" });
    pagerBar = el("div", { class: "ap-pager" });
    const leftCol = el("div", { class: "ap-left" }, mainScroll, pagerBar);
    resultPanel = el("div", { class: "ap-result" });
    body.append(leftCol, resultPanel);

    const applyBtn = el("button", { class: "ap-btn primary", onclick: () => { serializeSelection(); serializeGacha(); closeModal(); } }, "应用");
    const clearBtn = el("button", { class: "ap-btn", onclick: () => clearAll() }, "清空");

    modal.append(header, tabGroupEl, toolbar, body, el("div", { class: "ap-footer" }, clearBtn, applyBtn));
    overlay.append(modal);
    document.body.appendChild(overlay);
    currentModal = overlay;

    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) closeModal(); });

    injectStyle();
    restoreFromNode(node);

    await loadCategories();
    // 应用待处理的页码
    if (state._pendingTabPages) {
        for (const cat in state._pendingTabPages) {
            if (state.categories.includes(cat)) {
                const ts = ensureTabState(cat);
                ts.page = state._pendingTabPages[cat].page || 1;
            }
        }
        delete state._pendingTabPages;
    }
    buildTabs();
    const first = (state.currentTab === GACHA_TAB || state.categories.includes(state.currentTab)) ? state.currentTab : (state.categories[0] || GACHA_TAB);
    renderResult();
    switchTab(first);
}
function closeModal() {
    // 关闭前序列化 UI 状态
    if (nodeRef) serializeUIState();
    // 保存当前状态到节点存储
    if (nodeRef) {
        const nodeId = nodeRef.id;
        const ns = getNodeState(nodeId);
        ns.state.selectedMap = new Map(state.selectedMap);
        ns.state.tabState = state.tabState;
        ns.state.currentTab = state.currentTab;
        ns.state._pendingTabPages = state._pendingTabPages;
        ns.gachaState.resultTags = [...gachaState.resultTags];
        ns.gachaState.count = gachaState.count;
        ns.gachaState.checkedCats = [...gachaState.checkedCats];
        ns.gachaState.catCounts = { ...gachaState.catCounts };
    }
    if (currentModal) { currentModal.remove(); currentModal = null; }
    mainScroll = null; pagerBar = null; resultPanel = null; tabGroupEl = null; tabEls = {}; toolbarEl = null; searchInputEl = null;
    if (nodeRef && nodeRef._updateAnimaPreview) nodeRef._updateAnimaPreview();
}

function injectStyle() {
    if (document.getElementById("ap-style-v2")) return;
    const css = `
.ap-overlay{position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:10000;display:flex;align-items:center;justify-content:center;}
.ap-modal{width:94vw;max-width:1280px;height:90vh;background:${COLORS.modalBg};border-radius:10px;border:1px solid ${COLORS.border};display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 48px rgba(0,0,0,.55);}
.ap-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};}
.ap-title{color:${COLORS.text};font-size:16px;font-weight:600;}
.ap-close{color:${COLORS.textDim};cursor:pointer;font-size:16px;padding:4px 8px;border-radius:4px;transition:.15s;}
.ap-close:hover{color:${COLORS.text};background:rgba(255,255,255,.1);}
.ap-tabs{display:flex;gap:2px;padding:8px 16px 0;background:${COLORS.headerBg};flex-wrap:wrap;}
.ap-tab{padding:7px 16px;border-radius:4px 4px 0 0;cursor:pointer;font-size:13px;color:${COLORS.textDim};transition:.15s;}
.ap-tab:hover{color:${COLORS.text};}
.ap-toolbar{display:flex;align-items:center;gap:8px;padding:10px 16px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};border-bottom:1px solid ${COLORS.border};flex-wrap:wrap;}
.ap-search{flex:1;min-width:160px;padding:7px 10px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:5px;color:${COLORS.text};font-size:12px;}
.ap-search:focus{outline:none;border-color:${COLORS.accent};}
.ap-body{display:flex;flex-direction:row;flex:1;min-height:0;}
.ap-left{display:flex;flex-direction:column;flex:1;min-width:0;}
.ap-main{flex:1;overflow-y:auto;padding:14px 16px;}
.ap-pager{display:flex;align-items:center;justify-content:center;gap:16px;padding:8px;border-top:1px solid ${COLORS.border};background:${COLORS.contentBg};}
.ap-page-btn{background:${COLORS.cardBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:5px;padding:5px 14px;cursor:pointer;font-size:12px;}
.ap-page-btn:hover{border-color:${COLORS.accent};}
.ap-page-info{color:${COLORS.textDim};font-size:12px;}
.ap-result{width:clamp(240px,26vw,360px);background:${COLORS.contentBg};border-left:1px solid ${COLORS.border};overflow-y:auto;padding:12px;}
.ap-res-title{color:${COLORS.text};font-size:13px;font-weight:600;margin-bottom:8px;}
.ap-res-sub{color:${COLORS.accentHover};font-size:12px;font-weight:500;margin:10px 0 6px;}
.ap-res-grid{display:flex;flex-direction:column;gap:6px;}
.ap-res-card{display:flex;align-items:center;gap:8px;background:${COLORS.cardBg};border:1px solid ${COLORS.cardBorder};border-radius:6px;padding:6px 8px;transition:.15s;}
.ap-res-card:hover{border-color:${COLORS.accent};}
.ap-res-info{flex:1;min-width:0;}
.ap-res-name{color:${COLORS.text};font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.ap-res-cat{color:${COLORS.textDim};font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.ap-res-del{background:none;border:none;color:${COLORS.danger};cursor:pointer;font-size:13px;padding:2px 6px;border-radius:4px;flex-shrink:0;}
.ap-res-del:hover{background:rgba(255,107,107,.15);}
.ap-output{background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:6px;padding:8px;color:${COLORS.text};font-size:12px;line-height:1.5;word-break:break-word;max-height:160px;overflow-y:auto;}
.ap-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;}
.ap-card{position:relative;background:${COLORS.cardBg};border:1px solid ${COLORS.cardBorder};border-radius:8px;padding:12px;cursor:pointer;transition:transform .12s,border-color .15s;outline:none;}
.ap-card:hover{transform:translateY(-2px);border-color:${COLORS.accent};}
.ap-card.selected{border-color:${COLORS.success};box-shadow:0 0 0 2px rgba(46,213,115,.35);}
.ap-card-header{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:6px;}
.ap-card-en{font-size:13px;font-weight:600;color:${COLORS.text};word-break:break-word;}
.ap-card-check{width:20px;height:20px;flex-shrink:0;border-radius:50%;border:2px solid ${COLORS.border};display:flex;align-items:center;justify-content:center;font-size:12px;color:transparent;transition:.15s;}
.ap-card-check.active{background:${COLORS.success};border-color:${COLORS.success};color:#fff;}
.ap-card-cn{font-size:12px;color:${COLORS.textDim};line-height:1.4;}
.ap-empty{color:${COLORS.textDim};font-size:13px;padding:40px 10px;text-align:center;}
.ap-empty.small{padding:14px 6px;font-size:12px;}
.ap-btn{background:${COLORS.cardBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:6px;padding:8px 14px;cursor:pointer;font-size:12px;font-weight:500;transition:.15s;}
.ap-btn:hover{border-color:${COLORS.accent};}
.ap-btn.primary{background:${COLORS.accent};color:#fff;border-color:${COLORS.accent};}
.ap-btn.primary:hover{background:${COLORS.accentHover};}
.ap-btn.small{padding:6px 10px;font-size:12px;}
.ap-footer{display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:10px 16px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};}
.ap-toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%) translateY(10px);background:rgba(0,0,0,.82);color:#fff;padding:8px 14px;border-radius:6px;font-size:12px;opacity:0;pointer-events:none;transition:.2s;z-index:9999;max-width:80vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.ap-toast.show{opacity:1;transform:translateX(-50%) translateY(0);}
.ap-gacha{padding:4px;}
.ap-gacha-hint{color:${COLORS.textDim};font-size:12px;margin-bottom:12px;line-height:1.5;}
.ap-gacha-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;}
.ap-gacha-rowlabel{color:${COLORS.text};font-size:13px;}
.ap-cat-list{display:flex;flex-direction:column;gap:4px;margin-bottom:14px;max-height:260px;overflow-y:auto;padding:2px;}
.ap-cat-item{display:flex;align-items:center;gap:8px;background:${COLORS.cardBg};border:1px solid ${COLORS.cardBorder};border-radius:5px;padding:6px 8px;font-size:12px;color:${COLORS.text};transition:.15s;}
.ap-cat-item:hover{border-color:${COLORS.accent};}
.ap-mini-select{background:${COLORS.inputBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:5px;padding:6px 8px;font-size:12px;}
.ap-mini-num{width:56px;background:${COLORS.inputBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:5px;padding:6px;font-size:12px;text-align:center;appearance:textfield;-moz-appearance:textfield;-webkit-appearance:none;outline:none;}
.ap-gacha-sub{color:${COLORS.accentHover};font-size:13px;font-weight:500;margin-bottom:8px;}
@media (max-width:780px){
  .ap-body{flex-direction:column;}
  .ap-result{width:100%;border-left:none;border-top:1px solid ${COLORS.border};max-height:38vh;}
}
`;
    const style = document.createElement("style");
    style.id = "ap-style-v2";
    style.textContent = css;
    document.head.appendChild(style);
}

// ========== 注册扩展 ==========
app.registerExtension({
    name: "naiba.AnimaPromptNode",
    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "AnimaPromptNode") return;
        const origOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            const node = this;
            nodeRef = node;

            // 隐藏由前端代理的控件（selection_data / gacha_data / ui_state），separator 保留可见
            ["selection_data", "gacha_data", "ui_state"].forEach((name) => {
                const w = node.widgets?.find((x) => x.name === name);
                if (w) {
                    w.hidden = true;
                    if (w.inputEl) w.inputEl.style.display = "none";
                    if (w.element) w.element.style.display = "none";
                }
            });

            // 已选摘要预览区
            const previewArea = document.createElement("div");
            previewArea.style.cssText = `
                width:100%;min-height:54px;max-height:130px;background:${COLORS.inputBg};
                border:1px solid ${COLORS.border};border-radius:4px;
                margin:8px 0;padding:6px;overflow-y:auto;
                font-size:11px;color:${COLORS.text};line-height:1.5;`;
            const updatePreview = () => {
                let html = "";
                try {
                    const sel = JSON.parse(getWidget(node, "selection_data", "{}") || "{}");
                    const arr = Array.isArray(sel.selected) ? sel.selected : [];
                    if (arr.length) {
                        const names = arr.map((x) => x.raw_en || x.tag).filter(Boolean);
                        html += `<div style="margin:2px 0;"><span style="color:${COLORS.accent};">已选 ${names.length}：</span>${names.join(", ")}</div>`;
                    }
                } catch (e) { /* ignore */ }
                try {
                    const g = JSON.parse(getWidget(node, "gacha_data", "{}") || "{}");
                    const arr = Array.isArray(g.tags) ? g.tags : [];
                    if (arr.length) {
                        const names = arr.map((x) => x.raw_en || x.tag).filter(Boolean);
                        html += `<div style="margin:2px 0;"><span style="color:${COLORS.success};">扭蛋 ${names.length}：</span>${names.join(", ")}</div>`;
                    }
                } catch (e) { /* ignore */ }
                if (!html) html = `<div style="color:${COLORS.textDim};text-align:center;padding:14px;">点击下方按钮选择标签</div>`;
                previewArea.innerHTML = html;
            };
            node._updateAnimaPreview = updatePreview;
            updatePreview();

            const openBtn = document.createElement("button");
            openBtn.textContent = "⚓ 打开标签选择器";
            openBtn.style.cssText = `width:100%;padding:10px;margin:8px 0;background:${COLORS.accent};color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500;transition:background .2s;`;
            openBtn.addEventListener("mouseenter", () => openBtn.style.background = COLORS.accentHover);
            openBtn.addEventListener("mouseleave", () => openBtn.style.background = COLORS.accent);
            openBtn.addEventListener("click", () => createAnimaModal(node));

            const clearBtn = document.createElement("button");
            clearBtn.textContent = "清除已选";
            clearBtn.style.cssText = `width:100%;padding:8px;margin:4px 0;background:${COLORS.danger};color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:500;transition:background .2s;`;
            clearBtn.addEventListener("mouseenter", () => clearBtn.style.background = "#ff8585");
            clearBtn.addEventListener("mouseleave", () => clearBtn.style.background = COLORS.danger);
            clearBtn.addEventListener("click", () => {
                setWidget(node, "selection_data", "{}");
                setWidget(node, "gacha_data", JSON.stringify({ tags: [] }));
                state.selectedMap.clear();
                gachaState.resultTags = [];
                updatePreview();
                if (currentModal) { renderResult(); if (state.currentTab) switchTab(state.currentTab); }
            });

            // 🎲 随机抽取（节点级快扭：不打开弹窗也能扭蛋，仿 naiba_tag_picker 排版）
            const randomCount = document.createElement("input");
            randomCount.type = "number"; randomCount.min = "1"; randomCount.max = "30"; randomCount.value = "2";
            randomCount.title = "随机标签总数：随机选 N 个不同分类，每个分类各取 1 个标签";
            randomCount.style.cssText = "width:54px;margin-left:6px;background:" + COLORS.inputBg + ";color:" + COLORS.text + ";border:1px solid " + COLORS.cardBorder + ";border-radius:5px;height:28px;font-size:13px;text-align:center;";
            const randomBtn = document.createElement("button");
            randomBtn.textContent = "🎲 随机抽取";
            randomBtn.style.cssText = "flex:1;height:28px;font-size:13px;padding:0 10px;background:" + COLORS.cardBg + ";color:" + COLORS.text + ";border:1px solid " + COLORS.border + ";border-radius:6px;cursor:pointer;font-weight:500;transition:.15s;";
            randomBtn.addEventListener("mouseenter", () => randomBtn.style.borderColor = COLORS.accent);
            randomBtn.addEventListener("mouseleave", () => randomBtn.style.borderColor = COLORS.border);
            randomBtn.addEventListener("click", async () => {
                randomBtn.disabled = true;
                const orig = randomBtn.textContent;
                randomBtn.textContent = "生成中…";
                try {
                    await quickAcross(parseInt(randomCount.value, 10) || 2);
                    updatePreview();
                } catch (e) { /* quickAcross 已提示 */ }
                finally { randomBtn.disabled = false; randomBtn.textContent = orig; }
            });
            const randomRow = document.createElement("div");
            randomRow.style.cssText = "display:flex;flex-direction:row;align-items:stretch;margin:4px 0;gap:0;";
            randomRow.appendChild(randomBtn);
            randomRow.appendChild(randomCount);

            const container = document.createElement("div");
            container.style.cssText = "display:flex;flex-direction:column;gap:4px;width:100%;box-sizing:border-box;";
            container.appendChild(previewArea);
            container.appendChild(randomRow);
            container.appendChild(openBtn);
            container.appendChild(clearBtn);

            const measureContainerHeight = () => {
                const h = Math.ceil(container.scrollHeight || 0);
                // 未布局（scrollHeight 仍为 0）时用保守保底，其余一律按真实内容高度，
                // 不再使用硬编码 200 下限，避免矮节点被撑成约 2 倍高。
                return h > 0 ? h : 120;
            };
            const domWidget = node.addDOMWidget("anima_container", "ANIMA_CONTAINER", container, {
                getValue() { return ""; },
                setValue() {},
                getMinHeight() {
                    return measureContainerHeight();
                },
            });
            const panelEl = domWidget.element || container;
            [panelEl, container].forEach((elx) => {
                if (!elx) return;
                elx.classList.remove("h-full");
                elx.style.height = "auto";
                elx.style.minHeight = "max-content";
            });

            node.minWidth = 260;
            node.minHeight = 180;

            container.style.overflow = "hidden";
            domWidget.computeSize = (w) => [w, measureContainerHeight()];

            // 初次 computeSize 测量时节点 DOM 尚未布局，宽度未定会导致 scrollHeight 误测成约 2 倍。
            // 这里在容器真正布局、宽度稳定后调用 node.setSize 把节点高度收敛到真实内容高度。
            const applyContainerHeight = () => {
                if (typeof node.computeSize !== "function") return;
                const cs = node.computeSize();
                if (!cs || !cs[1]) return;
                if (Math.abs((node.size?.[1] || 0) - cs[1]) > 4) {
                    node.setSize?.([node.size[0], cs[1]]);
                }
                node.setDirtyCanvas?.(true, true);
                node.graph?.setDirtyCanvas(true, true);
            };

            let _resizeRaf = null;
            if (typeof ResizeObserver !== "undefined") {
                new ResizeObserver(() => {
                    if (_resizeRaf) cancelAnimationFrame(_resizeRaf);
                    _resizeRaf = requestAnimationFrame(applyContainerHeight);
                }).observe(container);
            }
            requestAnimationFrame(applyContainerHeight);
        };
    },
});
