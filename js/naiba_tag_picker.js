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
const GALLERY_TABS = ["artist", "character", "ip", "tag", "ip_char"];
const TABS = ["artist", "character", "ip", "tag", "ip_char", "gacha", "blacklist", "favorites", "settings"];
const TAB_LABEL = { artist: "画师", character: "角色", ip: "IP", tag: "标签", ip_char: "作品角色", gacha: "扭蛋", blacklist: "黑名单", favorites: "收藏", settings: "设置" };
const CATEGORY_CN = { artist: "画师", character: "角色", copyright: "IP", tag: "标签", character_ip: "作品角色" };
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
        artist: { source: "live", n: 1 },
        character: { source: "live", n: 0 },
        copyright: { source: "live", n: 0 },
    },
    tabState: {
        artist: { items: [], page: 1, loading: false, seq: 0, query: "", single: false },
        character: { items: [], page: 1, loading: false, seq: 0, query: "", single: false },
        ip: { items: [], page: 1, loading: false, seq: 0, query: "", single: false },
        tag: { items: [], page: 1, loading: false, seq: 0, query: "", single: false },
    ip_char: { items: [], page: 1, loading: false, seq: 0, query: "", single: false, ip: "" },
    },
    currentTab: "artist",
};
const gachaState = { resultTags: [] }; // [{tag, category}]
let nodeRef = null;

// ========== DOM 引用 ==========
let mainScroll = null;
let pagerBar = null;
let resultPanel = null;
let tabEls = {};
let gachaPanelEl = null;
let gachaCurrentGrid = null;   // 扭蛋主面板中「当前扭蛋结果」的 grid，用于即时刷新
let toolbarEl = null;           // 搜索工具栏，扭蛋/设置分页隐藏
let searchInputEl = null;       // 搜索输入框引用，供分页切换时同步关键字
let listFilter = "";            // 黑名单/收藏分页的搜索关键字

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
function cacheMax() { return parseInt(getWidget(nodeRef, "cache_max_mb", 500), 10) || 500; }

// ========== 页面关闭时停止预加载 ==========
window.addEventListener('beforeunload', () => {
    try {
        fetch('/naiba/tag/preload?action=stop', { keepalive: true });
    } catch (e) { /* ignore */ }
});

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
}
function removeSelected(tag) {
    state.selectedMap.delete(tag);
    serializeSelection();
    renderGallerySelectionStates();
    renderResult();
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
    refreshGachaCurrent();
    refreshGachaPreview();
}
function setGachaAll(tags, { syncModal = true } = {}) {
    gachaState.resultTags = tags.map((t) => ({ tag: t.tag || t, category: t.category || "" }));
    serializeGacha();
    if (syncModal) { renderResult(); refreshGachaCurrent(); refreshGachaPreview(); }
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
    const limit = Math.max(1, parseInt(getWidget(nodeRef, "max_images", 9), 10) || 9);
    // 画师页支持「仅单画师」：用 name_matches 收紧；这里直接走 search
    const path = `/naiba/tag/search?q=${encodeURIComponent(q)}&cat=${encodeURIComponent(category)}&limit=${encodeURIComponent(limit)}&page=${ts.page}&cache=${cacheOn()}&max=${cacheMax()}`;
    try {
        const data = await apiGetJson(path);
        if (seq !== ts.seq) return; // 过期请求，丢弃
        ts.items = (data.items || []).map((it) => ({ id: it.id, tag: it.tag, post_count: it.post_count, category: it.category, preview_url: it.preview_url, source_url: it.source_url }));
        // 当页返回数达到请求的 limit，说明可能还有下一页
        ts.hasMore = (ts.items.length >= limit);
    } catch (e) {
        if (seq !== ts.seq) return;
        ts.items = [];
        ts.hasMore = false;
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
    if (cat === "ip") {
        const viewBtn = el("button", {
            class: "tp-hover-btn tp-view-char", title: "查看该 IP 下的角色",
            onclick: (e) => {
                e.stopPropagation();
                state.tabState.ip_char.ip = it.tag;
                state.tabState.ip_char.page = 1;
                switchTab("ip_char");
                doSearchIpCharacters();
            },
        }, "👥");
        card.append(viewBtn);
    }
    card.addEventListener("click", (e) => {
        if (e.ctrlKey || e.metaKey) {
            const url = `${DANBOORU_BASE}/posts?tags=${encodeURIComponent(it.tag)}`;
            window.open(url, "_blank", "noopener");
            return;
        }
            if (cat === "ip_char") {
                const ip = state.tabState.ip_char.ip;
                const paired = ip ? `${it.tag}（${ip}）` : it.tag;
                selectTag({ tag: paired, category: "character_ip" });
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
    if (isGacha) {
        // 扭蛋结果卡片：按钮定位与画师分页一致 —— 删除(✕)左上，黑名单/收藏右上
        const isFav = state.favorites.has(item.tag);
        const category = item.category || "tag";
        const blk = el("button", { class: "tp-hover-btn tp-block", title: "加入黑名单并从扭蛋结果移除", onclick: (e) => { e.stopPropagation(); toggleBlacklist(item.tag); removeGacha(item.tag); } }, "🚫");
        const fav = el("button", { class: "tp-hover-btn tp-fav" + (isFav ? " active" : ""), title: "收藏", onclick: (e) => { e.stopPropagation(); toggleFavorite({ tag: item.tag, category }); if (currentModal) refreshGachaCurrent(); } }, isFav ? "★" : "☆");
        const del = el("button", { class: "tp-hover-btn tp-del", title: "移除", onclick: (e) => { e.stopPropagation(); removeGacha(item.tag); } }, "✕");
        card.append(img, info, blk, fav, del);
    } else {
        const del = el("button", { class: "tp-res-del", title: "移除", onclick: (e) => { e.stopPropagation(); removeSelected(item.tag); } }, "✕");
        card.append(img, info, del);
    }
    card.addEventListener("click", (e) => {
        if (e.ctrlKey || e.metaKey) { window.open(`${DANBOORU_BASE}/posts?tags=${encodeURIComponent(item.tag)}`, "_blank", "noopener"); }
    });
    return card;
}
function removeGacha(tag) {
    gachaState.resultTags = gachaState.resultTags.filter((t) => t.tag !== tag);
    serializeGacha();
    renderResult();
    refreshGachaCurrent();
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
    const hint = el("div", { class: "tp-gacha-hint" });
    hint.innerHTML = "每个分类单独选 <b>抽取方式</b> 和 <b>数量</b>：<br>· 全库随机：从 Danbooru 整个标签库随机取<br>· 当前页：从你正在看的画廊页里已有的标签随机取<br>点「重抽」只重摇这一分类，其余结果保留。";
    wrap.appendChild(hint);

    const rows = el("div", { class: "tp-gacha-rows" });
    for (const key of ["artist", "character", "copyright"]) {
        const cfg = state.gachaConfig[key];
        const label = CATEGORY_CN[key] || key;
        const srcSel = el("select", { class: "tp-mini-select" },
            el("option", { value: "live" }, "全库随机"),
            el("option", { value: "candidate" }, "当前页"),
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
        el("button", { class: "tp-btn", onclick: () => runGachaAllCandidate() }, "全部用当前页"),
        el("button", { class: "tp-btn", onclick: () => clearGacha() }, "清空扭蛋"),
    );
    wrap.appendChild(actions);

    // 当前扭蛋结果预览
    const cur = el("div", { class: "tp-gacha-current" });
    cur.appendChild(el("div", { class: "tp-gacha-sub" }, "当前扭蛋结果"));
    const grid = el("div", { class: "tp-grid small gacha-big" });
    gachaCurrentGrid = grid;   // 保存引用，供 clearGacha/setGachaAll 等即时刷新
    gachaState.resultTags.forEach((t) => grid.appendChild(buildResultCard(t, true)));
    if (!gachaState.resultTags.length) grid.appendChild(el("div", { class: "tp-empty" }, "尚无扭蛋结果"));
    cur.appendChild(grid);
    wrap.appendChild(cur);

    mainScroll.appendChild(wrap);
    refreshGachaCurrent();
    refreshGachaPreview();
    updatePager();
}

// 即时刷新扭蛋主面板里的「当前扭蛋结果」预览（无需切走再切回）
function refreshGachaCurrent() {
    if (!gachaCurrentGrid) return;
    gachaCurrentGrid.innerHTML = "";
    if (!gachaState.resultTags.length) {
        gachaCurrentGrid.appendChild(el("div", { class: "tp-empty" }, "尚无扭蛋结果"));
    } else {
        gachaState.resultTags.forEach((t) => gachaCurrentGrid.appendChild(buildResultCard(t, true)));
    }
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
    const tags = [...state.blacklist].filter((t) => !listFilter || t.toLowerCase().includes(listFilter));
    if (!tags.length) { mainScroll.appendChild(el("div", { class: "tp-empty" }, listFilter ? `未找到「${listFilter}」` : "黑名单为空")); return; }
    const list = el("div", { class: "tp-list" });
    tags.forEach((tag) => {
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
    const entries = [...state.favorites.entries()].filter(([tag]) => !listFilter || tag.toLowerCase().includes(listFilter));
    if (!entries.length) { mainScroll.appendChild(el("div", { class: "tp-empty" }, listFilter ? `未找到「${listFilter}」` : "收藏为空")); return; }
    const list = el("div", { class: "tp-list" });
    entries.forEach(([tag, category]) => {
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

    wrap.appendChild(el("div", { class: "tp-gacha-sub" }, "本地缓存"));
    wrap.appendChild(el("div", { class: "tp-gacha-hint" }, "开启后预览图和标签搜索结果写入 preview_cache/ 目录，重启后保留；关闭则仅本次会话内存缓存。"));

    const cacheRow = el("div", { class: "tp-gacha-row" });
    const cacheChk = el("input", { type: "checkbox" });
    cacheChk.checked = !!getWidget(nodeRef, "cache_enabled", true);
    cacheChk.addEventListener("change", () => { setWidget(nodeRef, "cache_enabled", cacheChk.checked); flashStatus("缓存：" + (cacheChk.checked ? "开" : "关")); });
    cacheRow.append(el("div", { class: "tp-gacha-rowlabel" }, "缓存开关"), cacheChk);
    wrap.appendChild(cacheRow);

    const maxRow = el("div", { class: "tp-gacha-row" });
    const maxNum = el("input", { class: "tp-mini-num", type: "number", min: "100", max: "20000", step: "100", value: String(getWidget(nodeRef, "cache_max_mb", 500)) });
    maxNum.addEventListener("change", () => { const v = Math.max(100, Math.min(20000, parseInt(maxNum.value, 10) || 500)); maxNum.value = String(v); setWidget(nodeRef, "cache_max_mb", v); flashStatus("缓存大小上限：" + v + " MB"); refreshCacheStatus(); });
    maxRow.append(el("div", { class: "tp-gacha-rowlabel" }, "大小(MB)"), maxNum);
    wrap.appendChild(maxRow);

    // 缓存状态显示
    const cacheStatusRow = el("div", { class: "tp-gacha-row", style: "min-height:auto;padding:6px 0;" });
    const cacheStatusText = el("div", { style: `font-size:11px;color:${COLORS.muted};flex:1;` }, "加载中...");
    cacheStatusRow.append(el("div", { class: "tp-gacha-rowlabel" }, "当前用量"), cacheStatusText);
    wrap.appendChild(cacheStatusRow);

    // 清理缓存按钮
    const clearRow = el("div", { class: "tp-gacha-row", style: "min-height:auto;padding:6px 0;" });
    const clearBtn = el("button", {
        class: "tp-btn",
        style: `font-size:11px;padding:4px 12px;background:${COLORS.warn};color:#fff;border:1px solid ${COLORS.warn};border-radius:5px;cursor:pointer;`,
        onclick: async () => {
            clearBtn.textContent = "清理中...";
            clearBtn.disabled = true;
            try {
                const data = await apiGetJson(`/naiba/tag/cache_clear?cache=${cacheOn()}&max=${cacheMax()}`);
                flashStatus(data.message || "已清理");
                refreshCacheStatus();
            } catch (e) {
                flashStatus("清理失败");
            }
            clearBtn.textContent = "清理缓存";
            clearBtn.disabled = false;
        }
    }, "清理缓存");
    clearRow.append(el("div", { class: "tp-gacha-rowlabel" }, ""), clearBtn);
    wrap.appendChild(clearRow);

    // 刷新缓存状态
    async function refreshCacheStatus() {
        try {
            const data = await apiGetJson(`/naiba/tag/cache_status?cache=${cacheOn()}&max=${cacheMax()}`);
            if (data.enabled) {
                cacheStatusText.textContent = `${data.cached_mb} / ${data.max_mb} MB (${data.usage_pct}%, ${data.count} 文件)`;
                cacheStatusText.style.color = data.usage_pct > 90 ? COLORS.warn : COLORS.muted;
            } else {
                cacheStatusText.textContent = "未启用";
                cacheStatusText.style.color = COLORS.muted;
            }
        } catch (e) {
            cacheStatusText.textContent = "获取失败";
            cacheStatusText.style.color = COLORS.warn;
        }
    }
    refreshCacheStatus();

    mainScroll.appendChild(wrap);
    updatePager();
}
function renderAll() { renderMain(); renderResult(); }

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
    // 搜索工具栏：仅画廊/黑名单/收藏分页显示；扭蛋与设置分页无意义，隐藏
    if (toolbarEl) toolbarEl.style.display = (state.currentTab === "gacha" || state.currentTab === "settings") ? "none" : "flex";
}
function switchTab(cat) {
    state.currentTab = cat;
    updateTabStyle();
    // 进入黑名单/收藏时，把搜索框显示与当前过滤关键字同步
    if (searchInputEl && (cat === "blacklist" || cat === "favorites")) searchInputEl.value = listFilter;
    renderMain();
    renderResult();
    if (cat === "ip_char") {
        if (!state.tabState.ip_char.ip) { flashStatus("请先在 IP 页点「查看角色」"); renderGallery(); return; }
        if (!state.tabState.ip_char.items.length) doSearchIpCharacters();
    } else if (GALLERY_TABS.includes(cat) && !state.tabState[cat].items.length) {
        doSearch(cat);
    }
}

async function doSearchIpCharacters() {
    const ts = state.tabState.ip_char;
    if (!ts.ip) { flashStatus("请先在 IP 页点「查看角色」"); return; }
    ts.loading = true;
    if (state.currentTab === "ip_char") renderGallery();
    const seq = ++ts.seq;
    const max = Math.max(1, parseInt(getWidget(nodeRef, "max_images", 9), 10) || 9);
    const path = `/naiba/tag/ip_characters?ip=${encodeURIComponent(ts.ip)}&limit=${max}&page=${ts.page}&cache=${cacheOn()}&max=${cacheMax()}`;
    try {
        const data = await apiGetJson(path);
        if (seq !== ts.seq) return;
        ts.items = (data.items || []).map((it) => ({
            id: it.id, tag: it.tag, post_count: it.post_count, category: it.category,
            preview_url: it.preview_url, source_url: it.source_url,
        }));
        ts.hasMore = (ts.items.length >= max);
        if (data.auth_required) flashStatus("Gelbooru 匿名无权限，请在节点填 API Key/User ID");
    } catch (e) {
        if (seq !== ts.seq) return;
        ts.items = [];
        ts.hasMore = false;
        flashStatus("IP角色搜索失败：" + (e && e.message ? e.message : e));
    } finally {
        ts.loading = false;
        if (seq === ts.seq && state.currentTab === "ip_char") renderGallery();
    }
}

function updatePager() {
    if (!pagerBar) return;
    const cat = state.currentTab;
    if (!GALLERY_TABS.includes(cat)) { pagerBar.innerHTML = ""; return; }
    const ts = state.tabState[cat];
    pagerBar.innerHTML = "";
    const prev = el("button", { class: "tp-page-btn", onclick: () => {
        if (cat === "ip_char") { if (ts.page > 1) { ts.page--; doSearchIpCharacters(); } }
        else if (ts.page > 1) { ts.page--; doSearch(cat); }
    } }, "‹ 上一页");
    const info = el("div", { class: "tp-page-info" }, `第 ${ts.page} 页`);
    const more = !!ts.hasMore;
    const next = el("button", { class: "tp-page-btn" + (more ? "" : " disabled"), onclick: () => {
        if (!more) return;
        if (cat === "ip_char") { ts.page++; doSearchIpCharacters(); }
        else { ts.page++; doSearch(cat); }
    } }, "下一页 ›");
    pagerBar.append(prev, info, next);
}

let _flashTimer = null;
function flashStatus(msg) {
    if (!currentModal) return;
    let t = currentModal.querySelector(".tp-toast");
    if (!t) { t = el("div", { class: "tp-toast" }); currentModal.appendChild(t); }
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(_flashTimer);
    _flashTimer = setTimeout(() => { if (t) t.classList.remove("show"); }, 2500);
}

// ========== 扭蛋逻辑 ==========
async function gachaLive(catKey, n) {
    const cfg = GACHA_CATS[catKey];
    const blacklist = JSON.stringify([...state.blacklist]);
    const path = `/naiba/tag/gacha_partial?${cfg.param}=${n}&blacklist=${encodeURIComponent(blacklist)}`;
    const data = await apiGetJson(path);
    return (data.tags || []).map((t) => ({ tag: t.tag, category: t.category }));
}
// 把总数 total 随机拆成 画师(a)/角色(c)/IP(i) 三个非负整数，三者之和 = total
function splitTotal(n) {
    n = Math.max(0, n | 0);
    const a = Math.floor(Math.random() * (n + 1));
    const c = Math.floor(Math.random() * (n - a + 1));
    const i = n - a - c;
    return { a, c, i };
}
// 按总数随机拆分到三类并取标签（各自独立随机，和 = total），替代原「混合随机」
async function fetchGachaByTotal(total) {
    const { a, c, i } = splitTotal(total);
    const blacklist = JSON.stringify([...state.blacklist]);
    const path = `/naiba/tag/gacha_partial?artist=${a}&character=${c}&copyright=${i}&blacklist=${encodeURIComponent(blacklist)}`;
    const data = await apiGetJson(path);
    return (data.tags || []).map((t) => ({ tag: t.tag || t, category: t.category || "" })).filter((x) => x.tag);
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
            if (s.length < cfg.n) shortfall.push(`${CATEGORY_CN[key]}当前页仅${s.length}/${cfg.n}`);
        } else {
            const s = await gachaLive(key, cfg.n);
            results[key] = s;
            if (s.length < cfg.n) shortfall.push(`${CATEGORY_CN[key]}全库只得${s.length}/${cfg.n}`);
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
    refreshGachaCurrent();
    refreshGachaPreview();
}

// ========== 外部随机（双向同步） ==========
    async function runExternalRandom(node) {
        const total = (node && node._randomTotal) ? node._randomTotal : 9;
        const tags = await fetchGachaByTotal(total);
        gachaState.resultTags = tags.slice();
        serializeGacha();
        setWidget(node, "gacha_mode", true);
        if (currentModal) { renderResult(); refreshGachaCurrent(); refreshGachaPreview(); }
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
    // D 站状态灯
    const statusLight = el("div", { class: "tp-status-light", title: "D站: 检测中..." });
    statusLight.style.cssText = `
        width: 10px; height: 10px; border-radius: 50%;
        background: ${COLORS.muted}; transition: background 0.3s, box-shadow 0.3s;
        cursor: default; flex-shrink: 0;
    `;
    let danbooruOnline = null; // null=未知, true=在线, false=离线
    function updateStatusLight(online) {
        danbooruOnline = online;
        if (online === true) {
            statusLight.style.background = COLORS.success;
            statusLight.style.boxShadow = `0 0 6px ${COLORS.success}`;
            statusLight.title = "D站: 已连接";
        } else if (online === false) {
            statusLight.style.background = COLORS.error;
            statusLight.style.boxShadow = `0 0 6px ${COLORS.error}`;
            statusLight.title = "D站: 未连接";
        } else {
            statusLight.style.background = COLORS.muted;
            statusLight.style.boxShadow = "none";
            statusLight.title = "D站: 检测中...";
        }
    }
    // 轮询 D 站状态
    async function checkDanbooruStatus() {
        try {
            const data = await apiGetJson("/naiba/tag/status");
            updateStatusLight(data.online === true);
        } catch (e) {
            updateStatusLight(false);
        }
    }
    // 打开弹窗时首次探测，之后每 15s 轮询
    checkDanbooruStatus();
    const statusInterval = setInterval(checkDanbooruStatus, 15000);

    // 预加载状态
    const preloadStatusEl = el("div", { style: `font-size:11px;color:${COLORS.muted};white-space:nowrap;` }, "");
    let preloadInterval = null;
    async function checkPreloadStatus() {
        try {
            const data = await apiGetJson(`/naiba/tag/preload?action=status&cache=${cacheOn()}&max=${cacheMax()}`);
            if (data.running) {
                preloadStatusEl.textContent = `缓存预加载: ${data.progress}/${data.total} (${data.cached_mb}/${data.max_mb}MB)`;
                preloadStatusEl.style.color = COLORS.accent;
            } else if (data.message) {
                preloadStatusEl.textContent = data.message;
                preloadStatusEl.style.color = COLORS.muted;
                if (preloadInterval) { clearInterval(preloadInterval); preloadInterval = null; }
            }
        } catch (e) { /* ignore */ }
    }
    // 自动启动预加载
    async function startPreload() {
        try {
            await apiGetJson(`/naiba/tag/preload?action=start&cache=${cacheOn()}&max=${cacheMax()}`);
            checkPreloadStatus();
            preloadInterval = setInterval(checkPreloadStatus, 2000);
        } catch (e) { /* ignore */ }
    }
    startPreload();

    const header = el("div", { class: "tp-header" },
        el("div", { class: "tp-title" }, "🎯 Naiba Tag Picker"),
        el("div", { class: "tp-header-right", style: "display:flex;align-items:center;gap:12px;" },
            preloadStatusEl,
            statusLight,
            el("div", { class: "tp-close", onclick: () => { clearInterval(statusInterval); if (preloadInterval) clearInterval(preloadInterval); closeModal(); } }, "✕"),
        ),
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
    const searchBtn = el("button", { class: "tp-btn small", onclick: () => {
        const cat = state.currentTab;
        if (cat === "ip_char") {
            state.tabState.ip_char.ip = searchInput.value.trim() || state.tabState.ip_char.ip;
            state.tabState.ip_char.page = 1;
            doSearchIpCharacters();
            return;
        }
        if (GALLERY_TABS.includes(cat)) {
            state.tabState[cat].query = searchInput.value.trim(); state.tabState[cat].page = 1; doSearch(cat);
        } else if (cat === "blacklist" || cat === "favorites") {
            listFilter = searchInput.value.trim().toLowerCase(); renderMain();
        }
    } }, "搜索");
    searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") searchBtn.click(); });
    // 「默认」按钮：清空搜索词，恢复该分类的默认（热门）标签列表，免去手动搜空白的奇怪交互
    const defaultBtn = el("button", { class: "tp-btn small", title: "清空搜索，恢复默认标签列表", onclick: () => {
        const cat = state.currentTab;
        if (cat === "ip_char") {
            state.tabState.ip_char.page = 1;
            searchInput.value = state.tabState.ip_char.ip || "";
            doSearchIpCharacters();
            return;
        }
        if (GALLERY_TABS.includes(cat)) {
            searchInput.value = ""; state.tabState[cat].query = ""; state.tabState[cat].page = 1; doSearch(cat);
        } else if (cat === "blacklist" || cat === "favorites") {
            searchInput.value = ""; listFilter = ""; renderMain();
        }
    } }, "默认");
    const perPage = el("div", { class: "tp-perpage" }, "每页 ", (() => {
        const s = el("input", { class: "tp-mini-num", type: "number", min: "1", max: "100", value: String(getWidget(node, "max_images", 9)) });
        s.addEventListener("change", () => { const v = Math.max(1, Math.min(100, parseInt(s.value, 10) || 9)); s.value = String(v); setWidget(node, "max_images", v); if (GALLERY_TABS.includes(state.currentTab)) doSearch(state.currentTab); });
        return s;
    })());
    toolbar.append(searchInput, defaultBtn, searchBtn, perPage);
    toolbarEl = toolbar;   // 保存引用，供 updateTabStyle 按分页显隐
    searchInputEl = searchInput;   // 保存引用，供分页切换时同步关键字

    // 主体：左画廊 + 右结果
    const body = el("div", { class: "tp-body" });
    mainScroll = el("div", { class: "tp-main" });
    pagerBar = el("div", { class: "tp-pager" });
    const leftCol = el("div", { class: "tp-left" }, mainScroll, pagerBar);
    resultPanel = el("div", { class: "tp-result" });
    body.append(leftCol, resultPanel);

    // 底部：仅保留「应用」按钮（原状态栏计数不同步，已移除，临时提示改用浮动 toast）
    const applyBtn = el("button", { class: "tp-btn primary", onclick: () => { serializeSelection(); serializeGacha(); if (nodeRef) setWidget(nodeRef, "gacha_mode", gachaState.resultTags.length > 0); closeModal(); } }, "应用");

    modal.append(header, tabGroup, toolbar, body, el("div", { class: "tp-footer" }, applyBtn));
    overlay.append(modal);
    document.body.appendChild(overlay);
    currentModal = overlay;

    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) closeModal(); });

    // 样式注入（仅一次）
    injectStyle();

    // 初始化
    restoreFromNode(node);
    updateTabStyle();

    // 设置双向同步回调：节点「随机生成」按钮自动同步到弹窗
    node._tpSetGacha = (tags) => {
        gachaState.resultTags = tags.slice();
        serializeGacha();
        if (resultPanel) renderResult();
        refreshGachaCurrent();
        refreshGachaPreview();
    };
    node._tpClearSelection = () => {
        gachaState = { randomMode: false, resultTags: [], banList: [], resultImages: {} };
        state.selection = {};
        serializeGacha();
        serializeAll();
        if (resultPanel) renderResult();
        renderMain();
        refreshGachaCurrent();
        refreshGachaPreview();
    };

    // 记住上次所在分页：再次打开时停留在关闭前的 tab（首次或无效时兜底 artist）
    switchTab(TABS.includes(state.currentTab) ? state.currentTab : "artist");
}
function closeModal() {
    if (nodeRef) { nodeRef._tpSetGacha = null; nodeRef._tpClearSelection = null; }
    if (currentModal) { currentModal.remove(); currentModal = null; }
    mainScroll = null; pagerBar = null; resultPanel = null; tabEls = {}; gachaPanelEl = null; toolbarEl = null; searchInputEl = null;
    // 弹窗关闭后刷新节点上的已选摘要预览框（应用/取消关闭都会触发，读到的是最新控件值）
    if (nodeRef && nodeRef._updateTagPickerPreview) nodeRef._updateTagPickerPreview();
}

function injectStyle() {
    if (document.getElementById("tp-style-v2")) return;
    const css = `
.tp-overlay{position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:10000;display:flex;align-items:center;justify-content:center;}
.tp-modal{width:94vw;max-width:1280px;height:90vh;background:${COLORS.modalBg};border-radius:10px;border:1px solid ${COLORS.border};display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 48px rgba(0,0,0,.55);}
.tp-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};}
.tp-status-light{animation:tp-status-breathe 1.6s ease-in-out infinite;}
@keyframes tp-status-breathe{0%,100%{opacity:1}50%{opacity:.55}}
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
/* 扭蛋当前结果：卡片放大至约 4 倍（缩略图 42px -> 168px），竖向布局，按钮同画师卡片角落定位 */
.tp-gacha-current .tp-grid.small.gacha-big{grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;}
.tp-gacha-current .tp-grid.small.gacha-big .tp-res-card{position:relative;overflow:hidden;flex-direction:column;align-items:stretch;text-align:center;padding:8px;gap:6px;}
.tp-gacha-current .tp-grid.small.gacha-big .tp-res-thumb{width:168px;height:168px;margin:0 auto;}
.tp-gacha-current .tp-grid.small.gacha-big .tp-res-info{min-width:0;}
.tp-gacha-current .tp-grid.small.gacha-big .tp-res-name{white-space:normal;word-break:break-all;}
.tp-gacha-current .tp-grid.small.gacha-big .tp-hover-btn{position:absolute;top:6px;width:28px;height:28px;border-radius:50%;border:none;cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;opacity:0;transition:.15s;box-shadow:0 2px 6px rgba(0,0,0,.4);}
.tp-gacha-current .tp-grid.small.gacha-big .tp-res-card:hover .tp-hover-btn,.tp-gacha-current .tp-grid.small.gacha-big .tp-res-card:focus-within .tp-hover-btn{opacity:1;}
.tp-gacha-current .tp-grid.small.gacha-big .tp-block{right:6px;background:${COLORS.danger};color:#fff;}
.tp-gacha-current .tp-grid.small.gacha-big .tp-fav{right:40px;background:${COLORS.textDim};color:#1a1a2e;}
.tp-gacha-current .tp-grid.small.gacha-big .tp-del{left:6px;background:${COLORS.danger};color:#fff;}
.tp-card{position:relative;background:${COLORS.cardBg};border:1px solid ${COLORS.cardBorder};border-radius:8px;overflow:hidden;cursor:pointer;transition:transform .12s,border-color .15s;outline:none;}
.tp-card:hover{transform:translateY(-2px);border-color:${COLORS.accent};}
.tp-card.selected{border-color:${COLORS.success};box-shadow:0 0 0 2px rgba(46,213,115,.4);}
.tp-thumb{width:100%;aspect-ratio:1/1;object-fit:cover;display:block;background:${COLORS.inputBg};}
.tp-name{padding:6px 8px 2px;color:${COLORS.text};font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.tp-meta{padding:0 8px 6px;color:${COLORS.textDim};font-size:11px;}
.tp-hover-btn{position:absolute;top:6px;width:28px;height:28px;border-radius:50%;border:none;cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;opacity:0;transition:.15s;box-shadow:0 2px 6px rgba(0,0,0,.4);}
.tp-card:hover .tp-hover-btn,.tp-card:focus-within .tp-hover-btn,.tp-card:focus .tp-hover-btn{opacity:1;}
.tp-block{right:6px;background:${COLORS.danger};color:#fff;}
.tp-fav{right:40px;background:${COLORS.textDim};color:#1a1a2e;}
.tp-view-char{left:6px;bottom:6px;background:${COLORS.accent};color:#fff;}
.tp-fav.active{background:${COLORS.warning};}
.tp-empty{color:${COLORS.textDim};font-size:13px;padding:40px 10px;text-align:center;}
.tp-empty.small{padding:14px 6px;font-size:12px;}
.tp-btn{background:${COLORS.cardBg};color:${COLORS.text};border:1px solid ${COLORS.border};border-radius:6px;padding:8px 14px;cursor:pointer;font-size:12px;font-weight:500;transition:.15s;}
.tp-btn:hover{border-color:${COLORS.accent};}
.tp-btn.primary{background:${COLORS.accent};color:#fff;border-color:${COLORS.accent};}
.tp-btn.primary:hover{background:${COLORS.accentHover};}
.tp-btn.small{padding:6px 10px;font-size:12px;}
.tp-footer{display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:10px 16px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};}
.tp-toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%) translateY(10px);background:rgba(0,0,0,.82);color:#fff;padding:8px 14px;border-radius:6px;font-size:12px;opacity:0;pointer-events:none;transition:.2s;z-index:9999;max-width:80vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.tp-toast.show{opacity:1;transform:translateX(-50%) translateY(0);}
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
                "cache_enabled", "cache_max_mb",
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
                flex:1;padding:8px;margin:8px 0 0 0;
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
                    const tags = await fetchGachaByTotal(node._randomTotal || 9);
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

            // 随机数目（组数：每组=画师+角色+IP，实际标签数=组数×3）；放在黄色按钮右侧
            const randomCount = document.createElement("input");
            randomCount.type = "number";
            randomCount.min = "1";
            randomCount.max = "30";
            randomCount.value = "9";
            randomCount.title = "随机标签总数：将随机分配给 画师 / 角色 / IP 三类，三者数量之和 = 该值（各自独立随机）";
            randomCount.style.cssText = `
                width:64px;padding:8px 4px;margin:8px 0 0 6px;
                background:${COLORS.inputBg};color:${COLORS.text};
                border:1px solid ${COLORS.border};border-radius:6px;
                font-size:12px;text-align:center;box-sizing:border-box;
            `;
            const _clampCount = () => {
                let v = parseInt(randomCount.value, 10);
                if (isNaN(v) || v < 1) v = 1;
                if (v > 30) v = 30;
                randomCount.value = String(v);
                node._randomTotal = v;
            };
            randomCount.addEventListener("change", _clampCount);
            _clampCount();
            const randomRow = document.createElement("div");
            randomRow.style.cssText = "display:flex;flex-direction:row;align-items:stretch;width:100%;box-sizing:border-box;";
            randomRow.appendChild(randomBtn);
            randomRow.appendChild(randomCount);

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
            container.appendChild(randomRow);
            container.appendChild(previewArea);
            container.appendChild(clearBtn);
            container.appendChild(openBtn);

            const measureContainerHeight = () => {
                const h = Math.ceil(container.scrollHeight || 0);
                // 未布局（scrollHeight 仍为 0）时用保守保底，其余一律按真实内容高度，
                // 不再使用硬编码 200 下限，避免矮节点被撑成约 2 倍高。
                return h > 0 ? h : 120;
            };
            const domWidget = node.addDOMWidget("tag_picker_container", "TAG_PICKER_CONTAINER", container, {
                getValue() { return ""; },
                setValue() {},
                getMinHeight() {
                    return measureContainerHeight();
                },
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

function flashToast(node, msg) {
    const t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = "position:fixed;left:50%;top:20px;transform:translateX(-50%);background:#6c5ce7;color:#fff;padding:8px 16px;border-radius:6px;z-index:20000;font-size:12px;";
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 1500);
}
