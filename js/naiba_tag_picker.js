/**
 * Naiba Tag Picker - 前端画廊扩展 v2
 * 统一状态层 + 左右分栏（左画廊/右结果）+ 多标签页（画师/角色/IP/标签/扭蛋/黑名单/收藏）
 * 交互红线：单面板、hover 即操作、零嵌套弹窗、最少点击。
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ========== 颜色常量（暗色玻璃 + 紫色强调） ==========
const COLORS = {
    modalBg: "#1a1a2e",
    headerBg: "#16213e",
    contentBg: "#0f1729",
    accent: "#6c5ce7",
    accentHover: "#7c6cf7",
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

const DANBOORU_BASE = "https://danbooru.donmai.us";
const GALLERY_TABS = ["artist", "character", "ip", "tag"];
const TABS = ["artist", "character", "ip", "tag", "gacha", "blacklist", "favorites", "settings"];
const TAB_LABEL = { artist: "画师", character: "角色", ip: "IP", tag: "标签", gacha: "扭蛋", blacklist: "黑名单", favorites: "收藏", settings: "设置" };
const CATEGORY_CN = { artist: "画师", character: "角色", copyright: "IP", tag: "标签" };
// 画廊 tab -> Danbooru category 参数
const TAB_CAT = { artist: "artist", character: "character", ip: "copyright", tag: "tag" };
// 扭蛋配置 key -> {routeParam, tabCat}
const GACHA_CATS = {
    artist: { param: "artist", tabCat: "artist" },
    character: { param: "character", tabCat: "character" },
    copyright: { param: "ip", tabCat: "ip" },
};
const MAX_TOTAL_SELECTED = 64;
const BLACKLIST_CAP = 5000;
const FAVORITES_CAP = 2000;

let currentModal = null;

// ========== 统一状态层 ==========
const state = {
    selectedMap: new Map(),   // tag -> {tag, category}
    blacklist: new Set(),     // tag 字符串
    favorites: new Map(),     // tag -> category
    gachaConfig: {            // 每类扭蛋配置
        artist: { source: "live", n: 3 },
        character: { source: "live", n: 3 },
        copyright: { source: "live", n: 3 },
    },
    tabState: {
        artist: { items: [], page: 1, loading: false, seq: 0, query: "", single: false },
        character: { items: [], page: 1, loading: false, seq: 0, query: "", single: false },
        ip: { items: [], page: 1, loading: false, seq: 0, query: "", single: false },
        tag: { items: [], page: 1, loading: false, seq: 0, query: "", single: false },
    },
    currentTab: "artist",
};
const gachaState = { resultTags: [] }; // [{tag, category}]
let nodeRef = null;

// ========== DOM 引用 ==========
let mainScroll = null;
let pagerBar = null;
let resultPanel = null;
let statusEl = null;
let tabEls = {};
let gachaPanelEl = null;

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

function previewSize() { return parseInt(getWidget(nodeRef, "preview_size", 220), 10) || 220; }
function cacheOn() { return getWidget(nodeRef, "cache_enabled", true) ? 1 : 0; }
function cacheMax() { return parseInt(getWidget(nodeRef, "cache_max_items", 300), 10) || 300; }

// ========== 版本化持久化 ==========
function serializeList(arr) { return JSON.stringify({ version: 1, items: arr }); }
function parseList(raw, cap) {
    try {
        const v = JSON.parse(raw);
        let items = Array.isArray(v) ? v : (v && Array.isArray(v.items) ? v.items : []);
        items = items.map((x) => (typeof x === "string" ? x : x?.tag)).filter(Boolean).map(String);
        const seen = new Set();
        const out = [];
        for (const t of items) { if (!seen.has(t)) { seen.add(t); out.push(t); } }
        return cap ? out.slice(0, cap) : out;
    } catch (e) { return []; }
}
function parseFavs(raw) {
    try {
        const v = JSON.parse(raw);
        const items = Array.isArray(v) ? v : (v && Array.isArray(v.items) ? v.items : []);
        const out = new Map();
        for (const it of items) {
            const tag = it?.tag || (typeof it === "string" ? it : null);
            if (!tag) continue;
            out.set(String(tag), it?.category || "tag");
        }
        return out;
    } catch (e) { return new Map(); }
}
function parseSelection(raw) {
    try {
        const v = JSON.parse(raw);
        if (v && Array.isArray(v.selected)) return v.selected.filter((x) => x && x.tag).map((x) => ({ tag: x.tag, category: x.category || "tag" }));
        // 兼容旧格式（按分类数组）
        if (v && typeof v === "object") {
            const out = [];
            for (const cat of GALLERY_TABS) (v[cat] || []).forEach((it) => { if (it && it.tag) out.push({ tag: it.tag, category: it.category || cat }); });
            return out;
        }
    } catch (e) {}
    return [];
}
function parseGacha(raw) {
    try {
        const v = JSON.parse(raw);
        if (v && Array.isArray(v.tags)) return v.tags.filter((x) => x && x.tag).map((x) => ({ tag: x.tag, category: x.category || "" }));
    } catch (e) {}
    return [];
}

function serializeSelection() { setWidget(nodeRef, "selection_data", JSON.stringify({ selected: [...state.selectedMap.values()] })); }
function serializeGacha() { setWidget(nodeRef, "gacha_data", JSON.stringify({ tags: gachaState.resultTags })); }
function serializeBlacklist() { setWidget(nodeRef, "blacklist_data", serializeList([...state.blacklist])); }
function serializeFavorites() { setWidget(nodeRef, "favorites_data", serializeList([...state.favorites.entries()].map(([tag, category]) => ({ tag, category })))); }

// ========== 统一更新入口 ==========
function selectTag(item) {
    if (!item || !item.tag) return;
    const key = item.tag;
    if (state.selectedMap.has(key)) state.selectedMap.delete(key);
    else {
        if (state.selectedMap.size >= MAX_TOTAL_SELECTED) { flashStatus("已达上限 " + MAX_TOTAL_SELECTED); return; }
        state.selectedMap.set(key, { tag: item.tag, category: item.category || "tag" });
    }
    serializeSelection();
    renderGallerySelectionStates();
    renderResult();
    renderStatus();
}
function removeSelected(tag) {
    state.selectedMap.delete(tag);
    serializeSelection();
    renderGallerySelectionStates();
    renderResult();
    renderStatus();
}
function toggleBlacklist(tag) {
    if (!tag) return;
    if (state.blacklist.has(tag)) {
        state.blacklist.delete(tag);
        flashStatus("已解除屏蔽：" + tag);
    } else {
        state.blacklist.add(tag);
        flashStatus("已加入黑名单：" + tag);
    }
    serializeBlacklist();
    if (GALLERY_TABS.includes(state.currentTab)) renderGallery();
    renderBlacklist();
}
function toggleFavorite(item) {
    if (!item || !item.tag) return;
    const key = item.tag;
    if (state.favorites.has(key)) state.favorites.delete(key);
    else {
        if (state.favorites.size >= FAVORITES_CAP) { flashStatus("收藏已达上限"); return; }
        state.favorites.set(key, item.category || "tag");
    }
    serializeFavorites();
    renderGallerySelectionStates();
    renderFavorites();
}
function replaceGachaCategory(catName, tags) {
    gachaState.resultTags = gachaState.resultTags.filter((t) => t.category !== catName)
        .concat(tags.map((t) => ({ tag: typeof t === "string" ? t : t.tag, category: catName })).filter((t) => t.tag));
    serializeGacha();
    renderResult();
    refreshGachaPreview();
}
function setGachaAll(tags, { syncModal = true } = {}) {
    gachaState.resultTags = tags.map((t) => ({ tag: t.tag || t, category: t.category || "" }));
    serializeGacha();
    if (syncModal) { renderResult(); refreshGachaPreview(); }
}

// ========== 网络 ==========
async function apiGetJson(path) {
    const resp = await api.fetchApi(path);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return await resp.json();
}
async function doSearch(cat) {
    const ts = state.tabState[cat];
    ts.loading = true;
    if (GALLERY_TABS.includes(state.currentTab) && state.currentTab === cat) renderGallery();
    const seq = ++ts.seq;
    const category = TAB_CAT[cat];
    const q = ts.query;
    // 画师页支持「仅单画师」：用 name_matches 收紧；这里直接走 search
    const path = `/naiba/tag/search?q=${encodeURIComponent(q)}&cat=${encodeURIComponent(category)}&limit=${encodeURIComponent(getWidget(nodeRef, "max_images", 9))}&page=${ts.page}`;
    try {
        const data = await apiGetJson(path);
        if (seq !== ts.seq) return; // 过期请求，丢弃
        ts.items = (data.items || []).map((it) => ({ id: it.id, tag: it.tag, post_count: it.post_count, category: it.category, preview_url: it.preview_url, source_url: it.source_url }));
    } catch (e) {
        if (seq !== ts.seq) return;
        ts.items = [];
        flashStatus("搜索失败：" + e.message);
    } finally {
        ts.loading = false;
        if (seq === ts.seq && (state.currentTab === cat || state.currentTab === "gacha")) renderGallery();
    }
}

// ========== 预览图（并发令牌桶） ==========
const _previewQueue = [];
let _previewRunning = 0;
const MAX_PREVIEW = 4;
function schedulePreview(tag, imgEl, size) {
    if (!imgEl) return;
    if (imgEl.dataset.tpTag === tag && imgEl.src) return;
    imgEl.dataset.tpTag = tag;
    _previewQueue.push({ tag, imgEl, size });
    drainPreview();
}
function drainPreview() {
    while (_previewRunning < MAX_PREVIEW && _previewQueue.length) {
        const job = _previewQueue.shift();
        _previewRunning++;
        loadPreview(job).finally(() => { _previewRunning--; drainPreview(); });
    }
}
async function loadPreview({ tag, imgEl, size }) {
    try {
        const path = `/naiba/tag/preview?tag=${encodeURIComponent(tag)}&size=${size}&cache=${cacheOn()}&max=${cacheMax()}`;
        const data = await apiGetJson(path);
        if (imgEl.dataset.tpTag === tag && data.preview_url) imgEl.src = data.preview_url;
    } catch (e) { /* 保持占位 */ }
}
function refreshGachaPreview() {
    if (!resultPanel) return;
    resultPanel.querySelectorAll("img[data-gacha]").forEach((img) => schedulePreview(img.dataset.tag, img, 56));
}

// ========== 卡片构建 ==========
function buildGalleryCard(it, cat) {
    const category = it.category || TAB_CAT[cat] || "tag";
    const isSel = state.selectedMap.has(it.tag);
    const isFav = state.favorites.has(it.tag);
    const card = el("div", {
        class: "tp-card" + (isSel ? " selected" : ""),
        tabindex: "0",
        title: it.tag + (it.post_count ? ` (${it.post_count})` : "") + "\nCtrl+点击 打开 Danbooru",
    });
    const img = el("img", { class: "tp-thumb", src: PLACEHOLDER, alt: it.tag, loading: "lazy" });
    schedulePreview(it.tag, img, previewSize());
    const name = el("div", { class: "tp-name" }, it.tag);
    const meta = el("div", { class: "tp-meta" }, (it.post_count ? "♥" + it.post_count : ""));
    // hover 操作按钮
    const blockBtn = el("button", {
        class: "tp-hover-btn tp-block", title: "加入黑名单并隐藏",
        onclick: (e) => { e.stopPropagation(); toggleBlacklist(it.tag); },
    }, "🚫");
    const favBtn = el("button", {
        class: "tp-hover-btn tp-fav" + (isFav ? " active" : ""), title: "收藏",
        onclick: (e) => { e.stopPropagation(); toggleFavorite({ tag: it.tag, category }); },
    }, isFav ? "★" : "☆");
    card.append(img, name, meta, blockBtn, favBtn);
    card.addEventListener("click", (e) => {
        if (e.ctrlKey || e.metaKey) {
            const url = `${DANBOORU_BASE}/posts?tags=${encodeURIComponent(it.tag)}`;
            window.open(url, "_blank", "noopener");
            return;
        }
        selectTag({ tag: it.tag, category });
    });
    return card;
}

function buildResultCard(item, isGacha) {
    const card = el("div", { class: "tp-res-card" });
    const img = el("img", { class: "tp-res-thumb", src: PLACEHOLDER, alt: item.tag });
    if (isGacha) img.dataset.gacha = "1";
    img.dataset.tag = item.tag;
    if (isGacha) schedulePreview(item.tag, img, 56);
    else schedulePreview(item.tag, img, 56);
    const info = el("div", { class: "tp-res-info" },
        el("div", { class: "tp-res-name", title: item.tag }, item.tag),
        el("div", { class: "tp-res-cat" }, CATEGORY_CN[item.category] || item.category || ""),
    );
    const del = el("button", { class: "tp-res-del", title: "移除", onclick: (e) => { e.stopPropagation(); if (isGacha) removeGacha(item.tag); else removeSelected(item.tag); } }, "✕");
    card.append(img, info, del);
    card.addEventListener("click", (e) => {
        if (e.ctrlKey || e.metaKey) { window.open(`${DANBOORU_BASE}/posts?tags=${encodeURIComponent(item.tag)}`, "_blank", "noopener"); }
    });
    return card;
}
function removeGacha(tag) {
    gachaState.resultTags = gachaState.resultTags.filter((t) => t.tag !== tag);
    serializeGacha();
    renderResult();
    refreshGachaPreview();
}

function buildListItemCard(item, { onAdd, onRemove, removeLabel, kind }) {
    const card = el("div", { class: "tp-list-card" });
    const info = el("div", { class: "tp-res-info" },
        el("div", { class: "tp-res-name", title: item.tag }, item.tag),
        el("div", { class: "tp-res-cat" }, CATEGORY_CN[item.category] || item.category || ""),
    );
    const addBtn = el("button", { class: "tp-list-btn", title: "加入选择", onclick: () => onAdd && onAdd(item) }, "＋选择");
    const rmBtn = el("button", { class: "tp-list-btn danger", title: removeLabel, onclick: () => onRemove && onRemove(item) }, removeLabel);
    card.append(info, addBtn, rmBtn);
    return card;
}

const PLACEHOLDER = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#16213e"/></svg>');

// ========== 渲染 ==========
function renderGallery() {
    if (!mainScroll) return;
    const cat = state.currentTab;
    if (!GALLERY_TABS.includes(cat)) { mainScroll.innerHTML = ""; return; }
    const ts = state.tabState[cat];
    mainScroll.innerHTML = "";
    if (ts.loading) { mainScroll.appendChild(el("div", { class: "tp-empty" }, "加载中…")); updatePager(); return; }
    const items = (ts.items || []).filter((it) => !state.blacklist.has(it.tag));
    if (!items.length) {
        mainScroll.appendChild(el("div", { class: "tp-empty" }, ts.query ? `未找到「${ts.query}」相关标签` : "暂无数据，试试搜索或翻页"));
        updatePager();
        return;
    }
    const grid = el("div", { class: "tp-grid" });
    items.forEach((it) => grid.appendChild(buildGalleryCard(it, cat)));
    mainScroll.appendChild(grid);
    updatePager();
}
function renderGallerySelectionStates() {
    if (!mainScroll) return;
    mainScroll.querySelectorAll(".tp-card").forEach((card) => {
        const name = card.querySelector(".tp-name")?.textContent;
        if (name == null) return;
        card.classList.toggle("selected", state.selectedMap.has(name));
        const fav = card.querySelector(".tp-fav");
        if (fav) fav.classList.toggle("active", state.favorites.has(name));
    });
}
function renderGachaPanel() {
    if (!mainScroll) return;
    mainScroll.innerHTML = "";
    const wrap = el("div", { class: "tp-gacha" });
    wrap.appendChild(el("div", { class: "tp-gacha-hint" }, "每类可独立设置来源（实时=Danbooru 随机 / 候选=从当前页抽）与数量；「重抽」仅重roll该分类，其余保留。"));

    const rows = el("div", { class: "tp-gacha-rows" });
    for (const key of ["artist", "character", "copyright"]) {
        const cfg = state.gachaConfig[key];
        const label = CATEGORY_CN[key] || key;
        const srcSel = el("select", { class: "tp-mini-select" },
            el("option", { value: "live" }, "实时"),
            el("option", { value: "candidate" }, "候选"),
        );
        srcSel.value = cfg.source;
        srcSel.addEventListener("change", () => { cfg.source = srcSel.value; });
        const num = el("input", { class: "tp-mini-num", type: "number", min: "0", max: "30", value: String(cfg.n) });
        num.addEventListener("change", () => { cfg.n = Math.max(0, Math.min(30, parseInt(num.value, 10) || 0)); num.value = String(cfg.n); });
        const reroll = el("button", { class: "tp-mini-btn", onclick: () => gachaReroll(key) }, "重抽");
        const row = el("div", { class: "tp-gacha-row" },
            el("div", { class: "tp-gacha-rowlabel" }, label),
            srcSel, el("div", { class: "tp-gacha-rowlabel" }, "×"), num, reroll,
        );
        rows.appendChild(row);
    }
    wrap.appendChild(rows);

    const actions = el("div", { class: "tp-gacha-actions" },
        el("button", { class: "tp-btn primary", onclick: () => runGachaGenerate() }, "按配置生成"),
        el("button", { class: "tp-btn", onclick: () => runGachaAllCandidate() }, "全部按当前页抽取"),
        el("button", { class: "tp-btn", onclick: () => clearGacha() }, "清空扭蛋"),
    );
    wrap.appendChild(actions);

    // 当前扭蛋结果预览
    const cur = el("div", { class: "tp-gacha-current" });
    cur.appendChild(el("div", { class: "tp-gacha-sub" }, "当前扭蛋结果"));
    const grid = el("div", { class: "tp-grid small" });
    gachaState.resultTags.forEach((t) => grid.appendChild(buildResultCard(t, true)));
    if (!gachaState.resultTags.length) grid.appendChild(el("div", { class: "tp-empty" }, "尚无扭蛋结果"));
    cur.appendChild(grid);
    wrap.appendChild(cur);

    mainScroll.appendChild(wrap);
    refreshGachaPreview();
    updatePager();
}
function renderBlacklist() {
    if (state.currentTab !== "blacklist") return;
    mainScroll.innerHTML = "";
    const head = el("div", { class: "tp-list-head" },
        el("div", {}, `黑名单（${state.blacklist.size}）`),
        el("button", { class: "tp-btn small", onclick: () => { if (confirm("确认清空黑名单？")) { state.blacklist.clear(); serializeBlacklist(); renderBlacklist(); } } }, "清空"),
    );
    mainScroll.appendChild(head);
    if (!state.blacklist.size) { mainScroll.appendChild(el("div", { class: "tp-empty" }, "黑名单为空")); return; }
    const list = el("div", { class: "tp-list" });
    [...state.blacklist].forEach((tag) => {
        list.appendChild(buildListItemCard({ tag, category: "" }, {
            onAdd: (it) => selectTag({ tag: it.tag, category: "tag" }),
            onRemove: (it) => toggleBlacklist(it.tag),
            removeLabel: "解除屏蔽",
        }));
    });
    mainScroll.appendChild(list);
}
function renderFavorites() {
    if (state.currentTab !== "favorites") return;
    mainScroll.innerHTML = "";
    const head = el("div", { class: "tp-list-head" },
        el("div", {}, `收藏（${state.favorites.size}）`),
        el("button", { class: "tp-btn small", onclick: () => { if (confirm("确认清空收藏？")) { state.favorites.clear(); serializeFavorites(); renderFavorites(); } } }, "清空"),
    );
    mainScroll.appendChild(head);
    if (!state.favorites.size) { mainScroll.appendChild(el("div", { class: "tp-empty" }, "收藏为空，画廊卡片悬停点 ☆ 即可收藏")); return; }
    const list = el("div", { class: "tp-list" });
    [...state.favorites.entries()].forEach(([tag, category]) => {
        list.appendChild(buildListItemCard({ tag, category }, {
            onAdd: (it) => selectTag({ tag: it.tag, category: it.category || "tag" }),
            onRemove: (it) => toggleFavorite({ tag: it.tag, category: it.category }),
            removeLabel: "取消收藏",
        }));
    });
    mainScroll.appendChild(list);
}

function renderResult() {
    if (!resultPanel) return;
    resultPanel.innerHTML = "";
    resultPanel.appendChild(el("div", { class: "tp-res-title" }, "结果"));
    // 已选
    const selSec = el("div", { class: "tp-res-section" });
    selSec.appendChild(el("div", { class: "tp-res-sub" }, `已选（${state.selectedMap.size}）`));
    const selGrid = el("div", { class: "tp-res-grid" });
    [...state.selectedMap.values()].forEach((t) => selGrid.appendChild(buildResultCard(t, false)));
    if (!state.selectedMap.size) selGrid.appendChild(el("div", { class: "tp-empty small" }, "点击画廊卡片选择"));
    selSec.appendChild(selGrid);
    resultPanel.appendChild(selSec);
    // 扭蛋
    const gSec = el("div", { class: "tp-res-section" });
    gSec.appendChild(el("div", { class: "tp-res-sub" }, `扭蛋（${gachaState.resultTags.length}）`));
    const gGrid = el("div", { class: "tp-res-grid" });
    gachaState.resultTags.forEach((t) => gGrid.appendChild(buildResultCard(t, true)));
    if (!gachaState.resultTags.length) gGrid.appendChild(el("div", { class: "tp-empty small" }, "扭蛋结果将显示在此"));
    gSec.appendChild(gGrid);
    resultPanel.appendChild(gSec);
    refreshGachaPreview();
}

function renderMain() {
    const cat = state.currentTab;
    if (cat === "gacha") renderGachaPanel();
    else if (cat === "blacklist") renderBlacklist();
    else if (cat === "favorites") renderFavorites();
    else if (cat === "settings") buildSettingsPanel();
    else renderGallery();
}

// 设置面板：缓存相关控件从节点外部 UI 移入此处管理
function buildSettingsPanel() {
    if (!mainScroll) return;
    mainScroll.innerHTML = "";
    const wrap = el("div", { class: "tp-gacha", style: "padding:16px 18px;max-width:560px;" });

    wrap.appendChild(el("div", { class: "tp-gacha-sub" }, "预览图缓存"));
    wrap.appendChild(el("div", { class: "tp-gacha-hint" }, "开启后预览图写入节点目录 preview_cache/，重启后保留；关闭则仅本次会话内存缓存。"));

    const cacheRow = el("div", { class: "tp-gacha-row" });
    const cacheChk = el("input", { type: "checkbox" });
    cacheChk.checked = !!getWidget(nodeRef, "cache_enabled", true);
    cacheChk.addEventListener("change", () => { setWidget(nodeRef, "cache_enabled", cacheChk.checked); flashStatus("缓存：" + (cacheChk.checked ? "开" : "关")); });
    cacheRow.append(el("div", { class: "tp-gacha-rowlabel" }, "缓存开关"), cacheChk);
    wrap.appendChild(cacheRow);

    const maxRow = el("div", { class: "tp-gacha-row" });
    const maxNum = el("input", { class: "tp-mini-num", type: "number", min: "10", max: "5000", step: "10", value: String(getWidget(nodeRef, "cache_max_items", 300)) });
    maxNum.addEventListener("change", () => { const v = Math.max(10, Math.min(5000, parseInt(maxNum.value, 10) || 300)); maxNum.value = String(v); setWidget(nodeRef, "cache_max_items", v); flashStatus("缓存文件数上限：" + v); });
    maxRow.append(el("div", { class: "tp-gacha-rowlabel" }, "文件数"), maxNum);
    wrap.appendChild(maxRow);

    wrap.appendChild(el("div", { class: "tp-gacha-sub", style: "margin-top:18px;" }, "外部随机"));
    const syncRow = el("div", { class: "tp-gacha-row" });
    const syncChk = el("input", { type: "checkbox" });
    syncChk.checked = !!getWidget(nodeRef, "sync_external_random", false);
    syncChk.addEventListener("change", () => { setWidget(nodeRef, "sync_external_random", syncChk.checked); flashStatus("外部随机同步：" + (syncChk.checked ? "开" : "关")); });
    syncRow.append(el("div", { class: "tp-gacha-rowlabel" }, "随机同步弹窗"), syncChk);
    wrap.appendChild(syncRow);
    wrap.appendChild(el("div", { class: "tp-gacha-hint" }, "开启：节点上「随机生成」=完全随机并同步到弹窗；关闭：按原方式随机且不主动同步弹窗。"));

    mainScroll.appendChild(wrap);
    updatePager();
}
function renderAll() { renderMain(); renderResult(); renderStatus(); }

function updateTabStyle() {
    for (const cat of TABS) {
        const t = tabEls[cat];
        if (!t) continue;
        const active = cat === state.currentTab;
        t.style.background = active ? COLORS.accent : "transparent";
        t.style.color = active ? "#fff" : COLORS.textDim;
        t.style.fontWeight = active ? "600" : "400";
    }
    // pager 仅画廊页显示
    if (pagerBar) pagerBar.style.display = GALLERY_TABS.includes(state.currentTab) ? "flex" : "none";
}
function switchTab(cat) {
    state.currentTab = cat;
    updateTabStyle();
    renderMain();
    renderResult();
    if (GALLERY_TABS.includes(cat) && !state.tabState[cat].items.length) doSearch(cat);
}

function updatePager() {
    if (!pagerBar) return;
    const cat = state.currentTab;
    if (!GALLERY_TABS.includes(cat)) { pagerBar.innerHTML = ""; return; }
    const ts = state.tabState[cat];
    pagerBar.innerHTML = "";
    const prev = el("button", { class: "tp-page-btn", onclick: () => { if (ts.page > 1) { ts.page--; doSearch(cat); } } }, "‹ 上一页");
    const info = el("div", { class: "tp-page-info" }, `第 ${ts.page} 页`);
    const next = el("button", { class: "tp-page-btn", onclick: () => { ts.page++; doSearch(cat); } }, "下一页 ›");
    pagerBar.append(prev, info, next);
}

function renderStatus() {
    if (!statusEl) return;
    statusEl.textContent = `已选 ${state.selectedMap.size} · 扭蛋 ${gachaState.resultTags.length} · 黑名单 ${state.blacklist.size} · 收藏 ${state.favorites.size}`;
}
let _flashTimer = null;
function flashStatus(msg) {
    if (!statusEl) return;
    const base = `已选 ${state.selectedMap.size} · 扭蛋 ${gachaState.resultTags.length} · 黑名单 ${state.blacklist.size} · 收藏 ${state.favorites.size}`;
    statusEl.textContent = msg + "   ｜   " + base;
    clearTimeout(_flashTimer);
    _flashTimer = setTimeout(renderStatus, 2500);
}

// ========== 扭蛋逻辑 ==========
async function gachaLive(catKey, n) {
    const cfg = GACHA_CATS[catKey];
    const blacklist = JSON.stringify([...state.blacklist]);
    const path = `/naiba/tag/gacha_partial?${cfg.param}=${n}&blacklist=${encodeURIComponent(blacklist)}`;
    const data = await apiGetJson(path);
    return (data.tags || []).map((t) => ({ tag: t.tag, category: t.category }));
}
function candidateSample(catKey, n) {
    const cfg = GACHA_CATS[catKey];
    const items = state.tabState[cfg.tabCat].items || [];
    const pool = items
        .map((it) => ({ tag: it.tag, category: catKey }))
        .filter((it) => !state.blacklist.has(it.tag))
        .filter((it) => !state.selectedMap.has(it.tag));
    const seen = new Set();
    const dedup = pool.filter((it) => { if (seen.has(it.tag)) return false; seen.add(it.tag); return true; });
    if (dedup.length <= n) return dedup;
    const arr = dedup.slice();
    for (let i = arr.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1));[arr[i], arr[j]] = [arr[j], arr[i]]; }
    return arr.slice(0, n);
}
async function runGachaGenerate() {
    const results = {};
    let shortfall = [];
    for (const key of ["artist", "character", "copyright"]) {
        const cfg = state.gachaConfig[key];
        if (cfg.n <= 0) { results[key] = []; continue; }
        if (cfg.source === "candidate") {
            const s = candidateSample(key, cfg.n);
            results[key] = s;
            if (s.length < cfg.n) shortfall.push(`${CATEGORY_CN[key]}候选仅${s.length}/${cfg.n}`);
        } else {
            const s = await gachaLive(key, cfg.n);
            results[key] = s;
            if (s.length < cfg.n) shortfall.push(`${CATEGORY_CN[key]}实只得${s.length}/${cfg.n}`);
        }
    }
    for (const key of ["artist", "character", "copyright"]) replaceGachaCategory(key, results[key].map((t) => t.tag));
    serializeGacha();
    setWidget(nodeRef, "gacha_mode", true);
    if (shortfall.length) flashStatus("部分不足：" + shortfall.join("，"));
    else flashStatus("扭蛋完成");
}
function runGachaAllCandidate() {
    // 全部类别用候选（当前页）抽取
    for (const key of ["artist", "character", "copyright"]) state.gachaConfig[key].source = "candidate";
    runGachaGenerate();
}
async function gachaReroll(catKey) {
    const cfg = state.gachaConfig[catKey];
    if (cfg.source === "candidate") replaceGachaCategory(catKey, candidateSample(catKey, cfg.n).map((t) => t.tag));
    else replaceGachaCategory(catKey, (await gachaLive(catKey, cfg.n)).map((t) => t.tag));
    flashStatus(`${CATEGORY_CN[catKey]} 重抽完成`);
}
function clearGacha() {
    gachaState.resultTags = [];
    serializeGacha();
    renderResult();
    refreshGachaPreview();
}

// ========== 外部随机 ==========
async function runExternalRandom(node) {
    const sync = !!getWidget(node, "sync_external_random", false);
    const resp = await api.fetchApi(`/naiba/tag/gacha_random?total=9`);
    const data = await resp.json();
    const tags = (data.tags || []).map((t) => ({ tag: t.tag || t, category: t.category || "" })).filter((x) => x.tag);
    gachaState.resultTags = tags.slice();
    serializeGacha();
    setWidget(node, "gacha_mode", true);
    const modalOpen = !!currentModal;
    if (sync || modalOpen) { renderResult(); refreshGachaPreview(); }
}

// ========== 恢复 ==========
function restoreFromNode(node) {
    state.selectedMap = new Map(parseSelection(getWidget(node, "selection_data", "{}")).map((s) => [s.tag, s]));
    gachaState.resultTags = parseGacha(getWidget(node, "gacha_data", "{}"));
    state.blacklist = new Set(parseList(getWidget(node, "blacklist_data", "{}"), BLACKLIST_CAP));
    state.favorites = parseFavs(getWidget(node, "favorites_data", "{}"));
}

// ========== 模态框 ==========
function createTagPickerModal(node) {
    if (currentModal) { currentModal.focus(); return; }

    const overlay = el("div", { class: "tp-overlay" });
    const modal = el("div", { class: "tp-modal" });

    // 标题栏
    const header = el("div", { class: "tp-header" },
        el("div", { class: "tp-title" }, "🎯 Naiba Tag Picker"),
        el("div", { class: "tp-close", onclick: () => closeModal() }, "✕"),
    );

    // 标签页
    const tabGroup = el("div", { class: "tp-tabs" });
    TABS.forEach((cat) => {
        const t = el("div", { class: "tp-tab", onclick: () => switchTab(cat) }, TAB_LABEL[cat]);
        tabEls[cat] = t;
        tabGroup.appendChild(t);
    });

    // 工具栏（搜索行 + 每页数量，仅画廊页有效）
    const toolbar = el("div", { class: "tp-toolbar" });
    const searchInput = el("input", { class: "tp-search", type: "text", placeholder: "搜索标签（回车搜索）" });
    const searchBtn = el("button", { class: "tp-btn small", onclick: () => { const cat = state.currentTab; if (GALLERY_TABS.includes(cat)) { state.tabState[cat].query = searchInput.value.trim(); state.tabState[cat].page = 1; doSearch(cat); } } }, "搜索");
    searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") searchBtn.click(); });
    const perPage = el("div", { class: "tp-perpage" }, "每页 ", (() => {
        const s = el("input", { class: "tp-mini-num", type: "number", min: "1", max: "100", value: String(getWidget(node, "max_images", 9)) });
        s.addEventListener("change", () => { const v = Math.max(1, Math.min(100, parseInt(s.value, 10) || 9)); s.value = String(v); setWidget(node, "max_images", v); if (GALLERY_TABS.includes(state.currentTab)) doSearch(state.currentTab); });
        return s;
    })());
    toolbar.append(searchInput, searchBtn, perPage);

    // 主体：左画廊 + 右结果
    const body = el("div", { class: "tp-body" });
    mainScroll = el("div", { class: "tp-main" });
    pagerBar = el("div", { class: "tp-pager" });
    const leftCol = el("div", { class: "tp-left" }, mainScroll, pagerBar);
    resultPanel = el("div", { class: "tp-result" });
    body.append(leftCol, resultPanel);

    // 底部状态栏
    statusEl = el("div", { class: "tp-status" });
    const applyBtn = el("button", { class: "tp-btn primary", onclick: () => { serializeSelection(); serializeGacha(); if (nodeRef) setWidget(nodeRef, "gacha_mode", gachaState.resultTags.length > 0); closeModal(); } }, "应用");

    modal.append(header, tabGroup, toolbar, body, el("div", { class: "tp-footer" }, statusEl, applyBtn));
    overlay.append(modal);
    document.body.appendChild(overlay);
    currentModal = overlay;

    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) closeModal(); });

    // 样式注入（仅一次）
    injectStyle();

    // 初始化
    restoreFromNode(node);
    updateTabStyle();
    renderStatus();
    switchTab("artist");
}
function closeModal() {
    if (currentModal) { currentModal.remove(); currentModal = null; }
    mainScroll = null; pagerBar = null; resultPanel = null; statusEl = null; tabEls = {}; gachaPanelEl = null;
    // 弹窗关闭后刷新节点上的已选摘要预览框（应用/取消关闭都会触发，读到的是最新控件值）
    if (nodeRef && nodeRef._updateTagPickerPreview) nodeRef._updateTagPickerPreview();
}

function injectStyle() {
    if (document.getElementById("tp-style-v2")) return;
    const css = `
.tp-overlay{position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:10000;display:flex;align-items:center;justify-content:center;}
.tp-modal{width:94vw;max-width:1280px;height:90vh;background:${COLORS.modalBg};border-radius:10px;border:1px solid ${COLORS.border};display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 48px rgba(0,0,0,.55);}
.tp-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};}
.tp-title{color:${COLORS.text};font-size:16px;font-weight:600;}
.tp-close{color:${COLORS.textDim};cursor:pointer;font-size:16px;padding:4px 8px;border-radius:4px;transition:.15s;}
.tp-close:hover{color:${COLORS.text};background:rgba(255,255,255,.1);}
.tp-tabs{display:flex;gap:2px;padding:8px 16px 0;background:${COLORS.headerBg};flex-wrap:wrap;}
.tp-tab{padding:7px 16px;border-radius:4px 4px 0 0;cursor:pointer;font-size:13px;color:${COLORS.textDim};transition:.15s;}
.tp-tab:hover{color:${COLORS.text};}
.tp-toolbar{display:flex;align-items:center;gap:8px;padding:10px 16px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};border-bottom:1px solid ${COLORS.border};flex-wrap:wrap;}
.tp-search{flex:1;min-width:160px;padding:7px 10px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:5px;color:${COLORS.text};font-size:12px;}
.tp-search:focus{outline:none;border-color:${COLORS.accent};}
.tp-perpage{display:flex;align-items:center;gap:6px;color:${COLORS.textDim};font-size:12px;}
.tp-body{display:flex;flex-direction:row;flex:1;min-height:0;}
.tp-left{display:flex;flex-direction:column;flex:1;min-width:0;}
.tp-main{flex:1;overflow-y:auto;padding:14px 16px;}
.tp-pager{display:flex;align-items:center;justify-content:center;gap:16px;padding:8px;border-top:1px solid ${COLORS.border};background:${COLORS.contentBg};}
.tp-page-btn{background:${COLORS.cardBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:5px;padding:5px 14px;cursor:pointer;font-size:12px;}
.tp-page-btn:hover{border-color:${COLORS.accent};}
.tp-page-info{color:${COLORS.textDim};font-size:12px;}
.tp-result{width:clamp(220px,22vw,320px);background:${COLORS.contentBg};border-left:1px solid ${COLORS.border};overflow-y:auto;padding:12px;}
.tp-res-title{color:${COLORS.text};font-size:13px;font-weight:600;margin-bottom:8px;}
.tp-res-sub{color:${COLORS.accentHover};font-size:12px;font-weight:500;margin:10px 0 6px;}
.tp-res-grid{display:flex;flex-direction:column;gap:6px;}
.tp-res-card{display:flex;align-items:center;gap:8px;background:${COLORS.cardBg};border:1px solid ${COLORS.cardBorder};border-radius:6px;padding:5px;transition:.15s;}
.tp-res-card:hover{border-color:${COLORS.accent};}
.tp-res-thumb{width:42px;height:42px;border-radius:4px;object-fit:cover;background:${COLORS.inputBg};flex-shrink:0;}
.tp-res-info{flex:1;min-width:0;}
.tp-res-name{color:${COLORS.text};font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.tp-res-cat{color:${COLORS.textDim};font-size:11px;}
.tp-res-del{background:none;border:none;color:${COLORS.danger};cursor:pointer;font-size:13px;padding:2px 6px;border-radius:4px;}
.tp-res-del:hover{background:rgba(255,107,107,.15);}
.tp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;}
.tp-grid.small{grid-template-columns:repeat(auto-fill,minmax(120px,1fr));}
.tp-card{position:relative;background:${COLORS.cardBg};border:1px solid ${COLORS.cardBorder};border-radius:8px;overflow:hidden;cursor:pointer;transition:transform .12s,border-color .15s;outline:none;}
.tp-card:hover{transform:translateY(-2px);border-color:${COLORS.accent};}
.tp-card.selected{border-color:${COLORS.success};box-shadow:0 0 0 2px rgba(46,213,115,.4);}
.tp-thumb{width:100%;aspect-ratio:1/1;object-fit:cover;display:block;background:${COLORS.inputBg};}
.tp-name{padding:6px 8px 2px;color:${COLORS.text};font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.tp-meta{padding:0 8px 6px;color:${COLORS.textDim};font-size:11px;}
.tp-hover-btn{position:absolute;top:6px;width:28px;height:28px;border-radius:50%;border:none;cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;opacity:0;transition:.15s;box-shadow:0 2px 6px rgba(0,0,0,.4);}
.tp-card:hover .tp-hover-btn,.tp-card:focus-within .tp-hover-btn,.tp-card:focus .tp-hover-btn{opacity:1;}
.tp-block{right:6px;background:${COLORS.danger};color:#fff;}
.tp-fav{right:40px;background:${COLORS.warning};color:#1a1a2e;}
.tp-fav.active{background:${COLORS.warning};}
.tp-empty{color:${COLORS.textDim};font-size:13px;padding:40px 10px;text-align:center;}
.tp-empty.small{padding:14px 6px;font-size:12px;}
.tp-btn{background:${COLORS.cardBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:6px;padding:8px 14px;cursor:pointer;font-size:12px;font-weight:500;transition:.15s;}
.tp-btn:hover{border-color:${COLORS.accent};}
.tp-btn.primary{background:${COLORS.accent};color:#fff;border-color:${COLORS.accent};}
.tp-btn.primary:hover{background:${COLORS.accentHover};}
.tp-btn.small{padding:6px 10px;font-size:12px;}
.tp-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 16px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};}
.tp-status{color:${COLORS.textDim};font-size:12px;flex:1;}
.tp-gacha{padding:4px;}
.tp-gacha-hint{color:${COLORS.textDim};font-size:12px;margin-bottom:10px;line-height:1.5;}
.tp-gacha-rows{display:flex;flex-direction:column;gap:8px;margin-bottom:12px;}
.tp-gacha-row{display:flex;align-items:center;gap:10px;}
.tp-gacha-rowlabel{color:${COLORS.text};font-size:13px;min-width:42px;}
.tp-mini-select{background:${COLORS.inputBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:5px;padding:6px 8px;font-size:12px;}
.tp-mini-num{width:56px;background:${COLORS.inputBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:5px;padding:6px;font-size:12px;}
.tp-mini-btn{background:${COLORS.cardBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:5px;padding:6px 12px;cursor:pointer;font-size:12px;}
.tp-mini-btn:hover{border-color:${COLORS.accent};}
.tp-gacha-actions{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;}
.tp-gacha-sub{color:${COLORS.accentHover};font-size:13px;font-weight:500;margin-bottom:8px;}
.tp-list-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;color:${COLORS.text};font-size:13px;}
.tp-list{display:flex;flex-direction:column;gap:6px;}
.tp-list-card{display:flex;align-items:center;gap:10px;background:${COLORS.cardBg};border:1px solid ${COLORS.cardBorder};border-radius:6px;padding:8px;}
.tp-list-card .tp-res-info{flex:1;}
.tp-list-btn{background:${COLORS.inputBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:5px;padding:5px 10px;cursor:pointer;font-size:12px;}
.tp-list-btn:hover{border-color:${COLORS.accent};}
.tp-list-btn.danger:hover{border-color:${COLORS.danger};color:${COLORS.danger};}
@media (max-width:780px){
  .tp-body{flex-direction:column;}
  .tp-result{width:100%;border-left:none;border-top:1px solid ${COLORS.border};max-height:38vh;}
}
`;
    const style = document.createElement("style");
    style.id = "tp-style-v2";
    style.textContent = css;
    document.head.appendChild(style);
}

// ========== 注册扩展 ==========
app.registerExtension({
    name: "naiba.TagPicker",

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "NaibaTagPicker") return;
        const origOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            const node = this;
            nodeRef = node;   // 供弹窗（设置页等）读取当前节点

            // 隐藏由前端代理的控件；gacha_mode 为自动托管（随机生成=开，清除=关），不显示在节点上
            const hiddenWidgets = ["selection_data", "gacha_data", "gacha_mode",
                "cache_enabled", "cache_max_items", "sync_external_random",
                "blacklist_data", "favorites_data"];
            hiddenWidgets.forEach((name) => {
                const w = node.widgets?.find((x) => x.name === name);
                if (w) {
                    w.hidden = true;
                    if (w.inputEl) w.inputEl.style.display = "none";
                    if (w.element) w.element.style.display = "none";
                }
            });

            // 自动管理后端 gacha_mode：点击「随机生成」即开启扭蛋输出，清除时关闭
            const setGachaMode = (val) => {
                const w = node.widgets?.find((x) => x.name === "gacha_mode");
                if (w) w.value = val;
            };

            // 外部「随机生成」按钮：直接生成一组随机标签并实时显示（可反复点再生）
            const randomBtn = document.createElement("button");
            randomBtn.textContent = "随机生成";
            randomBtn.style.cssText = `
                width:100%;padding:8px;margin:8px 0 0;
                background:${COLORS.warning};color:#1a1a2e;
                border:none;border-radius:6px;cursor:pointer;
                font-size:12px;font-weight:600;transition:background 0.2s;
            `;
            randomBtn.addEventListener("mouseenter", () => { if (!randomBtn.disabled) randomBtn.style.background = "#ffbe3d"; });
            randomBtn.addEventListener("mouseleave", () => { if (!randomBtn.disabled) randomBtn.style.background = COLORS.warning; });
            randomBtn.addEventListener("click", async () => {
                randomBtn.disabled = true;
                const origText = randomBtn.textContent;
                randomBtn.textContent = "生成中…";
                try {
                    const resp = await api.fetchApi(`/naiba/tag/gacha_random?total=9`);
                    const data = await resp.json();
                    const tags = (data.tags || [])
                        .map((t) => typeof t === "string" ? { tag: t, category: "" } : t)
                        .filter((x) => x && x.tag);
                    const gw = node.widgets?.find((x) => x.name === "gacha_data");
                    if (gw) gw.value = JSON.stringify({ tags });
                    setGachaMode(true);
                    updatePreview();
                    if (node._tpSetGacha) node._tpSetGacha(tags);
                } catch (e) {
                    console.warn("[NaibaTagPicker] 外部随机生成失败:", e);
                } finally {
                    randomBtn.disabled = false;
                    randomBtn.textContent = origText;
                }
            });

            // 已选摘要预览区
            const previewArea = document.createElement("div");
            previewArea.style.cssText = `
                width:100%;min-height:54px;max-height:130px;background:${COLORS.inputBg};
                border:1px solid ${COLORS.border};border-radius:4px;
                margin:8px 0;padding:6px;overflow-y:auto;
                font-size:11px;color:${COLORS.text};
            `;

            // 兼容两种 selection 结构：v2 的 {selected:[...]} 与原版 {artist/character/ip:[...]}
            const updatePreview = () => {
                const w = node.widgets?.find((x) => x.name === "selection_data");
                const gw = node.widgets?.find((x) => x.name === "gacha_data");
                let html = "";
                try {
                    const data = JSON.parse(w?.value || "{}");
                    if (Array.isArray(data.selected) && data.selected.length) {
                        const names = data.selected.map((x) => (x && x.tag) || x).filter(Boolean);
                        html += `<div style="margin:2px 0;"><span style="color:${COLORS.accent};">已选 ${names.length}：</span>${names.join(", ")}</div>`;
                    } else {
                        const fmt = (label, arr) => (arr && arr.length)
                            ? `<div style="margin:2px 0;"><span style="color:${COLORS.accent};">${label} ${arr.length}：</span>${arr.map((x) => x.tag).filter(Boolean).join(", ")}</div>`
                            : "";
                        html += fmt("画师", data.artist || []) + fmt("角色", data.character || []) + fmt("IP", data.ip || []);
                    }
                } catch (e) { /* ignore */ }
                try {
                    const gd = JSON.parse(gw?.value || "{}");
                    const gt = Array.isArray(gd.tags) ? gd.tags.filter(Boolean) : [];
                    if (gt.length) {
                        const names = gt.map((x) => (x && x.tag) || x).join(", ");
                        html += `<div style="margin:2px 0;"><span style="color:${COLORS.success};">扭蛋标签 ${gt.length}：</span>${names}</div>`;
                    }
                } catch (e) { /* ignore */ }
                if (!html) {
                    html = `<div style="color:${COLORS.textDim};text-align:center;padding:14px;">点击下方按钮选择标签</div>`;
                }
                previewArea.innerHTML = html;
            };
            updatePreview();
            node._updateTagPickerPreview = updatePreview;

            // 打开画廊按钮
            const openBtn = document.createElement("button");
            openBtn.textContent = "打开标签画廊";
            openBtn.style.cssText = `
                width:100%;padding:10px;margin:8px 0;
                background:${COLORS.accent};color:white;
                border:none;border-radius:6px;cursor:pointer;
                font-size:13px;font-weight:500;transition:background 0.2s;
            `;
            openBtn.addEventListener("mouseenter", () => openBtn.style.background = COLORS.accentHover);
            openBtn.addEventListener("mouseleave", () => openBtn.style.background = COLORS.accent);
            openBtn.addEventListener("click", () => createTagPickerModal(node));

            // 清除已选按钮：清空 selection_data / gacha_data 控件与弹窗内存状态
            const clearBtn = document.createElement("button");
            clearBtn.textContent = "清除已选";
            clearBtn.style.cssText = `
                width:100%;padding:8px;margin:4px 0;
                background:${COLORS.danger};color:white;
                border:none;border-radius:6px;cursor:pointer;
                font-size:12px;font-weight:500;transition:background 0.2s;
            `;
            clearBtn.addEventListener("mouseenter", () => clearBtn.style.background = "#ff8585");
            clearBtn.addEventListener("mouseleave", () => clearBtn.style.background = COLORS.danger);
            clearBtn.addEventListener("click", () => {
                const sd = node.widgets?.find((x) => x.name === "selection_data");
                if (sd) sd.value = "{}";
                const gd = node.widgets?.find((x) => x.name === "gacha_data");
                if (gd) gd.value = JSON.stringify({ tags: [] });
                setGachaMode(false);
                if (node._tpClearSelection) node._tpClearSelection();
                updatePreview();
            });

            const container = document.createElement("div");
            container.style.cssText = "display:flex;flex-direction:column;gap:4px;width:100%;box-sizing:border-box;";
            container.appendChild(randomBtn);
            container.appendChild(previewArea);
            container.appendChild(clearBtn);
            container.appendChild(openBtn);

            const domWidget = node.addDOMWidget("tag_picker_container", "TAG_PICKER_CONTAINER", container, {
                getValue() { return ""; },
                setValue() {},
            });

            // 修复：ComfyUI 会给 DOM 面板注入 h-full，父容器初始高度 0 时面板塌缩，
            // 导致按钮溢出节点黑框。强制按内容真实高度展开，节点边框随内容自适应。
            const panelEl = domWidget.element || container;
            [panelEl, container].forEach((elx) => {
                if (!elx) return;
                elx.classList.remove("h-full");
                elx.style.height = "auto";
                elx.style.minHeight = "max-content";
            });

            node.minWidth = 240;
            node.minHeight = 180;
        };
    },
});

function flashToast(node, msg) {
    const t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = "position:fixed;left:50%;top:20px;transform:translateX(-50%);background:#6c5ce7;color:#fff;padding:8px 16px;border-radius:6px;z-index:20000;font-size:12px;";
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 1500);
}
