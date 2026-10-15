/**
 * Naiba Preset Utils - 共享预设模态框和工具函数
 * 供 Multi LoRA Loader 和 Multi LoRA Loader (only model) 使用
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
    primary: "#3b82f6",       // 导入按钮（最高频主操作）蓝色
    danger: "#ff6b6b",
    dangerHover: "#ff8b8b",
    success: "#2ed573",
    warn: "#ffb347",
    text: "#e0e0e0",
    textDim: "#888",
    border: "#2a3a5c",
    inputBg: "#0a0f1e",
    listItemBg: "#16213e",
    listItemHover: "#1e2a4a",
    listItemActive: "#2a3a6a",
};

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
            background:rgba(0,0,0,0.45);z-index:10050;
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
        // 注入一次旋转动画 keyframes
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

// ========== 获取当前节点数据 ==========
function getCurrentData(node) {
    const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
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
        if ((o.strength_model ?? 1) !== (e.strength_model ?? 1) || (o.strength_clip ?? 1) !== (e.strength_clip ?? 1)) {
            changed.push({ from: o, to: e });
        }
    }
    for (const o of oldList) {
        if (!matchedOld.has(o)) removed.push(o);
    }
    return { added, removed, changed };
}

// 保存预设数据，返回 { ok, error?, coverError? }；错误由调用方决定如何展示
async function savePresetData(node, trimmedName, coverFile = null) {
    const data = getCurrentData(node);
    if (data.length === 0) {
        return { ok: false, error: "当前没有 LoRA 配置可保存" };
    }

    try {
        showShaProgress();
        try {
            const resp = await api.fetchApi("/naiba/presets/save", {
                method: "POST",
                body: JSON.stringify({ name: trimmedName, data }),
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
            return { ok: true, coverError };
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
 * @param {Function} [opts.onSaved] - 保存成功后的回调（如刷新预设网格）
 */
export async function openSavePresetDialog(node, { defaultName = "", existingNames = null, onSaved = null } = {}) {
    const existingNameList = Array.isArray(existingNames) ? existingNames.slice() : await fetchPresetNames();

    const dialogOverlay = document.createElement("div");
    dialogOverlay.style.cssText = `
        position:fixed;left:0;top:0;width:100%;height:100%;
        background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:10000;
    `;

    const box = document.createElement("div");
    box.style.cssText = `
        background:${COLORS.modalBg};border:1px solid ${COLORS.border};border-radius:6px;
        padding:16px;width:min(360px,calc(100vw - 48px));box-shadow:0 4px 20px rgba(0,0,0,0.4);
    `;

    const title = document.createElement("div");
    title.textContent = "保存预设";
    title.style.cssText = `color:${COLORS.text};font-size:14px;font-weight:bold;margin-bottom:10px;`;

    const input = document.createElement("input");
    input.value = defaultName || "";
    input.placeholder = "请输入预设名称";
    input.style.cssText = `
        width:100%;box-sizing:border-box;background:${COLORS.inputBg};border:1px solid ${COLORS.border};
        color:${COLORS.text};padding:6px 8px;border-radius:3px;font-size:13px;outline:none;
    `;

    const warn = document.createElement("div");
    warn.style.cssText = `color:${COLORS.warn};font-size:12px;margin-top:8px;display:none;`;

    // 覆盖已有预设时展示与当前内容的 git 风格差异（+新增 −移除 ~强度修改）
    const diffBox = document.createElement("div");
    diffBox.style.cssText = `
        display:none;margin-top:8px;padding:6px 8px;box-sizing:border-box;
        background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:3px;
        font-size:11px;line-height:1.7;max-height:150px;overflow-y:auto;
        font-family:Consolas,monospace;
    `;

    const dialogStatus = document.createElement("div");
    dialogStatus.style.cssText = `color:${COLORS.danger};font-size:12px;margin-top:8px;display:none;`;

    let dialogCoverFile = null;
    let dialogCoverUrl = "";
    let coverDragDepth = 0;
    let saving = false;
    let diffTimer = null;
    let diffSeq = 0;
    // 覆盖已有预设时用于展示其当前封面（不选新封面则覆盖后原样保留）
    let existingCoverNameShown = "";
    let existingCoverAvailable = false;

    const coverPicker = document.createElement("div");
    coverPicker.tabIndex = 0;
    coverPicker.style.cssText = `
        min-height:72px;margin-top:10px;padding:8px;box-sizing:border-box;
        display:flex;align-items:center;justify-content:center;gap:10px;
        border:1px dashed ${COLORS.border};border-radius:4px;background:${COLORS.inputBg};
        color:${COLORS.textDim};font-size:12px;cursor:pointer;transition:all 0.15s;
    `;

    const coverPreview = document.createElement("img");
    coverPreview.style.cssText = `
        width:56px;height:56px;object-fit:contain;display:none;flex-shrink:0;border-radius:3px;
    `;
    const coverPickerText = document.createElement("span");
    coverPickerText.textContent = "选择封面（可选）";
    coverPickerText.style.cssText = `min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;`;

    const dialogCoverInput = document.createElement("input");
    dialogCoverInput.type = "file";
    dialogCoverInput.accept = ".png,.jpg,.jpeg,.webp,.gif";
    dialogCoverInput.style.display = "none";

    const coverError = document.createElement("div");
    coverError.style.cssText = `color:${COLORS.danger};font-size:11px;margin-top:6px;display:none;`;

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
        if (dialogCoverFile) return; // 已选择新封面，以新封面为准
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

    coverPicker.appendChild(coverPreview);
    coverPicker.appendChild(coverPickerText);
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
        coverPicker.style.borderColor = COLORS.accent;
        coverPicker.style.color = COLORS.text;
        coverPickerText.textContent = "松开选择封面";
    });
    coverPicker.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    });
    coverPicker.addEventListener("dragleave", () => {
        coverDragDepth -= 1;
        if (coverDragDepth === 0) {
            coverPicker.style.borderColor = COLORS.border;
            coverPicker.style.color = COLORS.textDim;
            coverPickerText.textContent = coverPlaceholderText();
        }
    });
    coverPicker.addEventListener("drop", (e) => {
        e.preventDefault();
        coverDragDepth = 0;
        coverPicker.style.borderColor = COLORS.border;
        coverPicker.style.color = COLORS.textDim;
        const files = Array.from(e.dataTransfer?.files || []);
        const file = files.find(isSupportedCoverFile);
        if (file) selectDialogCover(file);
        else selectDialogCover(null);
    });

    const btnRow = document.createElement("div");
    btnRow.style.cssText = `display:flex;justify-content:flex-end;gap:8px;margin-top:14px;`;

    const btnStyle = (primary) =>
        `padding:6px 14px;border-radius:3px;font-size:12px;cursor:pointer;` +
        `border:1px solid ${primary ? COLORS.accent : COLORS.border};` +
        `background:${primary ? COLORS.accent : "transparent"};` +
        `color:${primary ? "#fff" : COLORS.text};`;

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "取消";
    cancelBtn.style.cssText = btnStyle(false);

    const confirmBtn = document.createElement("button");
    confirmBtn.style.cssText = btnStyle(true);

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
            const row = document.createElement("div");
            row.textContent = `与已保存预设「${name}」内容一致`;
            row.style.color = COLORS.textDim;
            diffBox.appendChild(row);
        } else {
            const header = document.createElement("div");
            header.textContent = "覆盖将产生以下变更（+ 新增  − 移除  ~ 强度修改）：";
            header.style.color = COLORS.text;
            diffBox.appendChild(header);
            const mkRow = (sign, text, color) => {
                const row = document.createElement("div");
                row.textContent = `${sign} ${text}`;
                row.style.color = color;
                row.title = text;
                diffBox.appendChild(row);
            };
            for (const e of diff.added) {
                mkRow("+", `${dispName(e)}（model ${fmtStrength(e.strength_model)}）`, COLORS.success);
            }
            for (const e of diff.removed) {
                mkRow("−", `${dispName(e)}（model ${fmtStrength(e.strength_model)}）`, COLORS.danger);
            }
            for (const c of diff.changed) {
                const parts = [];
                if ((c.from.strength_model ?? 1) !== (c.to.strength_model ?? 1)) {
                    parts.push(`model ${fmtStrength(c.from.strength_model)}→${fmtStrength(c.to.strength_model)}`);
                }
                if ((c.from.strength_clip ?? 1) !== (c.to.strength_clip ?? 1)) {
                    parts.push(`clip ${fmtStrength(c.from.strength_clip)}→${fmtStrength(c.to.strength_clip)}`);
                }
                mkRow("~", `${dispName(c.to)}: ${parts.join(", ")}`, COLORS.warn);
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
        if (seq !== diffSeq) return; // 名称已再次变化，丢弃过期结果
        if (!presetData) {
            diffBox.style.display = "none";
            return;
        }
        renderDiffBox(diffPresetData(presetData, getCurrentData(node)), name);
    }

    const close = () => {
        if (dialogCoverUrl) URL.revokeObjectURL(dialogCoverUrl);
        if (dialogOverlay.parentNode) dialogOverlay.parentNode.removeChild(dialogOverlay);
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
        const r = await savePresetData(node, name, dialogCoverFile);
        saving = false;
        confirmBtn.disabled = false;
        if (!r.ok) {
            dialogStatus.style.color = COLORS.danger;
            dialogStatus.textContent = r.error;
            dialogStatus.style.display = "block";
            return;
        }
        if (typeof onSaved === "function") {
            try { await onSaved(); } catch (e) { console.error("[Presets] onSaved callback failed:", e); }
        }
        // 保存成功后数据来源切换为该预设，同步持久化记录
        setLoadedPresetName(node, name);
        if (r.coverError) {
            // 数据已保存，仅封面上传失败：保留对话框便于重新选封面
            dialogStatus.style.color = COLORS.warn;
            dialogStatus.textContent = `预设已保存，但封面上传失败: ${r.coverError}`;
            dialogStatus.style.display = "block";
            return;
        }
        close();
    });

    box.appendChild(title);
    box.appendChild(input);
    box.appendChild(coverPicker);
    box.appendChild(dialogCoverInput);
    box.appendChild(coverError);
    box.appendChild(warn);
    box.appendChild(diffBox);
    box.appendChild(dialogStatus);
    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(confirmBtn);
    box.appendChild(btnRow);
    dialogOverlay.appendChild(box);
    document.body.appendChild(dialogOverlay);
    input.focus();
    input.select();
    updateWarn();
}

/**
 * 创建预设管理模态框
 * @param {Object} node - ComfyUI 节点实例
 * @param {Function} [onImport] - 导入预设后的回调函数（可选）
 */
export function createPresetsModal(node, onImport = null) {
    // 防止重复打开
    if (currentModal) {
        currentModal.focus();
        return;
    }

    // 是否绑定了节点：无节点时进入「仅管理」模式（list/delete/rename/cover 可用，
    // save/export/导入到节点/从文件导入 给出提示并禁用）
    const hasNode = !!node;

    // ========== 创建模态框容器 ==========
    const overlay = document.createElement("div");
    overlay.style.cssText = `
        position:fixed;top:0;left:0;width:100%;height:100%;
        background:rgba(0,0,0,0.6);z-index:10000;
        display:flex;align-items:center;justify-content:center;
    `;

    const modal = document.createElement("div");
    modal.style.cssText = `
        width:min(90vw,900px);max-height:85vh;background:${COLORS.modalBg};
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
    title.textContent = "LoRA 预设管理（支持图片拖拽上传）";
    title.style.cssText = `color:${COLORS.text};font-size:14px;font-weight:600;line-height:1.4;`;

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
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // ========== 搜索工具栏 ==========
    const toolbar = document.createElement("div");
    toolbar.style.cssText = `
        display:flex;align-items:center;gap:12px;padding:8px 16px;
        background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};
    `;

    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "搜索预设...";
    searchInput.style.cssText = `
        flex:1;max-width:100%;padding:7px 10px;background:${COLORS.inputBg};
        border:1px solid ${COLORS.border};border-radius:4px;color:${COLORS.text};
        font-size:12px;outline:none;
    `;
    searchInput.addEventListener("input", () => { applyPresetFilter(); });

    toolbar.appendChild(searchInput);
    modal.appendChild(toolbar);

    // ========== 内容区域 ==========
    const content = document.createElement("div");
    content.style.cssText = `
        flex:1;display:flex;flex-direction:column;gap:10px;
        padding:12px;overflow:hidden;min-height:0;
    `;

    // 预设网格
    const presetList = document.createElement("div");
    presetList.style.cssText = `
        flex:1;min-height:120px;overflow-y:auto;display:grid;
        grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
        gap:12px;padding:8px;background:${COLORS.inputBg};
        border:1px solid ${COLORS.border};border-radius:4px;align-content:start;
    `;
    content.appendChild(presetList);

    // 状态提示
    const statusMsg = document.createElement("div");
    statusMsg.style.cssText = `color:${COLORS.textDim};font-size:11px;text-align:center;min-height:16px;`;
    content.appendChild(statusMsg);

    // ========== 按钮区域 ==========
    const btnGroup = document.createElement("div");
    btnGroup.style.cssText = `display:flex;flex-wrap:wrap;gap:6px;`;

    const createBtn = (text, color, hoverColor) => {
        const btn = document.createElement("button");
        btn.textContent = text;
        btn.style.cssText = `
            flex:1;min-width:80px;padding:8px 12px;border:1px solid ${color};
            background:transparent;color:${color};border-radius:4px;
            cursor:pointer;font-size:12px;transition:all 0.15s;
        `;
        btn.addEventListener("mouseenter", () => {
            btn.style.background = color;
            btn.style.color = "#fff";
        });
        btn.addEventListener("mouseleave", () => {
            btn.style.background = "transparent";
            btn.style.color = color;
        });
        return btn;
    };

    const importBtn = createBtn("导入预设", COLORS.primary);
    const saveBtn = createBtn("保存预设", COLORS.success);
    const deleteBtn = createBtn("删除预设", COLORS.danger);
    const renameBtn = createBtn("重命名", COLORS.textDim);
    const exportBtn = createBtn("导出到文件", COLORS.accent);
    const importFileBtn = createBtn("从文件导入", COLORS.accent);

    // 布局：导入（主操作，蓝色）最左，重命名居中，保存/删除靠右
    btnGroup.appendChild(importBtn);
    btnGroup.appendChild(renameBtn);
    btnGroup.appendChild(saveBtn);
    btnGroup.appendChild(deleteBtn);
    content.appendChild(btnGroup);

    const btnGroup2 = document.createElement("div");
    btnGroup2.style.cssText = `display:flex;gap:6px;`;
    btnGroup2.appendChild(exportBtn);
    btnGroup2.appendChild(importFileBtn);
    content.appendChild(btnGroup2);

    modal.appendChild(content);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // ========== 内部状态 ==========
    let selectedPreset = null;
    let presetItems = [];
    let coverTargetItem = null;

    // 排序方式切换（字母序 / 修改时间倒序），选择持久化到 localStorage
    const PRESET_SORT_MODE_STORAGE_KEY = "naiba_preset_sort_mode";
    let presetSortMode = "name";
    let presetMtimes = {}; // name -> ms，由 /naiba/presets/list 附带返回
    try {
        if (localStorage.getItem(PRESET_SORT_MODE_STORAGE_KEY) === "time") presetSortMode = "time";
    } catch (e) { /* localStorage 不可用时保持默认字母序 */ }

    // 原地重排网格（不重建卡片，避免封面重新加载闪烁）
    function reorderPresetGrid() {
        const items = presetItems.slice();
        if (presetSortMode === "time") {
            items.sort((a, b) =>
                ((presetMtimes[b._name] ?? 0) - (presetMtimes[a._name] ?? 0)) || a._name.localeCompare(b._name)
            );
        } else {
            items.sort((a, b) => a._name.localeCompare(b._name));
        }
        items.forEach((item) => presetList.appendChild(item));
    }

    // 排序按钮（字母序 / 最新优先，与 LoRA 浏览器一致）
    const presetSortBtn = document.createElement("button");
    presetSortBtn.style.cssText = `
        padding:7px 12px;border:1px solid ${COLORS.border};
        border-radius:4px;cursor:pointer;font-size:12px;white-space:nowrap;
    `;
    const updatePresetSortBtnUI = () => {
        if (presetSortMode === "time") {
            presetSortBtn.textContent = "排序: 最新优先";
            presetSortBtn.title = "当前按预设文件修改时间倒序（最新在前），点击恢复字母序";
        } else {
            presetSortBtn.textContent = "排序: 字母序";
            presetSortBtn.title = "当前按字母序，点击切换为修改时间倒序（最新在前）";
        }
        presetSortBtn.style.background = presetSortMode === "time" ? COLORS.accent : "transparent";
        presetSortBtn.style.color = presetSortMode === "time" ? "white" : COLORS.textDim;
        presetSortBtn.style.borderColor = presetSortMode === "time" ? COLORS.accent : COLORS.border;
    };
    presetSortBtn.addEventListener("click", () => {
        presetSortMode = presetSortMode === "time" ? "name" : "time";
        try { localStorage.setItem(PRESET_SORT_MODE_STORAGE_KEY, presetSortMode); } catch (e) { /* 忽略持久化失败 */ }
        updatePresetSortBtnUI();
        reorderPresetGrid();
    });
    updatePresetSortBtnUI();
    toolbar.appendChild(presetSortBtn);

    // 选中已有预设时，保存按钮文案切换为「覆盖预设」，与保存对话框的覆盖语义一致
    const refreshSaveBtnLabel = () => {
        saveBtn.textContent = selectedPreset ? "覆盖预设" : "保存预设";
    };

    // ========== 关闭模态框 ==========
    function closeModal() {
        try {
            document.body.removeChild(overlay);
            currentModal = null;
            document.removeEventListener("keydown", escHandler);
        } catch (e) {
            console.error("[Presets] Error closing modal:", e);
        }
    }

    // 点击遮罩关闭
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeModal();
    });

    // ESC 关闭
    const escHandler = (e) => {
        if (e.key === "Escape") closeModal();
    };
    document.addEventListener("keydown", escHandler);
    overlay._escHandler = escHandler;

    // ========== 显示状态消息 ==========
    function showStatus(msg, isError = false) {
        statusMsg.textContent = msg;
        statusMsg.style.color = isError ? COLORS.danger : COLORS.success;
        setTimeout(() => {
            statusMsg.textContent = "";
        }, 3000);
    }

    // ========== 解析预设（按 sha256 定位改名文件，非破坏性） ==========
    // 导入时调用：返回重定位后的条目；绝不丢弃任何条目。
    // 旧预设（无 sha256）会原样返回，可正常导入。失败时回退到原始数据。
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

    async function applyCoverFile(name, file, item = null) {
        if (!isSupportedCoverFile(file)) {
            showStatus("请选择 PNG、JPG、WEBP 或 GIF 图片", true);
            return;
        }
        if (item?._coverUploading) return;

        if (item) {
            item._coverUploading = true;
            item._setDropActive(false);
            item._setCoverBusy(true);
        }

        try {
            const result = await uploadCover(name, file);
            if (!result.success) {
                showStatus(result.error || "封面上传失败", true);
                return;
            }
            item?._refreshCover();
            showStatus("封面已更新: " + name);
        } catch (err) {
            showStatus("封面上传失败: " + err.message, true);
        } finally {
            if (item) {
                item._coverUploading = false;
                item._setCoverBusy(false);
            }
        }
    }

    // ========== 设置节点数据 ==========
    function setNodeData(data) {
        const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
        if (!loraDataWidget) return;

        const serialized = JSON.stringify(data);

        // 清空现有条目（Multi LoRA Loader 节点）
        if (node._clearAllEntries) {
            node._clearAllEntries();
        }

        // 设置数据
        loraDataWidget.value = serialized;

        // 重建 UI（Multi LoRA Loader 节点）
        if (node._addLoraEntry && data.length > 0) {
            for (const item of data) {
                node._addLoraEntry(item);
            }
        }

        // Multi Loader 的逐条重建会在内部序列化；最后恢复完整导入数据，
        // 确保路径、SHA256 和未知字段不会被中间状态覆盖。
        loraDataWidget.value = serialized;
        
        // 更新显示区域（Visual LoRA Loader 节点）
        if (node._updateVisualLoraDisplay) {
            node._updateVisualLoraDisplay();
        }

        if (node._updateLoraDataPreview) {
            node._updateLoraDataPreview();
        }
        if (node._visualModalReload) {
            node._visualModalReload();
        }
        
        // 触发节点重绘（Visual LoRA Loader 节点）
        if (node._triggerVisualLoraResize) {
            node._triggerVisualLoraResize();
        }

        loraDataWidget.callback?.(loraDataWidget.value, app.canvas, node);
        node.graph?.change?.();
        node.setDirtyCanvas?.(true, true);
        node.graph?.setDirtyCanvas(true, true);
    }

    // ========== 预设搜索过滤（前端即时过滤网格卡片） ==========
    function applyPresetFilter() {
        const q = (searchInput.value || "").toLowerCase().trim();
        for (const item of presetItems) {
            const match = !q || (item._name || "").toLowerCase().includes(q);
            item.style.display = match ? "" : "none";
        }
    }

    // ========== 加载预设列表 ==========
    async function loadPresetList() {
        try {
            const resp = await api.fetchApi("/naiba/presets/list");
            const result = await resp.json();

            if (result.error) {
                showStatus(result.error, true);
                return;
            }

            presetList.innerHTML = "";
            presetItems = [];
            presetMtimes = result.mtimes || {};

            if (result.presets.length === 0) {
                const emptyMsg = document.createElement("div");
                emptyMsg.textContent = "暂无预设";
                emptyMsg.style.cssText = `color:${COLORS.textDim};text-align:center;padding:20px;font-size:12px;grid-column:1/-1;`;
                presetList.appendChild(emptyMsg);
                return;
            }

            // 按当前排序方式决定构建顺序（服务端默认字母序；时间模式最新在前，无时间的排末尾按名称）
            const orderedNames = result.presets.slice();
            if (presetSortMode === "time") {
                orderedNames.sort((a, b) =>
                    ((presetMtimes[b] ?? 0) - (presetMtimes[a] ?? 0)) || a.localeCompare(b)
                );
            }

            for (const name of orderedNames) {
                const item = document.createElement("div");
                item._name = name;
                item._selected = false;
                item.style.cssText = `
                    display:flex;flex-direction:column;gap:6px;padding:8px;border-radius:6px;
                    cursor:pointer;background:${COLORS.listItemBg};border:1px solid transparent;
                    transition:all 0.15s;position:relative;
                `;

                // 封面区（宽高比 1:1，无封面时显示占位）
                const cover = document.createElement("div");
                cover.style.cssText = `
                    width:100%;aspect-ratio:1/1;background:${COLORS.inputBg};
                    border-radius:4px;overflow:hidden;display:flex;align-items:center;
                    justify-content:center;position:relative;
                `;
                const coverImg = document.createElement("img");
                coverImg.style.cssText = "width:100%;height:100%;object-fit:contain;display:none;";
                coverImg.draggable = false;
                const coverPlaceholder = document.createElement("div");
                coverPlaceholder.textContent = "无封面";
                coverPlaceholder.style.cssText = `
                    color:${COLORS.textDim};font-size:11px;text-align:center;padding:4px;
                    display:none;align-items:center;justify-content:center;
                    position:absolute;inset:0;
                `;
                const dropHint = document.createElement("div");
                dropHint.textContent = "松开设置封面";
                dropHint.style.cssText = `
                    position:absolute;inset:0;display:none;align-items:center;justify-content:center;
                    padding:8px;text-align:center;color:#fff;font-size:12px;font-weight:600;
                    background:rgba(108,92,231,0.82);pointer-events:none;
                `;
                const coverAction = document.createElement("div");
                coverAction.textContent = "↑ 更换封面";
                coverAction.title = "选择封面图片";
                coverAction.tabIndex = 0;
                coverAction.setAttribute("role", "button");
                coverAction.style.cssText = `
                    position:absolute;left:0;right:0;bottom:0;display:none;
                    align-items:center;justify-content:center;padding:7px 6px;
                    color:#fff;font-size:11px;background:rgba(0,0,0,0.72);
                    cursor:pointer;
                `;
                coverImg.onload = () => {
                    coverImg.style.display = "block";
                    coverPlaceholder.style.display = "none";
                    coverAction.textContent = "↑ 更换封面";
                };
                coverImg.onerror = () => {
                    coverImg.style.display = "none";
                    coverPlaceholder.style.display = "flex";
                    coverAction.textContent = "＋ 添加封面";
                };
                cover.appendChild(coverImg);
                cover.appendChild(coverPlaceholder);
                cover.appendChild(coverAction);
                cover.appendChild(dropHint);
                item._coverImg = coverImg;
                item._refreshCover = () => {
                    // 先隐藏再加载：404 时浏览器会在 onerror 触发前画出破损图标，先隐藏避免闪烁
                    coverImg.style.display = "none";
                    coverPlaceholder.style.display = "none";
                    coverImg.src = `/naiba/presets/image?name=${encodeURIComponent(item._name)}&t=${Date.now()}`;
                };
                item._setDropActive = (active) => {
                    item._dropActive = active;
                    coverAction.style.display = active ? "none" : coverAction.style.display;
                    dropHint.style.display = active ? "flex" : "none";
                    item.style.background = active
                        ? COLORS.listItemHover
                        : (item._selected ? COLORS.listItemActive : COLORS.listItemBg);
                    item.style.borderColor = active
                        ? COLORS.accent
                        : (item._selected ? COLORS.accent : "transparent");
                };
                item._setCoverBusy = (busy) => {
                    dropHint.textContent = busy ? "正在上传..." : "松开设置封面";
                    dropHint.style.display = busy ? "flex" : "none";
                    coverAction.style.display = busy ? "none" : coverAction.style.display;
                };
                item._refreshCover();
                cover.title = "可拖入图片设置封面";
                cover.addEventListener("mouseenter", () => {
                    if (!item._dropActive && !item._coverUploading) coverAction.style.display = "flex";
                });
                cover.addEventListener("mouseleave", () => {
                    coverAction.style.display = "none";
                });
                const chooseCover = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    coverTargetItem = item;
                    coverFileInput.click();
                };
                coverAction.addEventListener("click", chooseCover);
                coverAction.addEventListener("keydown", (e) => {
                    if (e.key === "Enter" || e.key === " ") chooseCover(e);
                });
                item.appendChild(cover);

                // 名称（单行省略）
                const nameEl = document.createElement("div");
                nameEl.textContent = name;
                nameEl.title = name;
                nameEl.style.cssText = `
                    color:${COLORS.text};font-size:12px;text-align:center;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                `;
                item._nameEl = nameEl;
                item.appendChild(nameEl);

                item.addEventListener("mouseenter", () => {
                    if (item._selected || item._dropActive) return;
                    item.style.background = COLORS.listItemHover;
                    item.style.borderColor = COLORS.border;
                });
                item.addEventListener("mouseleave", () => {
                    if (item._selected || item._dropActive) return;
                    item.style.background = COLORS.listItemBg;
                    item.style.borderColor = "transparent";
                });
                item.addEventListener("click", () => {
                    // 若已选中，则再次点击取消选中
                    if (item._selected) {
                        item._selected = false;
                        item.style.background = COLORS.listItemBg;
                        item.style.borderColor = "transparent";
                        selectedPreset = null;
                        refreshSaveBtnLabel();
                        return;
                    }
                    // 取消其他选中
                    for (const pi of presetItems) {
                        pi._selected = false;
                        pi.style.background = COLORS.listItemBg;
                        pi.style.borderColor = "transparent";
                    }
                    // 选中当前
                    item._selected = true;
                    item.style.background = COLORS.listItemActive;
                    item.style.borderColor = COLORS.accent;
                    selectedPreset = item._name;
                    refreshSaveBtnLabel();
                });

                // 将本地图片拖到某个预设格子，直接替换该预设的封面。
                let dragDepth = 0;
                item.addEventListener("dragenter", (e) => {
                    e.preventDefault();
                    dragDepth += 1;
                    if (!item._coverUploading) item._setDropActive(true);
                });
                item.addEventListener("dragover", (e) => {
                    e.preventDefault();
                    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
                });
                item.addEventListener("dragleave", () => {
                    dragDepth = Math.max(0, dragDepth - 1);
                    if (dragDepth === 0 && !item._coverUploading) item._setDropActive(false);
                });
                item.addEventListener("drop", async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    dragDepth = 0;
                    const files = Array.from(e.dataTransfer?.files || []);
                    const file = files.find(isSupportedCoverFile);
                    if (!file) {
                        item._setDropActive(false);
                        showStatus("请拖入 PNG、JPG、WEBP 或 GIF 图片", true);
                        return;
                    }
                    await applyCoverFile(item._name, file, item);
                });

                // 双击重命名
                item.addEventListener("dblclick", () => {
                    startRename(item, item._name);
                });

                presetItems.push(item);
                presetList.appendChild(item);
            }

            // 应用当前搜索过滤
            applyPresetFilter();
        } catch (e) {
            showStatus("加载预设列表失败: " + e.message, true);
        }
    }

    // ========== 内联重命名 ==========
    function startRename(item, oldName) {
        const input = document.createElement("input");
        input.value = oldName;
        input.style.cssText = `
            width:100%;background:${COLORS.inputBg};border:1px solid ${COLORS.accent};
            color:${COLORS.text};padding:4px 6px;border-radius:3px;font-size:12px;outline:none;
            box-sizing:border-box;
        `;

        // 隐藏名称元素，插入输入框（保留封面，不破坏卡片结构）
        if (item._nameEl) item._nameEl.style.display = "none";
        item.appendChild(input);
        input.focus();
        input.select();

        const restoreName = (text) => {
            if (input.parentNode) input.parentNode.removeChild(input);
            if (item._nameEl) {
                item._nameEl.style.display = "";
                item._nameEl.textContent = text;
            }
        };

        const finishRename = async () => {
            const newName = input.value.trim();
            if (!newName || newName === oldName) {
                restoreName(oldName);
                return;
            }

            try {
                const resp = await api.fetchApi("/naiba/presets/rename", {
                    method: "POST",
                    body: JSON.stringify({ old_name: oldName, new_name: newName }),
                });
                const result = await resp.json();

                if (result.error) {
                    showStatus(result.error, true);
                    restoreName(oldName);
                } else {
                    restoreName(newName);
                    item._name = newName;
                    showStatus("重命名成功");
                    if (selectedPreset === oldName) {
                        selectedPreset = newName;
                    }
                    // 刷新封面（文件名已变更，加时间戳避免缓存）
                    item._refreshCover?.();
                }
            } catch (e) {
                showStatus("重命名失败: " + e.message, true);
                restoreName(oldName);
            }
        };

        input.addEventListener("blur", finishRename);
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") input.blur();
            if (e.key === "Escape") {
                restoreName(oldName);
            }
        });
    }

    // ========== 按钮事件 ==========

    // 仅由卡片封面上的“添加/更换封面”操作触发。
    const coverFileInput = document.createElement("input");
    coverFileInput.type = "file";
    coverFileInput.accept = ".png,.jpg,.jpeg,.webp,.gif";
    coverFileInput.style.display = "none";
    content.appendChild(coverFileInput);

    coverFileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        const item = coverTargetItem;
        coverTargetItem = null;
        coverFileInput.value = "";
        if (!file || !item) return;
        await applyCoverFile(item._name, file, item);
    });

    // 导入预设
    importBtn.addEventListener("click", async () => {
        if (!hasNode) {
            showStatus("请先在画布中放置 Lora Data Preview 节点", true);
            return;
        }
        if (!selectedPreset) {
            showStatus("请先选择一个预设", true);
            return;
        }

        try {
            const resp = await api.fetchApi(`/naiba/presets/load?name=${encodeURIComponent(selectedPreset)}`);
            const result = await resp.json();

            if (result.error) {
                showStatus(result.error, true);
                return;
            }

            showShaProgress();
            try {
                // 按 sha256 重定位改名文件（非破坏性：无 sha256 或本地无匹配则保留原名）
                const resolved = await resolvePreset(result.data);
                // 无论本地是否有所，完整套用所有条目（缺失项由选择器以 (missing) 显示）
                setNodeData(resolved);
                // 记录当前数据来源的预设名（持久化到节点 properties），供保存按钮预填覆盖迭代
                setLoadedPresetName(node, selectedPreset);
                showStatus(`已导入预设: ${selectedPreset}`);
                closeModal();
                // 调用导入回调（如果存在）
                if (typeof onImport === "function") {
                    onImport();
                }
            } finally {
                hideShaProgress();
            }
        } catch (e) {
            console.error("[Presets] Import error:", e);
            showStatus("导入失败: " + e.message, true);
        }
    });

    saveBtn.addEventListener("click", () => {
        if (!hasNode) {
            showStatus("请先在画布中放置 Lora Data Preview 节点", true);
            return;
        }
        openSavePresetDialog(node, {
            defaultName: selectedPreset || "",
            existingNames: presetItems.map((el) => el._name),
            onSaved: async () => {
                await loadPresetList();
                showStatus("预设保存成功");
            },
        });
    });

    // 删除预设
    deleteBtn.addEventListener("click", async () => {
        if (!selectedPreset) {
            showStatus("请先选择一个预设", true);
            return;
        }

        if (!confirm(`确定删除预设 "${selectedPreset}" 吗？`)) return;

        try {
            const resp = await api.fetchApi(`/naiba/presets/delete?name=${encodeURIComponent(selectedPreset)}`, {
                method: "DELETE",
            });
            const result = await resp.json();

            if (result.error) {
                showStatus(result.error, true);
            } else {
                showStatus("预设已删除");
                selectedPreset = null;
                refreshSaveBtnLabel();
                await loadPresetList();
            }
        } catch (e) {
            showStatus("删除失败: " + e.message, true);
        }
    });

    // 重命名
    renameBtn.addEventListener("click", () => {
        if (!selectedPreset) {
            showStatus("请先选择一个预设", true);
            return;
        }

        const item = presetItems.find((el) => el._name === selectedPreset || el._selected);
        if (item) {
            startRename(item, selectedPreset);
        }
    });

    // 导出到本地文件（先经后端补全 sha256，再下载，避免丢失哈希）
    exportBtn.addEventListener("click", async () => {
        if (!hasNode) {
            showStatus("请先在画布中放置 Lora Data Preview 节点", true);
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
    });

    // 从本地文件导入
    importFileBtn.addEventListener("click", () => {
        if (!hasNode) {
            showStatus("请先在画布中放置 Lora Data Preview 节点", true);
            return;
        }
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".json";
        input.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            try {
                const text = await file.text();
                const data = JSON.parse(text);

                if (!Array.isArray(data)) {
                    showStatus("文件格式错误：需要是 JSON 数组", true);
                    return;
                }

                // 验证数据格式
                for (const item of data) {
                    if (!item.name || typeof item.strength_model !== "number") {
                        showStatus("文件格式错误：缺少必要字段", true);
                        return;
                    }
                }

                showShaProgress();
                try {
                    // 按 sha256 重定位改名文件（非破坏性：无 sha256 或本地无匹配则保留原名）
                    const resolved = await resolvePreset(data);
                    // 无论本地是否有所，完整套用所有条目（缺失项由选择器以 (missing) 显示）
                    setNodeData(resolved);
                    // 文件导入无法对应已有预设名，清空来源记录
                    setLoadedPresetName(node, null);
                    showStatus("已从文件导入预设");
                    closeModal();
                    // 调用导入回调（如果存在）
                    if (typeof onImport === "function") {
                        onImport();
                    }
                } finally {
                    hideShaProgress();
                }
            } catch (e) {
                showStatus("文件解析失败: " + e.message, true);
            }
        });
        input.click();
    });

    // ========== 初始化 ==========
    loadPresetList();

    // 设置单例
    currentModal = modal;
    modal.focus = () => {
        overlay.style.display = "flex";
    };
}
