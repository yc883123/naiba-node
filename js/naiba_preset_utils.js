/**
 * Naiba Preset Utils - 共享预设管理模态框与工具函数
 * 供 Visual LoRA Loader、Multi LoRA Loader（含 only model）、Lora Data Preview 使用
 *
 * 预设管理页交互：点击预设卡片弹出操作菜单；左上角分类按钮负责筛选与分类管理。
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
    primary: "#3b82f6",
    danger: "#ff6b6b",
    dangerHover: "#ff8b8b",
    success: "#2ed573",
    warn: "#ffb347",
    text: "#e0e0e0",
    textDim: "#888",
    border: "#2a3a5c",
    inputBg: "#0a0f1e",
};

const UNCATEGORIZED_FILTER = "__uncategorized__";
const CATEGORY_STORE_FALLBACK = { categories: [], assignments: {} };

// ========== 样式（单次注入，避免各节点重复内联样式） ==========
function ensurePresetStyles() {
    if (document.getElementById("naiba-preset-styles")) return;
    const style = document.createElement("style");
    style.id = "naiba-preset-styles";
    style.textContent = `
.nps-overlay{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;background:rgba(3,6,14,.78);}
.nps-modal{position:relative;display:flex;flex-direction:column;width:min(92vw,980px);height:min(86vh,820px);background:linear-gradient(180deg,#1c1c34 0%,#141426 100%);border:1px solid rgba(108,92,231,.38);border-radius:16px;box-shadow:0 18px 50px rgba(0,0,0,.6);overflow:hidden;}
.nps-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px 12px;background:linear-gradient(180deg,rgba(22,33,62,.85),rgba(22,33,62,0));}
.nps-title-wrap{display:flex;align-items:center;gap:10px;min-width:0;}
.nps-logo{width:10px;height:10px;border-radius:50%;background:linear-gradient(135deg,#8b7bff,#4f46e5);box-shadow:0 0 12px rgba(108,92,231,.9);}
.nps-title{color:#f1f1f7;font-size:16px;font-weight:650;letter-spacing:.3px;}
.nps-count{color:#9aa0b8;font-size:11px;padding:3px 9px;border:1px solid #2a3a5c;border-radius:999px;background:rgba(10,15,30,.6);white-space:nowrap;}
.nps-icon-btn{display:flex;align-items:center;justify-content:center;width:30px;height:30px;border:none;border-radius:8px;background:transparent;color:#8d93ab;cursor:pointer;transition:.15s;}
.nps-icon-btn:hover{background:rgba(255,255,255,.08);color:#fff;}
.nps-toolbar{position:relative;display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:0 20px 14px;}
.nps-cat-btn{display:flex;align-items:center;gap:7px;height:34px;padding:0 12px;border-radius:9px;border:1px solid #2a3a5c;background:#121a2e;color:#c9cee0;font-size:12px;cursor:pointer;white-space:nowrap;transition:.15s;max-width:200px;min-width:0;flex-shrink:1;}
.nps-cat-btn:hover{border-color:rgba(108,92,231,.65);color:#fff;}
.nps-cat-btn.active{border-color:rgba(108,92,231,.75);background:rgba(108,92,231,.16);color:#dfe3ff;}
.nps-cat-btn .nps-chevron{transition:transform .15s;}
.nps-cat-btn.open .nps-chevron{transform:rotate(180deg);}
.nps-cat-label{overflow:hidden;text-overflow:ellipsis;}
.nps-search-wrap{position:relative;flex:1 1 160px;min-width:120px;}
.nps-search-wrap svg{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:#6d7490;pointer-events:none;}
.nps-search{width:100%;height:34px;padding:0 12px 0 32px;box-sizing:border-box;border-radius:9px;border:1px solid #2a3a5c;background:#0b1120;color:#e0e0e0;font-size:12px;outline:none;transition:.15s;}
.nps-search::placeholder{color:#5d6684;}
.nps-search:focus{border-color:rgba(108,92,231,.7);box-shadow:0 0 0 3px rgba(108,92,231,.14);}
.nps-sort-btn{display:flex;align-items:center;gap:6px;height:34px;padding:0 11px;border-radius:9px;border:1px solid #2a3a5c;background:transparent;color:#8d93ab;font-size:12px;cursor:pointer;transition:.15s;white-space:nowrap;flex-shrink:0;}
.nps-sort-btn:hover{color:#dfe3ff;border-color:rgba(108,92,231,.5);}
.nps-sort-btn.active{color:#dfe3ff;border-color:rgba(108,92,231,.65);background:rgba(108,92,231,.14);}
.nps-cat-panel{position:absolute;top:calc(100% + 6px);left:20px;width:248px;max-height:min(420px,60vh);overflow-y:auto;padding:6px;border-radius:12px;border:1px solid rgba(139,123,255,.5);background:#26284a;box-shadow:0 18px 50px rgba(0,0,0,.6);z-index:20;}
.nps-cat-item{display:flex;align-items:center;gap:9px;padding:8px 62px 8px 10px;min-height:36px;box-sizing:border-box;border-radius:8px;color:#c9cee0;font-size:12px;cursor:pointer;user-select:none;position:relative;}
.nps-cat-item:hover{background:rgba(255,255,255,.06);color:#fff;}
.nps-cat-item.active{background:rgba(108,92,231,.18);color:#e6e3ff;}
.nps-cat-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.nps-cat-count{font-size:10px;color:#7b819b;background:rgba(255,255,255,.05);padding:1px 7px;border-radius:999px;}
.nps-cat-item.active .nps-cat-count{color:#cfc9ff;background:rgba(108,92,231,.28);}
.nps-cat-actions{position:absolute;right:8px;top:50%;transform:translateY(-50%);display:flex;align-items:center;gap:2px;opacity:0;pointer-events:none;}
.nps-cat-item:hover .nps-cat-actions{opacity:1;pointer-events:auto;}
.nps-cat-actions button{display:flex;align-items:center;justify-content:center;width:22px;height:22px;border:none;border-radius:6px;background:transparent;color:#8d93ab;cursor:pointer;}
.nps-cat-actions button:hover{background:rgba(255,255,255,.1);color:#fff;}
.nps-cat-actions button.danger:hover{background:rgba(255,107,107,.16);color:#ff8b8b;}
.nps-menu-sep{height:1px;margin:5px 8px;background:rgba(255,255,255,.28);}
.nps-cat-inline{display:flex;align-items:center;gap:6px;padding:6px 7px;}
.nps-cat-new{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:8px;color:#8f96b5;font-size:12px;cursor:pointer;transition:.12s;}
.nps-cat-new:hover{background:rgba(108,92,231,.12);color:#c9c4ff;}
.nps-body{flex:1;min-height:0;overflow-y:auto;padding:4px 20px 20px;}
.nps-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:14px;align-content:start;}
.nps-card{display:flex;flex-direction:column;gap:8px;padding:9px;border-radius:12px;background:#151b2e;border:1px solid rgba(42,58,92,.75);cursor:pointer;position:relative;}
.nps-card:hover{border-color:rgba(108,92,231,.65);}
.nps-card.drop-active{border-color:#6c5ce7;background:#1b2238;}
.nps-card-more{position:absolute;top:12px;right:12px;z-index:2;box-sizing:border-box;width:32px;height:32px;border-radius:10px;border:1px solid rgba(255,255,255,.16);display:flex;align-items:center;justify-content:center;background:rgba(6,10,20,.72);color:#c9cee0;opacity:0;pointer-events:none;font-size:18px;line-height:1;}
.nps-card:hover .nps-card-more{opacity:1;}
.nps-card-import{position:absolute;top:12px;left:12px;z-index:2;box-sizing:border-box;display:flex;align-items:center;justify-content:center;width:32px;height:32px;padding:0;border:1px solid rgba(255,255,255,.16);border-radius:10px;background:rgba(6,10,20,.72);color:#c9cee0;opacity:0;pointer-events:none;cursor:pointer;}
.nps-card:hover .nps-card-import{opacity:1;pointer-events:auto;}
.nps-card-import:hover{background:rgba(108,92,231,.9);color:#fff;}
.nps-card.drop-active .nps-card-import{opacity:0;pointer-events:none;}
.nps-cover{position:relative;width:100%;aspect-ratio:1/1;border-radius:9px;overflow:hidden;background:#0b1120;display:flex;align-items:center;justify-content:center;}
.nps-cover img{width:100%;height:100%;object-fit:contain;display:none;}
.nps-cover-ph{position:absolute;inset:0;display:none;align-items:center;justify-content:center;flex-direction:column;gap:6px;color:#5d6684;font-size:11px;}
.nps-drop-hint{position:absolute;inset:0;display:none;align-items:center;justify-content:center;padding:10px;text-align:center;color:#fff;font-size:12px;font-weight:600;background:rgba(108,92,231,.85);}
.nps-name{color:#e4e6f1;font-size:12px;font-weight:550;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 2px;}
.nps-tags{display:flex;flex-wrap:wrap;gap:4px;justify-content:center;min-height:18px;}
.nps-tag{font-size:10px;color:#b7aefc;background:rgba(108,92,231,.14);border:1px solid rgba(108,92,231,.35);padding:1px 7px;border-radius:999px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.nps-tag.muted{color:#6d7490;background:rgba(255,255,255,.03);border-color:#262b46;}
.nps-empty{grid-column:1/-1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:60px 20px;color:#8d93ab;font-size:13px;text-align:center;}
.nps-empty-icon{width:52px;height:52px;border-radius:16px;display:flex;align-items:center;justify-content:center;background:rgba(108,92,231,.12);color:#8b7bff;}
.nps-empty-actions{display:flex;gap:8px;margin-top:4px;}
.nps-empty-sub{font-size:11px;color:#6d7490;}
.nps-menu{position:fixed;min-width:196px;max-height:calc(100vh - 20px);overflow-y:auto;padding:6px;border-radius:12px;border:1px solid rgba(139,123,255,.5);background:#2b2a4e;box-shadow:0 20px 50px rgba(0,0,0,.62);z-index:10100;}
.nps-menu-item{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:8px;color:#d3d6e4;font-size:12px;cursor:pointer;transition:.12s;user-select:none;}
.nps-menu-item:hover{background:rgba(255,255,255,.07);color:#fff;}
.nps-menu-item.danger{color:#ff8b8b;}
.nps-menu-item.danger:hover{background:rgba(255,107,107,.14);}
.nps-menu-item.disabled{opacity:.42;cursor:not-allowed;}
.nps-menu-item.disabled:hover{background:transparent;color:#d3d6e4;}
.nps-menu-icon{display:flex;width:16px;justify-content:center;color:currentColor;opacity:.9;}
.nps-menu-sep-line{height:1px;margin:5px 8px;background:#3d3f68;}
.nps-toast{position:absolute;left:50%;bottom:18px;transform:translate(-50%,10px);padding:8px 16px;border-radius:9px;background:rgba(10,16,30,.94);border:1px solid #2a3a5c;color:#cfe9d8;font-size:12px;box-shadow:0 10px 30px rgba(0,0,0,.5);opacity:0;pointer-events:none;transition:.2s;z-index:30;max-width:80%;text-align:center;}
.nps-toast.show{opacity:1;transform:translate(-50%,0);}
.nps-toast.error{color:#ffb1b1;border-color:rgba(255,107,107,.5);}
.nps-toast.warn{color:#ffd39a;border-color:rgba(255,179,71,.5);}
.nps-dialog-overlay{position:fixed;inset:0;z-index:10120;display:flex;align-items:center;justify-content:center;background:rgba(3,6,14,.7);}
.nps-dialog{width:min(520px,calc(100vw - 40px));max-height:calc(100vh - 60px);overflow-y:auto;padding:18px;border-radius:14px;border:1px solid rgba(108,92,231,.4);background:linear-gradient(180deg,#1c1c34,#151528);box-shadow:0 24px 70px rgba(0,0,0,.65);}
.nps-dialog-title{color:#f1f1f7;font-size:15px;font-weight:650;margin-bottom:14px;display:flex;align-items:center;gap:8px;min-width:0;}
.nps-dialog-sub{font-size:11px;font-weight:400;color:#8d93ab;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.nps-field{margin-bottom:12px;}
.nps-field-label{display:flex;align-items:center;justify-content:space-between;gap:8px;color:#9aa0b8;font-size:11px;margin-bottom:6px;}
.nps-field-hint{color:#5d6684;font-size:10px;}
.nps-input{width:100%;height:32px;padding:0 10px;box-sizing:border-box;border-radius:8px;border:1px solid #2a3a5c;background:#0b1120;color:#e0e0e0;font-size:12px;outline:none;transition:.15s;}
.nps-input:focus{border-color:rgba(108,92,231,.7);box-shadow:0 0 0 3px rgba(108,92,231,.12);}
.nps-cat-inline .nps-input{width:auto;flex:1;min-width:0;}
.nps-mini-btn{display:flex;align-items:center;justify-content:center;width:28px;height:28px;padding:0;flex-shrink:0;border-radius:7px;border:1px solid #3d3f68;background:#1f2140;color:#c9cee0;cursor:pointer;}
.nps-mini-btn:hover{filter:brightness(1.15);}
.nps-mini-btn.primary{border-color:#6c5ce7;background:#6c5ce7;color:#fff;}
.nps-chips{display:flex;flex-wrap:wrap;gap:6px;min-height:24px;}
.nps-chip{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:999px;border:1px solid #2a3a5c;background:#121a2e;color:#a9afc7;font-size:11px;cursor:pointer;transition:.12s;user-select:none;}
.nps-chip:hover{border-color:rgba(108,92,231,.6);color:#e0ddff;}
.nps-chip.selected{border-color:rgba(108,92,231,.85);background:rgba(108,92,231,.22);color:#e8e5ff;box-shadow:0 0 0 1px rgba(108,92,231,.25) inset;}
.nps-chip-check{display:flex;opacity:0;transition:.12s;}
.nps-chip.selected .nps-chip-check{opacity:1;}
.nps-no-cats{color:#6d7490;font-size:11px;padding:4px 0;line-height:1.6;}
.nps-note{color:#7b819b;font-size:11px;line-height:1.6;}
.nps-buttons{display:flex;justify-content:flex-end;gap:8px;margin-top:16px;}
.nps-btn{height:32px;padding:0 16px;border-radius:8px;border:1px solid #2a3a5c;background:transparent;color:#c9cee0;font-size:12px;cursor:pointer;transition:.15s;}
.nps-btn:hover{border-color:#4a4f70;color:#fff;}
.nps-btn.primary{border-color:#6c5ce7;background:linear-gradient(135deg,#7466f2,#5b4bd6);color:#fff;box-shadow:0 6px 18px rgba(108,92,231,.35);}
.nps-btn.primary:hover{filter:brightness(1.08);}
.nps-btn:disabled{opacity:.5;cursor:not-allowed;filter:none;}
.nps-form-error{color:#ff8b8b;font-size:11px;margin-top:8px;display:none;}
.nps-warn{color:#ffb347;font-size:11px;margin-top:8px;display:none;}
.nps-cover-picker{width:132px;aspect-ratio:1/1;margin:2px auto 0;padding:8px;box-sizing:border-box;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;border:1px dashed #2a3a5c;border-radius:10px;background:#0b1120;color:#6d7490;font-size:11px;cursor:pointer;transition:.15s;overflow:hidden;}
.nps-cover-picker:hover,.nps-cover-picker.dragover{border-color:#6c5ce7;color:#c9cee0;}
.nps-cover-picker img{flex:1;min-height:0;width:100%;object-fit:contain;display:none;border-radius:6px;}
.nps-cover-picker span{width:100%;min-width:0;text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.nps-diff{display:none;margin-top:10px;padding:9px 11px;background:#0b1120;border:1px solid #2a3a5c;border-radius:9px;font-size:11px;line-height:1.8;max-height:260px;overflow-y:auto;font-family:Consolas,monospace;color:#9aa0b8;}
.nps-diff-row{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.nps-diff-head{color:#e0e0e0;}
.nps-diff-add{color:#2ed573;}
.nps-diff-del{color:#ff6b6b;}
.nps-diff-chg{color:#ffb347;}
.nps-hidden-input{display:none;}
.nps-svg{display:block;flex-shrink:0;}
`;
    document.head.appendChild(style);
}

// ========== DOM 辅助 ==========
function el(tag, className = "", text = null) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== null && text !== undefined) node.textContent = text;
    return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const ICON_PATHS = {
    search: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.2-4.2"/>',
    folder: '<path d="M3 6h6l2 2h10v11H3z"/>',
    star: '<path d="m12 3.5 2.6 5.4 5.9.9-4.3 4.2 1 5.9-5.2-2.8-5.2 2.8 1-5.9L3.5 9.8l5.9-.9z"/>',
    dot: '<circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    sort: '<path d="M7 4v16M7 20l-3-3M7 20l3-3M17 20V4M17 4l-3 3M17 4l3 3"/>',
    importPreset: '<path d="M12 3v10m0 0 4-4m-4 4-4-4"/><path d="M4 15v4h16v-4"/>',
    save: '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v6h7V3"/><path d="M8 21v-7h8v7"/>',
    image: '<rect x="4" y="5" width="16" height="14" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="m4 16 5-5 4 4 3-3 4 4"/>',
    tag: '<path d="M3 12V4h8l9 9-8 8z"/><path d="M8 8h.01"/>',
    edit: '<path d="M4 20h4L20 8l-4-4L4 16z"/><path d="m14 6 4 4"/>',
    trash: '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="m6 7 1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
    export: '<path d="M12 15V4m0 0 4 4m-4-4L8 8"/><path d="M4 15v4h16v-4"/>',
    fileImport: '<path d="M14 3H6v18h12V9z"/><path d="M14 3v6h6"/><path d="M12 11v6m0 0 3-3m-3 3-3-3"/>',
    check: '<path d="m5 13 4 4 10-10"/>',
};

function icon(name, size = 15) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("nps-svg");
    svg.innerHTML = `<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICON_PATHS[name] || ""}</g>`;
    return svg;
}

// ========== 单例模态框管理 ==========
let currentModal = null;

// ========== SHA256 扫描进度窗口 ==========
// 保存/导入预设时后端会扫描 LoRA 文件 SHA256，大文件（GB 级）可能耗时数秒甚至更久，
// 期间弹出居中提示框，避免用户误以为卡死。单例复用，请求结束即隐藏。
let _shaProgressOverlay = null;
function showShaProgress() {
    if (!_shaProgressOverlay) {
        const overlay = document.createElement("div");
        overlay.style.cssText = `
            position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.45);z-index:10500;
            display:flex;align-items:center;justify-content:center;
        `;
        const box = document.createElement("div");
        box.style.cssText = `
            display:flex;align-items:center;gap:12px;
            background:${COLORS.modalBg};border:1px solid ${COLORS.accent};
            border-radius:8px;padding:16px 22px;
            box-shadow:0 8px 30px rgba(0,0,0,0.6);
        `;
        const spinner = document.createElement("div");
        spinner.style.cssText = `
            width:18px;height:18px;border:2px solid ${COLORS.border};
            border-top-color:${COLORS.accent};border-radius:50%;
            animation:naiba-shaspin 0.8s linear infinite;flex-shrink:0;
        `;
        const txt = document.createElement("span");
        txt.textContent = "扫描sha256中.....";
        txt.style.cssText = `color:${COLORS.text};font-size:13px;white-space:nowrap;`;
        box.appendChild(spinner);
        box.appendChild(txt);
        overlay.appendChild(box);
        _shaProgressOverlay = overlay;
        if (!document.getElementById("naiba-shaspin-style")) {
            const st = document.createElement("style");
            st.id = "naiba-shaspin-style";
            st.textContent = "@keyframes naiba-shaspin{to{transform:rotate(360deg)}}";
            document.head.appendChild(st);
        }
    }
    if (!_shaProgressOverlay.parentNode) {
        document.body.appendChild(_shaProgressOverlay);
    }
    _shaProgressOverlay.style.display = "flex";
}
function hideShaProgress() {
    if (_shaProgressOverlay) {
        _shaProgressOverlay.style.display = "none";
    }
}

// ========== 上传预设封面 ==========
async function uploadCover(name, file) {
    const fd = new FormData();
    fd.append("name", name);
    fd.append("file", file);
    const resp = await api.fetchApi("/naiba/presets/upload-image", { method: "POST", body: fd });
    return resp.json();
}

const SUPPORTED_COVER_EXTENSIONS = /\.(png|jpe?g|webp|gif)$/i;

function isSupportedCoverFile(file) {
    if (!file) return false;
    return ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(file.type)
        || SUPPORTED_COVER_EXTENSIONS.test(file.name || "");
}

// ========== 预设数据 ==========
function getCurrentData(node) {
    const loraDataWidget = node?.widgets?.find((w) => w.name === "lora_data");
    if (!loraDataWidget) return [];
    try {
        return JSON.parse(loraDataWidget.value || "[]");
    } catch {
        return [];
    }
}

async function fetchPresetNames() {
    try {
        const resp = await api.fetchApi("/naiba/presets/list");
        const result = await resp.json();
        if (result.error || !Array.isArray(result.presets)) return [];
        return result.presets;
    } catch (e) {
        console.error("[Presets] Failed to fetch preset names:", e);
        return [];
    }
}

async function fetchPresetData(name) {
    try {
        const resp = await api.fetchApi(`/naiba/presets/load?name=${encodeURIComponent(name)}`);
        const result = await resp.json();
        if (result.error || !Array.isArray(result.data)) return null;
        return result.data;
    } catch (e) {
        console.warn("[Presets] Failed to load preset data for diff:", e);
        return null;
    }
}

function normalizeCategoryStore(raw) {
    const categories = Array.isArray(raw?.categories)
        ? raw.categories.filter((value) => typeof value === "string" && value)
        : [];
    const known = new Set(categories);
    const assignments = {};
    if (raw?.assignments && typeof raw.assignments === "object") {
        for (const [presetName, values] of Object.entries(raw.assignments)) {
            if (!Array.isArray(values)) continue;
            const list = values.filter((value) => known.has(value));
            if (list.length) assignments[presetName] = list;
        }
    }
    return { categories, assignments };
}

async function fetchCategoryStore() {
    try {
        const resp = await api.fetchApi("/naiba/presets/categories");
        const result = await resp.json();
        if (result.error) {
            console.warn("[Presets] Failed to load categories:", result.error);
            return null;
        }
        return normalizeCategoryStore(result);
    } catch (e) {
        console.warn("[Presets] Failed to load categories:", e);
        return null;
    }
}

// ========== 当前数据来源预设名（持久化到节点 properties，随工作流保存/加载） ==========
export function getLoadedPresetName(node) {
    return (node && node.properties && node.properties.naiba_loaded_preset) || "";
}

export function setLoadedPresetName(node, name) {
    if (!node) return;
    if (name) {
        if (!node.properties) node.properties = {};
        node.properties.naiba_loaded_preset = name;
    } else if (node.properties) {
        delete node.properties.naiba_loaded_preset;
    }
}

// 条目身份匹配：优先 sha256（文件改名仍可对上），回退到归一化路径（手动添加的条目尚未回填 sha）
function normLoraPath(name) {
    return String(name || "").replace(/\\/g, "/").replace(/^\/+/, "").toLowerCase();
}

function diffPresetData(oldData, newData) {
    const oldList = Array.isArray(oldData) ? oldData : [];
    const newList = Array.isArray(newData) ? newData : [];
    const oldBySha = new Map();
    const oldByName = new Map();
    for (const e of oldList) {
        if (e?.sha256) oldBySha.set(String(e.sha256).toLowerCase(), e);
        oldByName.set(normLoraPath(e?.name), e);
    }
    const matchedOld = new Set();
    const added = [];
    const removed = [];
    const changed = [];
    for (const e of newList) {
        let o = e?.sha256 ? oldBySha.get(String(e.sha256).toLowerCase()) : null;
        if (!o) o = oldByName.get(normLoraPath(e?.name)) || null;
        if (!o) {
            added.push(e);
            continue;
        }
        matchedOld.add(o);
        const onOff = (v) => v !== false;
        if ((o.strength_model ?? 1) !== (e.strength_model ?? 1)
            || (o.strength_clip ?? 1) !== (e.strength_clip ?? 1)
            || onOff(o.enabled) !== onOff(e.enabled)) {
            changed.push({ from: o, to: e });
        }
    }
    for (const o of oldList) {
        if (!matchedOld.has(o)) removed.push(o);
    }
    return { added, removed, changed };
}

// 保存预设数据，返回 { ok, error?, coverError?, categoryError?, categories? }；错误由调用方决定如何展示
async function savePresetData(node, trimmedName, coverFile = null, categories = null) {
    const data = getCurrentData(node);
    if (data.length === 0) {
        return { ok: false, error: "当前没有 LoRA 配置可保存" };
    }

    try {
        showShaProgress();
        try {
            const body = { name: trimmedName, data };
            if (Array.isArray(categories)) body.categories = categories;
            const resp = await api.fetchApi("/naiba/presets/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const result = await resp.json();

            if (result.error) {
                return { ok: false, error: result.error };
            }

            let coverError = "";
            if (coverFile) {
                try {
                    const uploadResult = await uploadCover(trimmedName, coverFile);
                    if (!uploadResult.success) {
                        coverError = uploadResult.error || "未知错误";
                    }
                } catch (error) {
                    coverError = error.message;
                }
            }
            return {
                ok: true,
                coverError,
                categoryError: result.category_error || "",
                categories: Array.isArray(result.categories) ? result.categories : null,
            };
        } finally {
            hideShaProgress();
        }
    } catch (e) {
        return { ok: false, error: e.message };
    }
}

/**
 * 打开保存预设对话框（可脱离预设管理模态框独立使用，如节点工具栏按钮）
 * @param {Object} node - ComfyUI 节点实例
 * @param {Object} [opts]
 * @param {string} [opts.defaultName] - 预填的预设名（如最近导入的预设名，便于覆盖迭代）
 * @param {string[]|null} [opts.existingNames] - 已有预设名列表；缺省时向后端拉取
 * @param {string[]|null} [opts.defaultCategories] - 预选分类；缺省时按同名预设的现有分类预选
 * @param {Function} [opts.onSaved] - 保存成功后的回调（如刷新预设网格）
 */
export async function openSavePresetDialog(node, {
    defaultName = "",
    existingNames = null,
    defaultCategories = null,
    onSaved = null,
} = {}) {
    ensurePresetStyles();
    const existingNameList = Array.isArray(existingNames) ? existingNames.slice() : await fetchPresetNames();
    const loadedCategoryStore = await fetchCategoryStore();
    const categoryStoreAvailable = !!loadedCategoryStore;
    const categoryStore = loadedCategoryStore || CATEGORY_STORE_FALLBACK;
    const availableCategories = categoryStore.categories;

    const overlay = el("div", "nps-dialog-overlay");
    const box = el("div", "nps-dialog");

    const title = el("div", "nps-dialog-title", "保存预设");

    const nameField = el("div", "nps-field");
    nameField.appendChild(el("div", "nps-field-label", "预设名称"));
    const input = el("input", "nps-input");
    input.type = "text";
    input.value = defaultName || "";
    input.placeholder = "请输入预设名称";
    nameField.appendChild(input);

    const categoryField = el("div", "nps-field");
    const categoryLabel = el("div", "nps-field-label");
    categoryLabel.appendChild(document.createTextNode("分类（可多选）"));
    categoryLabel.appendChild(el("span", "nps-field-hint", "不选则归入未分类"));
    categoryField.appendChild(categoryLabel);
    const chipsWrap = el("div", "nps-chips");
    categoryField.appendChild(chipsWrap);

    const selectedCategories = new Set();
    let categoriesTouched = false;

    const initialCategories = Array.isArray(defaultCategories)
        ? defaultCategories
        : (defaultName ? categoryStore.assignments[defaultName] || [] : []);
    for (const category of initialCategories) {
        if (availableCategories.includes(category)) selectedCategories.add(category);
    }

    function renderCategoryChips() {
        chipsWrap.innerHTML = "";
        if (!categoryStoreAvailable) {
            chipsWrap.appendChild(el("div", "nps-no-cats", "分类信息加载失败，本次保存将保留原分类设置"));
            return;
        }

        const uncategorizedChip = el(
            "div",
            "nps-chip" + (selectedCategories.size === 0 ? " selected" : ""),
        );
        if (selectedCategories.size === 0) {
            const checkWrap = el("span", "nps-chip-check");
            checkWrap.appendChild(icon("check", 11));
            uncategorizedChip.appendChild(checkWrap);
        }
        uncategorizedChip.appendChild(el("span", "", "未分类"));
        uncategorizedChip.title = "不选择任何分类时归入未分类";
        uncategorizedChip.addEventListener("click", () => {
            categoriesTouched = true;
            selectedCategories.clear();
            renderCategoryChips();
        });
        chipsWrap.appendChild(uncategorizedChip);

        if (!availableCategories.length) {
            chipsWrap.appendChild(el("div", "nps-no-cats", "暂无分类，可在预设管理页左上角新增分类"));
            return;
        }

        for (const category of availableCategories) {
            const chip = el("div", "nps-chip" + (selectedCategories.has(category) ? " selected" : ""));
            if (selectedCategories.has(category)) {
                const checkWrap = el("span", "nps-chip-check");
                checkWrap.appendChild(icon("check", 11));
                chip.appendChild(checkWrap);
            }
            chip.appendChild(el("span", "", category));
            chip.addEventListener("click", () => {
                categoriesTouched = true;
                if (selectedCategories.has(category)) selectedCategories.delete(category);
                else selectedCategories.add(category);
                renderCategoryChips();
            });
            chipsWrap.appendChild(chip);
        }
    }
    renderCategoryChips();

    const coverField = el("div", "nps-field");
    coverField.appendChild(el("div", "nps-field-label", "封面（可选，支持拖入图片）"));
    const coverPicker = el("div", "nps-cover-picker");
    coverPicker.tabIndex = 0;
    const coverPreview = el("img");
    const coverPickerText = el("span", "", "选择封面（可选）");
    coverPicker.append(coverPreview, coverPickerText);
    coverField.appendChild(coverPicker);

    const dialogCoverInput = document.createElement("input");
    dialogCoverInput.type = "file";
    dialogCoverInput.accept = ".png,.jpg,.jpeg,.webp,.gif";
    dialogCoverInput.className = "nps-hidden-input";

    const coverError = el("div", "nps-form-error");

    const warn = el("div", "nps-warn");

    // 覆盖已有预设时展示与当前内容的 git 风格差异（+新增 −移除 ~强度修改）
    const diffBox = el("div", "nps-diff");

    const dialogStatus = el("div", "nps-form-error");

    let dialogCoverFile = null;
    let dialogCoverUrl = "";
    let coverDragDepth = 0;
    let saving = false;
    let diffTimer = null;
    let diffSeq = 0;
    let existingCoverNameShown = "";
    let existingCoverAvailable = false;

    function selectDialogCover(file) {
        if (!isSupportedCoverFile(file)) {
            coverError.textContent = "请选择 PNG、JPG、WEBP 或 GIF 图片";
            coverError.style.display = "block";
            return;
        }
        coverError.style.display = "none";
        dialogCoverFile = file;
        if (dialogCoverUrl) URL.revokeObjectURL(dialogCoverUrl);
        dialogCoverUrl = URL.createObjectURL(file);
        coverPreview.src = dialogCoverUrl;
        coverPreview.style.display = "block";
        coverPickerText.textContent = file.name;
    }

    const isExistingPresetName = (name) =>
        !!name && existingNameList.some((n) => n.toLowerCase() === name.toLowerCase());

    const coverPlaceholderText = () => {
        if (dialogCoverFile) return dialogCoverFile.name;
        if (isExistingPresetName(input.value.trim()) && existingCoverAvailable) return "覆盖后将保留原封面";
        return "选择封面（可选）";
    };

    // 名称命中已有预设时，展示其当前封面，明确「不选新封面就直接复用原封面」
    function refreshExistingCoverPreview() {
        if (dialogCoverFile) return;
        const name = input.value.trim();
        if (isExistingPresetName(name)) {
            if (existingCoverNameShown === name) return;
            existingCoverNameShown = name;
            coverPreview.onload = () => {
                if (dialogCoverFile) return;
                existingCoverAvailable = true;
                coverPreview.style.display = "block";
                coverPickerText.textContent = coverPlaceholderText();
            };
            coverPreview.onerror = () => {
                if (dialogCoverFile) return;
                existingCoverAvailable = false;
                existingCoverNameShown = "";
                coverPreview.style.display = "none";
                coverPickerText.textContent = "选择封面（可选）";
            };
            coverPreview.src = `/naiba/presets/image?name=${encodeURIComponent(name)}`;
        } else {
            existingCoverNameShown = "";
            existingCoverAvailable = false;
            coverPreview.onload = null;
            coverPreview.onerror = null;
            coverPreview.removeAttribute("src");
            coverPreview.style.display = "none";
            coverPickerText.textContent = coverPlaceholderText();
        }
    }

    coverPicker.addEventListener("click", () => dialogCoverInput.click());
    coverPicker.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            dialogCoverInput.click();
        }
    });
    dialogCoverInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        dialogCoverInput.value = "";
        if (file) selectDialogCover(file);
    });
    coverPicker.addEventListener("dragenter", (e) => {
        e.preventDefault();
        coverDragDepth += 1;
        coverPicker.classList.add("dragover");
        coverPickerText.textContent = "松开选择封面";
    });
    coverPicker.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    });
    coverPicker.addEventListener("dragleave", () => {
        coverDragDepth -= 1;
        if (coverDragDepth === 0) {
            coverPicker.classList.remove("dragover");
            coverPickerText.textContent = coverPlaceholderText();
        }
    });
    coverPicker.addEventListener("drop", (e) => {
        e.preventDefault();
        coverDragDepth = 0;
        coverPicker.classList.remove("dragover");
        const files = Array.from(e.dataTransfer?.files || []);
        const file = files.find(isSupportedCoverFile);
        if (file) selectDialogCover(file);
        else selectDialogCover(null);
    });

    const btnRow = el("div", "nps-buttons");
    const cancelBtn = el("button", "nps-btn", "取消");
    cancelBtn.type = "button";
    const confirmBtn = el("button", "nps-btn primary", "保存");
    confirmBtn.type = "button";
    btnRow.append(cancelBtn, confirmBtn);

    function updateWarn() {
        const name = input.value.trim();
        const dup = name && existingNameList.some((n) => n.toLowerCase() === name.toLowerCase());
        if (dup) {
            warn.textContent = `预设「${name}」已存在，将覆盖现有内容`;
            warn.style.display = "block";
            confirmBtn.textContent = "确认覆盖";
        } else {
            warn.style.display = "none";
            confirmBtn.textContent = "保存";
        }
        dialogStatus.style.display = "none";

        if (!categoriesTouched) {
            selectedCategories.clear();
            if (categoryStoreAvailable && dup) {
                for (const category of categoryStore.assignments[name] || []) {
                    if (availableCategories.includes(category)) selectedCategories.add(category);
                }
            }
            renderCategoryChips();
        }

        refreshExistingCoverPreview();
        if (diffTimer) clearTimeout(diffTimer);
        diffTimer = setTimeout(refreshDiff, 250);
    }

    // ========== 覆盖差异对比（git 风格） ==========
    const fmtStrength = (v) => Number(v ?? 1).toFixed(2);
    const dispName = (e) => String(e?.name || "?").split(/[\\/]/).pop();

    function renderDiffBox(diff, name) {
        diffBox.innerHTML = "";
        const noChange = diff.added.length === 0 && diff.removed.length === 0 && diff.changed.length === 0;
        if (noChange) {
            const row = el("div", "nps-diff-row", `与已保存预设「${name}」内容一致`);
            row.style.color = COLORS.textDim;
            diffBox.appendChild(row);
        } else {
            diffBox.appendChild(el("div", "nps-diff-row nps-diff-head", "覆盖将产生以下变更（+ 新增  − 移除  ~ 强度修改）："));
            const mkRow = (sign, text, className) => {
                const row = el("div", `nps-diff-row ${className}`, `${sign} ${text}`);
                row.title = text;
                diffBox.appendChild(row);
            };
            for (const e of diff.added) {
                mkRow("+", `${dispName(e)}（model强度 ${fmtStrength(e.strength_model)}）`, "nps-diff-add");
            }
            for (const e of diff.removed) {
                mkRow("−", `${dispName(e)}（model强度 ${fmtStrength(e.strength_model)}）`, "nps-diff-del");
            }
            for (const c of diff.changed) {
                const parts = [];
                if ((c.from.strength_model ?? 1) !== (c.to.strength_model ?? 1)) {
                    parts.push(`model强度 ${fmtStrength(c.from.strength_model)}→${fmtStrength(c.to.strength_model)}`);
                }
                if ((c.from.strength_clip ?? 1) !== (c.to.strength_clip ?? 1)) {
                    parts.push(`clip强度 ${fmtStrength(c.from.strength_clip)}→${fmtStrength(c.to.strength_clip)}`);
                }
                if ((c.from.enabled !== false) !== (c.to.enabled !== false)) {
                    parts.push(`启用状态 ${(c.from.enabled !== false) ? "开" : "关"}→${(c.to.enabled !== false) ? "开" : "关"}`);
                }
                mkRow("~", `${dispName(c.to)}: ${parts.join("，")}`, "nps-diff-chg");
            }
        }
        diffBox.style.display = "block";
    }

    async function refreshDiff() {
        const seq = ++diffSeq;
        const name = input.value.trim();
        if (!name || !isExistingPresetName(name)) {
            diffBox.style.display = "none";
            return;
        }
        const presetData = await fetchPresetData(name);
        if (seq !== diffSeq) return;
        if (!presetData) {
            diffBox.style.display = "none";
            return;
        }
        renderDiffBox(diffPresetData(presetData, getCurrentData(node)), name);
    }

    const keyHandler = (e) => {
        if (e.key === "Escape") {
            e.stopPropagation();
            e.preventDefault();
            close();
        }
    };

    const close = () => {
        document.removeEventListener("keydown", keyHandler, true);
        if (dialogCoverUrl) URL.revokeObjectURL(dialogCoverUrl);
        overlay.remove();
    };

    cancelBtn.addEventListener("click", close);
    input.addEventListener("input", updateWarn);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") confirmBtn.click();
        if (e.key === "Escape") close();
    });
    confirmBtn.addEventListener("click", async () => {
        if (saving) return;
        const name = input.value.trim();
        if (!name) {
            input.focus();
            return;
        }
        saving = true;
        confirmBtn.disabled = true;
        const categories = Array.from(selectedCategories);
        const r = await savePresetData(
            node,
            name,
            dialogCoverFile,
            categoryStoreAvailable ? categories : null,
        );
        saving = false;
        confirmBtn.disabled = false;
        if (!r.ok) {
            dialogStatus.style.color = COLORS.danger;
            dialogStatus.textContent = r.error;
            dialogStatus.style.display = "block";
            return;
        }
        if (typeof onSaved === "function") {
            try {
                await onSaved(name, r.categories ?? categories);
            } catch (e) {
                console.error("[Presets] onSaved callback failed:", e);
            }
        }
        setLoadedPresetName(node, name);
        const problems = [];
        if (r.categoryError) problems.push(`分类保存失败: ${r.categoryError}`);
        if (r.coverError) problems.push(`封面上传失败: ${r.coverError}`);
        if (problems.length) {
            dialogStatus.style.color = COLORS.warn;
            dialogStatus.textContent = `预设已保存，但${problems.join("；")}`;
            dialogStatus.style.display = "block";
            return;
        }
        close();
    });

    box.appendChild(title);
    box.appendChild(nameField);
    box.appendChild(categoryField);
    box.appendChild(coverField);
    box.appendChild(dialogCoverInput);
    box.appendChild(coverError);
    box.appendChild(warn);
    box.appendChild(diffBox);
    box.appendChild(dialogStatus);
    box.appendChild(btnRow);
    overlay.appendChild(box);
    document.addEventListener("keydown", keyHandler, true);
    document.body.appendChild(overlay);
    input.focus();
    input.select();
    updateWarn();
}

/**
 * 创建预设管理模态框
 * @param {Object|null} node - ComfyUI 节点实例；为 null 时进入「仅管理」模式
 * @param {Function} [onImport] - 导入预设后的回调函数（可选）
 */
export function createPresetsModal(node, onImport = null) {
    if (currentModal) {
        currentModal.focus();
        return;
    }

    ensurePresetStyles();

    const hasNode = !!node;
    const nodeActionHint = "请先在画布中放置 Lora Data Preview 节点";

    // ========== 模态框骨架 ==========
    const overlay = el("div", "nps-overlay");
    const modal = el("div", "nps-modal");

    const header = el("div", "nps-header");
    const titleWrap = el("div", "nps-title-wrap");
    titleWrap.appendChild(el("span", "nps-logo"));
    titleWrap.appendChild(el("span", "nps-title", "LoRA 预设"));
    const countBadge = el("span", "nps-count", "共 0 个");
    titleWrap.appendChild(countBadge);
    header.appendChild(titleWrap);

    const closeBtn = el("button", "nps-icon-btn");
    closeBtn.type = "button";
    closeBtn.title = "关闭";
    closeBtn.appendChild(icon("close", 16));
    header.appendChild(closeBtn);
    modal.appendChild(header);

    const toolbar = el("div", "nps-toolbar");
    const categoryBtn = el("button", "nps-cat-btn");
    categoryBtn.type = "button";
    categoryBtn.title = "按分类筛选 / 管理分类";
    categoryBtn.appendChild(icon("star", 15));
    const categoryLabelEl = el("span", "nps-cat-label", "全部预设");
    categoryBtn.appendChild(categoryLabelEl);
    const chevronIcon = icon("chevron", 14);
    chevronIcon.classList.add("nps-chevron");
    categoryBtn.appendChild(chevronIcon);
    toolbar.appendChild(categoryBtn);

    const searchWrap = el("div", "nps-search-wrap");
    searchWrap.appendChild(icon("search", 15));
    const searchInput = el("input", "nps-search");
    searchInput.type = "text";
    searchInput.placeholder = "搜索预设...";
    searchWrap.appendChild(searchInput);
    toolbar.appendChild(searchWrap);

    const sortBtn = el("button", "nps-sort-btn");
    sortBtn.type = "button";
    sortBtn.appendChild(icon("sort", 15));
    const sortLabel = el("span", "", "字母序");
    sortBtn.appendChild(sortLabel);
    toolbar.appendChild(sortBtn);

    modal.appendChild(toolbar);

    const bodyEl = el("div", "nps-body");
    const grid = el("div", "nps-grid");
    bodyEl.appendChild(grid);
    modal.appendChild(bodyEl);

    const toast = el("div", "nps-toast");
    modal.appendChild(toast);

    const coverFileInput = document.createElement("input");
    coverFileInput.type = "file";
    coverFileInput.accept = ".png,.jpg,.jpeg,.webp,.gif";
    coverFileInput.className = "nps-hidden-input";
    modal.appendChild(coverFileInput);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // ========== 状态 ==========
    let presetNames = [];
    let presetMtimes = {};
    let categoryStore = normalizeCategoryStore(null);
    let cardEls = [];
    let activeCategory = "all";
    let searchQuery = "";
    let categoryPanelEl = null;
    let coverTargetName = null;
    let toastTimer = null;
    let menuEl = null;
    let menuOutsideHandler = null;

    const SORT_MODE_STORAGE_KEY = "naiba_preset_sort_mode";
    let sortMode = "name";
    try {
        if (localStorage.getItem(SORT_MODE_STORAGE_KEY) === "time") sortMode = "time";
    } catch (e) { /* localStorage 不可用时保持默认字母序 */ }

    const emptyFilterEl = el("div", "nps-empty");
    emptyFilterEl.appendChild(icon("search", 30));
    emptyFilterEl.appendChild(el("div", "", "没有匹配的预设"));
    emptyFilterEl.appendChild(el("div", "nps-empty-sub", "试试调整搜索词或分类筛选"));
    emptyFilterEl.style.display = "none";

    // ========== 基础工具 ==========
    function showStatus(message, kind = "success") {
        if (kind === true) kind = "error";
        toast.textContent = message;
        toast.classList.remove("error", "warn");
        if (kind === "error") toast.classList.add("error");
        else if (kind === "warn") toast.classList.add("warn");
        toast.classList.add("show");
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
    }

    function getPresetCategories(name) {
        return categoryStore.assignments[name] || [];
    }

    function getVisibleCategories(name) {
        const known = new Set(categoryStore.categories);
        return getPresetCategories(name).filter((category) => known.has(category));
    }

    function matchesCategory(name) {
        if (activeCategory === "all") return true;
        if (activeCategory === UNCATEGORIZED_FILTER) return getVisibleCategories(name).length === 0;
        return getVisibleCategories(name).includes(activeCategory);
    }

    function sortedNames() {
        const names = presetNames.slice();
        if (sortMode === "time") {
            names.sort((a, b) =>
                ((presetMtimes[b] ?? 0) - (presetMtimes[a] ?? 0)) || a.localeCompare(b)
            );
        } else {
            names.sort((a, b) => a.localeCompare(b));
        }
        return names;
    }

    function refreshCategoryButton() {
        const label = activeCategory === "all"
            ? "全部预设"
            : (activeCategory === UNCATEGORIZED_FILTER ? "未分类" : activeCategory);
        categoryLabelEl.textContent = label;
        categoryLabelEl.title = label;
        categoryBtn.classList.toggle("active", activeCategory !== "all");
    }

    function updateSortButton() {
        if (sortMode === "time") {
            sortLabel.textContent = "最新优先";
            sortBtn.title = "当前按预设文件修改时间倒序（最新在前），点击恢复字母序";
            sortBtn.classList.add("active");
        } else {
            sortLabel.textContent = "字母序";
            sortBtn.title = "当前按字母序，点击切换为修改时间倒序（最新在前）";
            sortBtn.classList.remove("active");
        }
    }

    function applyFilters() {
        let visible = 0;
        for (const card of cardEls) {
            const show = (!searchQuery || card._name.toLowerCase().includes(searchQuery))
                && matchesCategory(card._name);
            card.style.display = show ? "" : "none";
            if (show) visible += 1;
        }
        emptyFilterEl.style.display = cardEls.length > 0 && visible === 0 ? "flex" : "none";
        const filtered = !!searchQuery || activeCategory !== "all";
        countBadge.textContent = filtered
            ? `${visible} / ${presetNames.length}`
            : `共 ${presetNames.length} 个`;
    }

    // ========== 节点数据 ==========
    async function resolvePreset(data) {
        try {
            const resp = await api.fetchApi("/naiba/presets/resolve", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ data }),
            });
            const r = await resp.json();
            if (r.error) return data;
            return r.data ?? data;
        } catch (e) {
            console.warn("[Presets] resolve failed, use raw data:", e);
            return data;
        }
    }

    function setNodeData(data) {
        const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
        if (!loraDataWidget) return;

        const serialized = JSON.stringify(data);

        if (node._clearAllEntries) {
            node._clearAllEntries();
        }

        loraDataWidget.value = serialized;

        if (node._addLoraEntry && data.length > 0) {
            for (const item of data) {
                node._addLoraEntry(item);
            }
        }

        // Multi Loader 的逐条重建会在内部序列化；最后恢复完整导入数据，
        // 确保路径、SHA256 和未知字段不会被中间状态覆盖。
        loraDataWidget.value = serialized;

        if (node._updateVisualLoraDisplay) {
            node._updateVisualLoraDisplay();
        }
        if (node._updateLoraDataPreview) {
            node._updateLoraDataPreview();
        }
        if (node._visualModalReload) {
            node._visualModalReload();
        }
        if (node._triggerVisualLoraResize) {
            node._triggerVisualLoraResize();
        }

        loraDataWidget.callback?.(loraDataWidget.value, app.canvas, node);
        node.graph?.change?.();
        node.setDirtyCanvas?.(true, true);
        node.graph?.setDirtyCanvas(true, true);
    }

    // ========== 分类面板 ==========
    function countCategories() {
        const counts = new Map();
        for (const name of presetNames) {
            for (const category of getVisibleCategories(name)) {
                counts.set(category, (counts.get(category) || 0) + 1);
            }
        }
        return counts;
    }

    function selectCategory(value) {
        activeCategory = value;
        refreshCategoryButton();
        closeCategoryPanel();
        applyFilters();
    }

    function closeCategoryPanel() {
        if (!categoryPanelEl) return;
        categoryPanelEl.remove();
        categoryPanelEl = null;
        categoryBtn.classList.remove("open");
        document.removeEventListener("mousedown", categoryOutsideHandler, true);
    }

    function categoryOutsideHandler(e) {
        if (!categoryPanelEl) return;
        if (categoryPanelEl.contains(e.target) || categoryBtn.contains(e.target)) return;
        closeCategoryPanel();
    }

    async function mutateCategories(payload) {
        const resp = await api.fetchApi("/naiba/presets/categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const result = await resp.json();
        if (result.error) throw new Error(result.error);
        categoryStore = normalizeCategoryStore(result);
        return categoryStore;
    }

    function afterCategoryMutation() {
        refreshCategoryButton();
        for (const card of cardEls) card._tagsWrap?._render?.();
        applyFilters();
        renderCategoryPanel();
    }

    function startCategoryRename(category, row) {
        if (!categoryPanelEl) return;
        const wrap = el("div", "nps-cat-inline");
        const input = el("input", "nps-input");
        input.type = "text";
        input.value = category;
        const okBtn = el("button", "nps-mini-btn primary");
        okBtn.type = "button";
        okBtn.title = "保存";
        okBtn.appendChild(icon("check", 13));
        const cancelBtn = el("button", "nps-mini-btn");
        cancelBtn.type = "button";
        cancelBtn.title = "取消";
        cancelBtn.appendChild(icon("close", 13));
        wrap.append(input, okBtn, cancelBtn);
        categoryPanelEl.replaceChild(wrap, row);
        input.focus();
        input.select();

        const restore = () => { if (categoryPanelEl) renderCategoryPanel(); };
        const submit = async () => {
            const value = input.value.trim();
            if (!value || value === category) {
                restore();
                return;
            }
            try {
                await mutateCategories({ action: "rename", name: category, new_name: value });
                if (activeCategory === category) activeCategory = value;
                afterCategoryMutation();
                showStatus("分类已重命名");
            } catch (e) {
                showStatus("重命名分类失败: " + e.message, true);
                restore();
            }
        };
        okBtn.addEventListener("click", submit);
        cancelBtn.addEventListener("click", restore);
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.stopPropagation();
                submit();
            }
            if (e.key === "Escape") {
                e.stopPropagation();
                e.preventDefault();
                restore();
            }
        });
    }

    async function deleteCategoryFlow(category) {
        const affected = countCategories().get(category) || 0;
        const ok = confirm(
            `确定删除分类「${category}」吗？\n该分类下 ${affected} 个预设若不属于其它分类，将归为未分类。`
        );
        if (!ok) return;
        try {
            await mutateCategories({ action: "delete", name: category });
            if (activeCategory === category) activeCategory = "all";
            afterCategoryMutation();
            showStatus("分类已删除");
        } catch (e) {
            showStatus("删除分类失败: " + e.message, true);
        }
    }

    function startCategoryCreate() {
        if (!categoryPanelEl) return;
        const newRow = categoryPanelEl.querySelector(".nps-cat-new");
        if (!newRow) return;
        const wrap = el("div", "nps-cat-inline");
        const input = el("input", "nps-input");
        input.type = "text";
        input.placeholder = "分类名称";
        const okBtn = el("button", "nps-mini-btn primary");
        okBtn.type = "button";
        okBtn.title = "添加";
        okBtn.appendChild(icon("plus", 13));
        const cancelBtn = el("button", "nps-mini-btn");
        cancelBtn.type = "button";
        cancelBtn.title = "取消";
        cancelBtn.appendChild(icon("close", 13));
        wrap.append(input, okBtn, cancelBtn);
        categoryPanelEl.replaceChild(wrap, newRow);
        input.focus();

        const restore = () => { if (categoryPanelEl) renderCategoryPanel(); };
        const submit = async () => {
            const value = input.value.trim();
            if (!value) {
                input.focus();
                return;
            }
            try {
                await mutateCategories({ action: "create", name: value });
                afterCategoryMutation();
                showStatus(`分类已创建: ${value}`);
            } catch (e) {
                showStatus("新增分类失败: " + e.message, true);
            }
        };
        okBtn.addEventListener("click", submit);
        cancelBtn.addEventListener("click", restore);
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.stopPropagation();
                submit();
            }
            if (e.key === "Escape") {
                e.stopPropagation();
                e.preventDefault();
                restore();
            }
        });
    }

    function makeCategoryRow(label, count, value, { onRename = null, onDelete = null, iconName = "star" } = {}) {
        const row = el("div", "nps-cat-item" + (activeCategory === value ? " active" : ""));
        row.appendChild(icon(activeCategory === value ? "check" : iconName, 14));
        row.appendChild(el("span", "nps-cat-name", label));
        row.appendChild(el("span", "nps-cat-count", String(count)));

        if (onRename || onDelete) {
            const actions = el("div", "nps-cat-actions");
            if (onRename) {
                const renameBtn = el("button", "", "");
                renameBtn.type = "button";
                renameBtn.title = "重命名分类";
                renameBtn.appendChild(icon("edit", 13));
                renameBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    onRename(row);
                });
                actions.appendChild(renameBtn);
            }
            if (onDelete) {
                const deleteBtn = el("button", "danger", "");
                deleteBtn.type = "button";
                deleteBtn.title = "删除分类";
                deleteBtn.appendChild(icon("trash", 13));
                deleteBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    onDelete();
                });
                actions.appendChild(deleteBtn);
            }
            row.appendChild(actions);
        }

        row.addEventListener("click", () => selectCategory(value));
        return row;
    }

    function renderCategoryPanel() {
        if (!categoryPanelEl) return;
        categoryPanelEl.innerHTML = "";
        const counts = countCategories();
        const uncategorized = presetNames.filter((name) => getVisibleCategories(name).length === 0).length;

        categoryPanelEl.appendChild(makeCategoryRow("全部预设", presetNames.length, "all"));
        categoryPanelEl.appendChild(
            makeCategoryRow("未分类", uncategorized, UNCATEGORIZED_FILTER, { iconName: "dot" })
        );
        categoryPanelEl.appendChild(el("div", "nps-menu-sep"));

        for (const category of categoryStore.categories) {
            categoryPanelEl.appendChild(
                makeCategoryRow(category, counts.get(category) || 0, category, {
                    onRename: (row) => startCategoryRename(category, row),
                    onDelete: () => deleteCategoryFlow(category),
                })
            );
        }

        if (categoryStore.categories.length) {
            categoryPanelEl.appendChild(el("div", "nps-menu-sep"));
        }
        const newRow = el("div", "nps-cat-new");
        newRow.appendChild(icon("plus", 14));
        newRow.appendChild(el("span", "", "新增分类"));
        newRow.addEventListener("click", startCategoryCreate);
        categoryPanelEl.appendChild(newRow);
    }

    function toggleCategoryPanel() {
        if (categoryPanelEl) {
            closeCategoryPanel();
            return;
        }
        categoryPanelEl = el("div", "nps-cat-panel");
        toolbar.appendChild(categoryPanelEl);
        categoryBtn.classList.add("open");
        renderCategoryPanel();
        setTimeout(() => {
            if (categoryPanelEl) {
                document.addEventListener("mousedown", categoryOutsideHandler, true);
            }
        }, 0);
    }

    // ========== 卡片 ==========
    function makeTags(name) {
        const wrap = el("div", "nps-tags");
        const render = () => {
            wrap.innerHTML = "";
            const categories = getVisibleCategories(name);
            if (!categories.length) {
                wrap.appendChild(el("span", "nps-tag muted", "未分类"));
                return;
            }
            for (const category of categories.slice(0, 2)) {
                wrap.appendChild(el("span", "nps-tag", category));
            }
            if (categories.length > 2) {
                wrap.appendChild(el("span", "nps-tag", `+${categories.length - 2}`));
            }
        };
        render();
        wrap._render = render;
        return wrap;
    }

    function buildCard(name) {
        const card = el("div", "nps-card");
        card._name = name;

        card.appendChild(el("div", "nps-card-more", "⋯"));

        if (hasNode) {
            const quickImportBtn = el("button", "nps-card-import");
            quickImportBtn.type = "button";
            quickImportBtn.title = "导入预设";
            quickImportBtn.appendChild(icon("importPreset", 17));
            quickImportBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                importPreset(name);
            });
            card.appendChild(quickImportBtn);
        }

        const cover = el("div", "nps-cover");
        const coverImg = document.createElement("img");
        coverImg.draggable = false;
        const coverPlaceholder = el("div", "nps-cover-ph");
        coverPlaceholder.appendChild(icon("image", 26));
        coverPlaceholder.appendChild(el("span", "", "无封面"));
        const dropHint = el("div", "nps-drop-hint", "松开设置封面");
        cover.append(coverImg, coverPlaceholder, dropHint);

        const refreshCover = () => {
            coverImg.style.display = "none";
            coverPlaceholder.style.display = "none";
            coverImg.src = `/naiba/presets/image?name=${encodeURIComponent(name)}&t=${Date.now()}`;
        };
        coverImg.onload = () => {
            coverImg.style.display = "block";
            coverPlaceholder.style.display = "none";
        };
        coverImg.onerror = () => {
            coverImg.style.display = "none";
            coverPlaceholder.style.display = "flex";
        };
        refreshCover();

        const setDropActive = (active) => {
            card.classList.toggle("drop-active", active);
            dropHint.style.display = active ? "flex" : "none";
        };

        let dragDepth = 0;
        let coverBusy = false;

        const applyCover = async (file) => {
            if (coverBusy) return;
            if (!isSupportedCoverFile(file)) {
                showStatus("请选择 PNG、JPG、WEBP 或 GIF 图片", true);
                return;
            }
            coverBusy = true;
            dropHint.textContent = "正在上传...";
            setDropActive(true);
            try {
                const result = await uploadCover(name, file);
                if (!result.success) {
                    showStatus(result.error || "封面上传失败", true);
                    return;
                }
                refreshCover();
                showStatus("封面已更新: " + name);
            } catch (err) {
                showStatus("封面上传失败: " + err.message, true);
            } finally {
                coverBusy = false;
                dropHint.textContent = "松开设置封面";
                setDropActive(false);
            }
        };
        card._applyCover = applyCover;

                card.addEventListener("dragenter", (e) => {
            e.preventDefault();
            dragDepth += 1;
            if (!coverBusy) setDropActive(true);
        });
        card.addEventListener("dragover", (e) => {
            e.preventDefault();
            if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
        });
        card.addEventListener("dragleave", () => {
            dragDepth = Math.max(0, dragDepth - 1);
            if (dragDepth === 0 && !coverBusy) setDropActive(false);
        });
        card.addEventListener("drop", async (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragDepth = 0;
            card._suppressClickUntil = Date.now() + 400;
            if (coverBusy) return;
            const file = Array.from(e.dataTransfer?.files || []).find(isSupportedCoverFile);
            if (!file) {
                setDropActive(false);
                showStatus("请拖入 PNG、JPG、WEBP 或 GIF 图片", true);
                return;
            }
            await applyCover(file);
        });

        const nameEl = el("div", "nps-name", name);
        nameEl.title = name;
        const tagsWrap = makeTags(name);
        card._tagsWrap = tagsWrap;

        card.append(cover, nameEl, tagsWrap);
        card.addEventListener("click", () => {
            if (Date.now() < (card._suppressClickUntil || 0)) return;
            openCardMenu(card, name);
        });
        return card;
    }

    function buildEmptyState() {
        const wrap = el("div", "nps-empty");
        const iconWrap = el("div", "nps-empty-icon");
        iconWrap.appendChild(icon("star", 26));
        wrap.appendChild(iconWrap);
        wrap.appendChild(el("div", "", "还没有预设"));
        if (!hasNode) {
            wrap.appendChild(el("div", "nps-empty-sub", nodeActionHint));
            return wrap;
        }
        wrap.appendChild(el("div", "nps-empty-sub", "先保存当前 LoRA 配置，或从文件导入"));
        const actions = el("div", "nps-empty-actions");
        const saveBtn = el("button", "nps-btn primary", "保存当前配置");
        saveBtn.type = "button";
        saveBtn.addEventListener("click", () => {
            openSavePresetDialog(node, {
                defaultName: getLoadedPresetName(node) || "",
                onSaved: async () => {
                    await loadData();
                    showStatus("预设已保存");
                },
            });
        });
        const importBtn = el("button", "nps-btn", "从文件导入");
        importBtn.type = "button";
        importBtn.addEventListener("click", importFromFile);
        actions.append(saveBtn, importBtn);
        wrap.appendChild(actions);
        return wrap;
    }

    function renderGrid() {
        grid.innerHTML = "";
        cardEls = [];
        if (!presetNames.length) {
            grid.appendChild(buildEmptyState());
            countBadge.textContent = "共 0 个";
            return;
        }
        for (const name of sortedNames()) {
            const card = buildCard(name);
            cardEls.push(card);
            grid.appendChild(card);
        }
        grid.appendChild(emptyFilterEl);
        applyFilters();
    }

    function reorderGrid() {
        if (!cardEls.length) return;
        const byName = new Map(cardEls.map((card) => [card._name, card]));
        for (const name of sortedNames()) {
            const card = byName.get(name);
            if (card) grid.appendChild(card);
        }
        grid.appendChild(emptyFilterEl);
    }

    // ========== 加载数据 ==========
    async function loadData() {
        try {
            const [listResp, catResp] = await Promise.all([
                api.fetchApi("/naiba/presets/list"),
                api.fetchApi("/naiba/presets/categories"),
            ]);
            const list = await listResp.json();
            if (list.error) {
                showStatus(list.error, true);
                return;
            }
            const categoryResult = await catResp.json();
            if (categoryResult.error) {
                console.warn("[Presets] 加载分类失败:", categoryResult.error);
            } else {
                categoryStore = normalizeCategoryStore(categoryResult);
            }

            presetMtimes = list.mtimes || {};
            presetNames = Array.isArray(list.presets) ? list.presets : [];
            if (activeCategory !== "all" && activeCategory !== UNCATEGORIZED_FILTER
                && !categoryStore.categories.includes(activeCategory)) {
                activeCategory = "all";
            }
            refreshCategoryButton();
            renderGrid();
            renderCategoryPanel();
        } catch (e) {
            showStatus("加载预设列表失败: " + e.message, true);
        }
    }

    // ========== 卡片菜单 ==========
    function closeCardMenu() {
        if (!menuEl) return;
        if (menuEl._menuHoverCleanup) {
            menuEl._menuHoverCleanup();
            menuEl._menuHoverCleanup = null;
        }
        menuEl.remove();
        menuEl = null;
        if (menuOutsideHandler) {
            document.removeEventListener("mousedown", menuOutsideHandler, true);
            menuOutsideHandler = null;
        }
        bodyEl.removeEventListener("scroll", closeCardMenu);
        window.removeEventListener("resize", closeCardMenu);
    }

    function addMenuItem(menu, iconName, label, action, { danger = false, disabled = false, disabledHint = "" } = {}) {
        const item = el("div", "nps-menu-item" + (danger ? " danger" : "") + (disabled ? " disabled" : ""));
        const iconWrap = el("span", "nps-menu-icon");
        iconWrap.appendChild(icon(iconName, 15));
        item.append(iconWrap, el("span", "", label));
        if (disabled && disabledHint) item.title = disabledHint;
        item.addEventListener("click", (e) => {
            e.stopPropagation();
            if (disabled) {
                if (disabledHint) showStatus(disabledHint, true);
                return;
            }
            closeCardMenu();
            action();
        });
        menu.appendChild(item);
    }

    function openCardMenu(card, name) {
        closeCardMenu();
        const menu = el("div", "nps-menu");
        const nodeDisabled = !hasNode;

        addMenuItem(menu, "importPreset", "导入预设", () => importPreset(name), { disabled: nodeDisabled, disabledHint: nodeActionHint });
        addMenuItem(menu, "save", "保存 / 覆盖预设…", () => openSaveDialogFor(name), { disabled: nodeDisabled, disabledHint: nodeActionHint });
        menu.appendChild(el("div", "nps-menu-sep-line"));
        addMenuItem(menu, "image", "更换封面…", () => chooseCoverFor(name));
        addMenuItem(menu, "tag", "编辑分类…", () => openCategoryEditor(name));
        addMenuItem(menu, "edit", "重命名…", () => openRenameDialog(name));
        menu.appendChild(el("div", "nps-menu-sep-line"));
        addMenuItem(menu, "export", "导出到文件", exportCurrentData, { disabled: nodeDisabled, disabledHint: nodeActionHint });
        addMenuItem(menu, "fileImport", "从文件导入", importFromFile, { disabled: nodeDisabled, disabledHint: nodeActionHint });
        menu.appendChild(el("div", "nps-menu-sep-line"));
        addMenuItem(menu, "trash", "删除预设", () => deletePreset(name), { danger: true });

        document.body.appendChild(menu);
        menuEl = menu;

        // 指针离开卡片或菜单后延时收起，避免菜单长期遮住右侧卡片；
        // 期间移入卡片/菜单会取消收起
        let menuHideTimer = null;
        const cancelMenuHide = () => {
            if (menuHideTimer) {
                clearTimeout(menuHideTimer);
                menuHideTimer = null;
            }
        };
        const scheduleMenuHide = () => {
            cancelMenuHide();
            menuHideTimer = setTimeout(() => {
                menuHideTimer = null;
                if (menuEl === menu) closeCardMenu();
            }, 100);
        };
        card.addEventListener("mouseleave", scheduleMenuHide);
        menu.addEventListener("mouseenter", cancelMenuHide);
        menu.addEventListener("mouseleave", scheduleMenuHide);
        menu._menuHoverCleanup = () => {
            cancelMenuHide();
            card.removeEventListener("mouseleave", scheduleMenuHide);
            menu.removeEventListener("mouseenter", cancelMenuHide);
            menu.removeEventListener("mouseleave", scheduleMenuHide);
        };

        const rect = card.getBoundingClientRect();
        const menuWidth = menu.offsetWidth;
        const menuHeight = menu.offsetHeight;
        const gap = 8;
        let left;
        let top;
        if (rect.right + gap + menuWidth <= window.innerWidth - 10) {
            // 优先浮现在卡片右侧
            left = rect.right + gap;
            top = rect.top;
        } else if (rect.left - gap - menuWidth >= 10) {
            // 右侧放不下时翻到卡片左侧
            left = rect.left - gap - menuWidth;
            top = rect.top;
        } else {
            // 两侧都放不下（窄窗口）时退回卡片下方/上方
            left = Math.max(10, Math.min(rect.left, window.innerWidth - menuWidth - 10));
            top = rect.bottom + gap;
            if (top + menuHeight > window.innerHeight - 10) {
                top = Math.max(10, rect.top - menuHeight - gap);
            }
        }
        left = Math.max(10, Math.min(left, window.innerWidth - menuWidth - 10));
        top = Math.max(10, Math.min(top, window.innerHeight - menuHeight - 10));
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;

        menuOutsideHandler = (e) => {
            if (menuEl && !menuEl.contains(e.target)) closeCardMenu();
        };
        setTimeout(() => {
            if (menuEl === menu) {
                document.addEventListener("mousedown", menuOutsideHandler, true);
            }
        }, 0);
        bodyEl.addEventListener("scroll", closeCardMenu);
        window.addEventListener("resize", closeCardMenu);
    }

    // ========== 操作入口 ==========
    async function importPreset(name) {
        if (!hasNode) {
            showStatus(nodeActionHint, true);
            return;
        }
        try {
            const resp = await api.fetchApi(`/naiba/presets/load?name=${encodeURIComponent(name)}`);
            const result = await resp.json();
            if (result.error) {
                showStatus(result.error, true);
                return;
            }
            showShaProgress();
            try {
                const resolved = await resolvePreset(result.data);
                setNodeData(resolved);
                setLoadedPresetName(node, name);
                closeModal();
                if (typeof onImport === "function") onImport();
            } finally {
                hideShaProgress();
            }
        } catch (e) {
            console.error("[Presets] Import error:", e);
            showStatus("导入失败: " + e.message, true);
        }
    }

    function openSaveDialogFor(name) {
        if (!hasNode) {
            showStatus(nodeActionHint, true);
            return;
        }
        openSavePresetDialog(node, {
            defaultName: name,
            defaultCategories: getPresetCategories(name),
            existingNames: presetNames.slice(),
            onSaved: async () => {
                await loadData();
                showStatus("预设已保存");
            },
        });
    }

    function chooseCoverFor(name) {
        coverTargetName = name;
        coverFileInput.click();
    }

    coverFileInput.addEventListener("change", async () => {
        const file = coverFileInput.files[0];
        coverFileInput.value = "";
        const name = coverTargetName;
        coverTargetName = null;
        if (!file || !name) return;
        const card = cardEls.find((item) => item._name === name);
        if (card?._applyCover) await card._applyCover(file);
    });

    function openTextPromptDialog({ title, subtitle = "", label = "", value = "", placeholder = "", confirmText = "确定", onSubmit }) {
        const overlayEl = el("div", "nps-dialog-overlay");
        const box = el("div", "nps-dialog");
        const titleEl = el("div", "nps-dialog-title", title);
        if (subtitle) titleEl.appendChild(el("span", "nps-dialog-sub", subtitle));
        box.appendChild(titleEl);

        const field = el("div", "nps-field");
        if (label) field.appendChild(el("div", "nps-field-label", label));
        const inputEl = el("input", "nps-input");
        inputEl.type = "text";
        inputEl.value = value;
        inputEl.placeholder = placeholder;
        field.appendChild(inputEl);
        const errorEl = el("div", "nps-form-error");
        field.appendChild(errorEl);
        box.appendChild(field);

        const buttons = el("div", "nps-buttons");
        const cancelBtn = el("button", "nps-btn", "取消");
        cancelBtn.type = "button";
        const confirmBtn = el("button", "nps-btn primary", confirmText);
        confirmBtn.type = "button";
        buttons.append(cancelBtn, confirmBtn);
        box.appendChild(buttons);
        overlayEl.appendChild(box);

        let submitting = false;
        const keyHandler = (e) => {
            if (e.key === "Escape") {
                e.stopPropagation();
                e.preventDefault();
                close();
            }
        };
        const close = () => {
            document.removeEventListener("keydown", keyHandler, true);
            overlayEl.remove();
        };
        cancelBtn.addEventListener("click", close);
        const submit = async () => {
            if (submitting) return;
            const next = inputEl.value.trim();
            if (!next) {
                errorEl.textContent = "名称不能为空";
                errorEl.style.display = "block";
                inputEl.focus();
                return;
            }
            if (next === value) {
                close();
                return;
            }
            submitting = true;
            confirmBtn.disabled = true;
            try {
                await onSubmit(next);
                close();
            } catch (e) {
                errorEl.textContent = e.message;
                errorEl.style.display = "block";
            } finally {
                submitting = false;
                confirmBtn.disabled = false;
            }
        };
        confirmBtn.addEventListener("click", submit);
        inputEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                submit();
            }
        });

        document.addEventListener("keydown", keyHandler, true);
        document.body.appendChild(overlayEl);
        inputEl.focus();
        inputEl.select();
    }

    function openRenameDialog(oldName) {
        openTextPromptDialog({
            title: "重命名预设",
            subtitle: oldName,
            label: "预设名称",
            value: oldName,
            confirmText: "重命名",
            onSubmit: async (newName) => {
                const resp = await api.fetchApi("/naiba/presets/rename", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ old_name: oldName, new_name: newName }),
                });
                const result = await resp.json();
                if (result.error) throw new Error(result.error);
                if (getLoadedPresetName(node) === oldName) {
                    setLoadedPresetName(node, newName);
                }
                await loadData();
                showStatus(result.warning || "重命名成功", result.warning ? "warn" : "success");
            },
        });
    }

    function openCategoryEditor(name) {
        const allCategories = categoryStore.categories.slice();
        const selected = new Set(getVisibleCategories(name));

        const overlayEl = el("div", "nps-dialog-overlay");
        const box = el("div", "nps-dialog");
        const titleEl = el("div", "nps-dialog-title", "编辑分类");
        titleEl.appendChild(el("span", "nps-dialog-sub", name));
        box.appendChild(titleEl);

        const field = el("div", "nps-field");
        const label = el("div", "nps-field-label");
        label.appendChild(document.createTextNode("为预设勾选分类（可多选）"));
        label.appendChild(el("span", "nps-field-hint", "不勾选任何分类时归入未分类"));
        field.appendChild(label);

        const chipsWrap = el("div", "nps-chips");
        if (!allCategories.length) {
            chipsWrap.appendChild(el("div", "nps-no-cats", "暂无分类，请先在左上角分类菜单中新增分类"));
        } else {
            for (const category of allCategories) {
                const chip = el("div", "nps-chip" + (selected.has(category) ? " selected" : ""));
                if (selected.has(category)) {
                    const checkWrap = el("span", "nps-chip-check");
                    checkWrap.appendChild(icon("check", 11));
                    chip.appendChild(checkWrap);
                }
                chip.appendChild(el("span", "", category));
                chip.addEventListener("click", () => {
                    if (selected.has(category)) selected.delete(category);
                    else selected.add(category);
                    chip.classList.toggle("selected", selected.has(category));
                });
                chipsWrap.appendChild(chip);
            }
        }
        field.appendChild(chipsWrap);
        box.appendChild(field);

        const status = el("div", "nps-form-error");
        box.appendChild(status);

        const buttons = el("div", "nps-buttons");
        const cancelBtn = el("button", "nps-btn", "取消");
        cancelBtn.type = "button";
        const saveBtn = el("button", "nps-btn primary", "保存分类");
        saveBtn.type = "button";
        buttons.append(cancelBtn, saveBtn);
        box.appendChild(buttons);
        overlayEl.appendChild(box);

        const keyHandler = (e) => {
            if (e.key === "Escape") {
                e.stopPropagation();
                e.preventDefault();
                close();
            }
        };
        const close = () => {
            document.removeEventListener("keydown", keyHandler, true);
            overlayEl.remove();
        };
        cancelBtn.addEventListener("click", close);
        saveBtn.addEventListener("click", async () => {
            saveBtn.disabled = true;
            try {
                const resp = await api.fetchApi("/naiba/presets/set-categories", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name, categories: Array.from(selected) }),
                });
                const result = await resp.json();
                if (result.error) throw new Error(result.error);
                const assigned = Array.isArray(result.categories) ? result.categories : [];
                if (assigned.length) categoryStore.assignments[name] = assigned;
                else delete categoryStore.assignments[name];
                afterCategoryMutation();
                close();
                showStatus("分类已更新");
            } catch (e) {
                status.textContent = e.message;
                status.style.display = "block";
            } finally {
                saveBtn.disabled = false;
            }
        });

        document.addEventListener("keydown", keyHandler, true);
        document.body.appendChild(overlayEl);
    }

    async function deletePreset(name) {
        if (!confirm(`确定删除预设 "${name}" 吗？`)) return;
        try {
            const resp = await api.fetchApi(`/naiba/presets/delete?name=${encodeURIComponent(name)}`, {
                method: "DELETE",
            });
            const result = await resp.json();
            if (result.error) {
                showStatus(result.error, true);
                return;
            }
            if (getLoadedPresetName(node) === name) {
                setLoadedPresetName(node, null);
            }
            await loadData();
            showStatus(result.warning || "预设已删除", result.warning ? "warn" : "success");
        } catch (e) {
            showStatus("删除失败: " + e.message, true);
        }
    }

    async function exportCurrentData() {
        if (!hasNode) {
            showStatus(nodeActionHint, true);
            return;
        }
        const data = getCurrentData(node);
        if (data.length === 0) {
            showStatus("当前没有 LoRA 配置可导出", true);
            return;
        }
        try {
            showShaProgress();
            const resp = await api.fetchApi("/naiba/presets/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ data, return_data: true }),
            });
            const result = await resp.json();
            if (result.error) {
                showStatus("导出失败：" + result.error, true);
                return;
            }
            const out = result.data || data;
            const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `lora_preset_${new Date().toISOString().slice(0, 10)}.json`;
            a.click();
            URL.revokeObjectURL(url);
            showStatus("预设已导出（已补全 sha256）");
        } catch (e) {
            showStatus("导出失败：" + e.message, true);
        } finally {
            hideShaProgress();
        }
    }

    function importFromFile() {
        if (!hasNode) {
            showStatus(nodeActionHint, true);
            return;
        }
        const fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.accept = ".json";
        fileInput.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            try {
                const text = await file.text();
                const data = JSON.parse(text);

                if (!Array.isArray(data)) {
                    showStatus("文件格式错误：需要是 JSON 数组", true);
                    return;
                }
                for (const item of data) {
                    if (!item.name || typeof item.strength_model !== "number") {
                        showStatus("文件格式错误：缺少必要字段", true);
                        return;
                    }
                }

                showShaProgress();
                try {
                    const resolved = await resolvePreset(data);
                    setNodeData(resolved);
                    setLoadedPresetName(node, null);
                    closeModal();
                    if (typeof onImport === "function") onImport();
                } finally {
                    hideShaProgress();
                }
            } catch (err) {
                showStatus("文件解析失败: " + err.message, true);
            }
        });
        fileInput.click();
    }

    // ========== 关闭与事件 ==========
    const escHandler = (e) => {
        if (e.key !== "Escape") return;
        if (menuEl) {
            closeCardMenu();
            return;
        }
        if (categoryPanelEl) {
            closeCategoryPanel();
            return;
        }
        closeModal();
    };

    function closeModal() {
        closeCardMenu();
        closeCategoryPanel();
        try {
            overlay.remove();
            currentModal = null;
            document.removeEventListener("keydown", escHandler);
        } catch (e) {
            console.error("[Presets] Error closing modal:", e);
        }
    }

    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeModal();
    });
    document.addEventListener("keydown", escHandler);

    closeBtn.addEventListener("click", closeModal);
    categoryBtn.addEventListener("click", toggleCategoryPanel);
    searchInput.addEventListener("input", () => {
        searchQuery = (searchInput.value || "").toLowerCase().trim();
        applyFilters();
    });
    sortBtn.addEventListener("click", () => {
        sortMode = sortMode === "time" ? "name" : "time";
        try {
            localStorage.setItem(SORT_MODE_STORAGE_KEY, sortMode);
        } catch (e) { /* 忽略持久化失败 */ }
        updateSortButton();
        reorderGrid();
    });

    // ========== 初始化 ==========
    refreshCategoryButton();
    updateSortButton();
    loadData();

    currentModal = modal;
    modal.focus = () => {
        overlay.style.display = "flex";
    };
}