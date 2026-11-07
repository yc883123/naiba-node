/**
 * Naiba Qwen 提示词工作台 - 前端UI扩展(方案A「分段工作台」)
 * 与 goohai 原版的差异:
 * - 顶部模式徽章条(T2I/I2I/反推 自动判定变色)+ llama-cpp 依赖状态横幅
 * - 图像 chip 条带(计数 + 缩略 + 加端口按钮),替代原版的匿名端口堆叠
 * - 自适应高度提示词编辑区(字数统计/清空按钮/随模式变化的占位文案)
 * - 参数区分「模型 / 参数」两个分区,输出语言挪进提示词操作行,种子一行内聚 + 🎲 随机按钮
 * - 常驻按钮用 naiba 低饱和暗色调(高饱和亮色只做状态点缀)
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ========== 颜色常量(与 visual_lora_loader 保持同一 naiba 色板) ==========
const COLORS = {
    headerBg: "#16213e",
    contentBg: "#0f1729",
    accent: "#6c5ce7",
    accentHover: "#7c6cf7",
    success: "#2ed573",
    warning: "#ffa502",
    text: "#e0e0e0",
    textDim: "#888",
    border: "#2a3a5c",
    inputBg: "#0a0f1e",
    cardBg: "#16213e",
    // 节点常驻按钮低饱和色(naiba 设计哲学:高饱和色只留给弹窗一次性动作)
    btnPrimary: "#5544a6",
    btnPrimaryHover: "#6352b8",
    btnDanger: "#b0524d",
    btnDangerHover: "#c26863",
    toggleOff: "#3a3a5a",
};

const NODE_NAME = "NaibaQwenPromptOptimizer";
const LLAMA_STATUS_ROUTE = "/naiba/qwen_prompt_optimizer/llama_status";
const LLAMA_INSTALL_ROUTE = "/naiba/qwen_prompt_optimizer/install_llama";
const MAX_IMAGES = 10;
const MIN_PROMPT_HEIGHT = 120;
const MAX_PROMPT_HEIGHT = 320;
const PROMPT_WIDGET_NAMES = new Set(["用户提示词", "user_prompt"]);
const LANG_WIDGET_NAMES = new Set(["输出语言", "output_language"]);
const SEED_WIDGET_NAMES = new Set(["种子值", "seed"]);
const SEED_MODE_WIDGET_NAMES = new Set(["种子模式", "seed_mode"]);
const LAST_SEED_MODE_PROPERTY = "naiba_last_executed_seed_mode";
const imageName = (index) => `图像_${String(index + 1).padStart(2, "0")}`;
const isImageInput = (slot) => {
    const name = String(slot?.name || "");
    return name.startsWith("图像_") || name.startsWith("image_");
};

function el(tag, style, text) {
    const node = document.createElement(tag);
    if (style) node.style.cssText = style;
    if (text != null) node.textContent = text;
    return node;
}

// ========== 模式判定 ==========
function detectMode(connectedCount, promptText) {
    if (connectedCount <= 0) return { key: "t2i", label: "文生图 T2I" };
    if (String(promptText || "").trim()) return { key: "i2i", label: "图生图 I2I" };
    return { key: "reverse", label: "反推 REVERSE" };
}

const MODE_BADGE_STYLE = {
    t2i: { background: "rgba(108,92,231,.18)", border: "#6c5ce7", color: "#a99cf5" },
    i2i: { background: "rgba(58,95,143,.28)", border: "#5b82b8", color: "#9cc0ec" },
    reverse: { background: "rgba(255,165,2,.15)", border: "#ffa502", color: "#ffc14d" },
};

const PLACEHOLDER_BY_MODE = {
    t2i: "描述想生成的画面，口语化即可。例如：一只戴宇航员头盔的橘猫，漂浮在粉紫色星云里，皮克斯风格…",
    i2i: "描述要如何修改输入图像。例如：把背景换成雪山日出，保持人物姿势和服装不变…",
    reverse: "反推模式：提示词留空即可，直接根据输入图像反推生成提示词。",
};

// ========== 依赖状态(模块级共享,所有实例同用一份结果) ==========
let _llamaStatusCache = null;
const _llamaStatusListeners = new Set();

async function fetchLlamaStatus(force = false) {
    if (_llamaStatusCache && !force) return _llamaStatusCache;
    try {
        const response = await api.fetchApi(LLAMA_STATUS_ROUTE, { cache: "no-store" });
        if (!response.ok) return null;
        _llamaStatusCache = await response.json();
    } catch {
        return _llamaStatusCache;
    }
    _llamaStatusListeners.forEach((fn) => fn(_llamaStatusCache));
    return _llamaStatusCache;
}

function dependencyMessage(message, success = false) {
    const text = String(message || "未知错误");
    const escaped = text
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;")
        .replaceAll("\n", "<br>");
    const content = success
        ? `<div style="display:flex;align-items:flex-start;gap:12px;color:#2ed573;line-height:1.7;">`
            + `<span style="display:inline-flex;align-items:center;justify-content:center;flex:0 0 28px;width:28px;height:28px;border-radius:50%;background:#2ed573;color:#fff;font-size:20px;font-weight:700;line-height:1;">✓</span>`
            + `<div>${escaped}</div></div>`
        : escaped;
    if (app.ui?.dialog?.show) app.ui.dialog.show(content);
    else window.alert(text);
}

// ========== 图像端口同步(移植自 goohai:保持「最后已连 + 2」个端口) ==========
function syncImagePorts(node) {
    let inputs = node.inputs || [];
    let imageIndexes = inputs
        .map((slot, index) => ({ slot, index }))
        .filter(({ slot }) => isImageInput(slot));
    if (!imageIndexes.length) {
        node.addInput(imageName(0), "IMAGE");
        imageIndexes = [{ slot: node.inputs[node.inputs.length - 1], index: node.inputs.length - 1 }];
    }
    let lastConnected = -1;
    imageIndexes.forEach(({ slot }, imageIndex) => {
        if (slot?.link != null) lastConnected = Math.max(lastConnected, imageIndex);
    });
    const target = Math.min(MAX_IMAGES, Math.max(1, lastConnected + 2));
    while (imageIndexes.length > target) {
        const last = imageIndexes[imageIndexes.length - 1];
        if (last.slot?.link != null) break;
        node.removeInput(last.index);
        imageIndexes = (node.inputs || [])
            .map((slot, index) => ({ slot, index }))
            .filter(({ slot }) => isImageInput(slot));
    }
    while (imageIndexes.length < target) {
        node.addInput(imageName(imageIndexes.length), "IMAGE");
        imageIndexes = (node.inputs || [])
            .map((slot, index) => ({ slot, index }))
            .filter(({ slot }) => isImageInput(slot));
    }
    let number = 0;
    for (const slot of node.inputs || []) {
        if (!isImageInput(slot)) continue;
        slot.name = imageName(number);
        slot.label = `图像 ${number + 1}`;
        number += 1;
    }
}

// ========== 图像缩略(尽力而为:读上游节点预览,拿不到退化成连接状态点) ==========
function upstreamImageSrc(node, slot) {
    try {
        const link = slot?.link;
        if (link == null) return null;
        const linkObj = app.graph?.links?.[link];
        const srcNode = linkObj ? app.graph?._nodes_by_id?.[linkObj.origin_id] : null;
        const img = srcNode?.imgs?.[0];
        if (img?.src) return img.src;
        if (img instanceof Image || img?.complete) return img?.src || null;
    } catch { /* 预览缺失不致命 */ }
    return null;
}

// ========== 种子随机(移植自 goohai 的队列期随机逻辑) ==========
function nextRandomSeed() {
    if (globalThis.crypto?.getRandomValues) {
        const value = new Uint32Array(1);
        globalThis.crypto.getRandomValues(value);
        return Number(value[0]) || 1;
    }
    return (Math.floor(Math.random() * 0xFFFFFFFF) + 1) >>> 0;
}

function prepareRuntimeSeeds() {
    const nodes = app.graph?._nodes || (app.graph?._nodes_by_id && Object.values(app.graph._nodes_by_id)) || [];
    for (const node of nodes) {
        if (node?.comfyClass !== NODE_NAME && node?.type !== NODE_NAME) continue;
        const mode = node.widgets?.find((item) => SEED_MODE_WIDGET_NAMES.has(item.name))?.value;
        if (mode === "随机") {
            const seedWidget = node.widgets?.find((item) => SEED_WIDGET_NAMES.has(item.name));
            if (seedWidget) {
                seedWidget.value = nextRandomSeed();
                seedWidget.callback?.(seedWidget.value);
            }
        }
    }
}

function prepareRuntimeSeedModes() {
    const nodes = app.graph?._nodes || (app.graph?._nodes_by_id && Object.values(app.graph._nodes_by_id)) || [];
    const restores = [];
    for (const node of nodes) {
        if (node?.comfyClass !== NODE_NAME && node?.type !== NODE_NAME) continue;
        const widget = node.widgets?.find((item) => SEED_MODE_WIDGET_NAMES.has(item.name));
        if (!widget) continue;
        const selectedMode = widget.value;
        const lastExecutedMode = node._naibaLastExecutedSeedMode || node.properties?.[LAST_SEED_MODE_PROPERTY];
        const queuedMode = selectedMode === "固定" && lastExecutedMode === "随机" ? "随机" : selectedMode;
        node._naibaQueuedSeedMode = selectedMode;
        if (queuedMode !== selectedMode) {
            widget.value = queuedMode;
            restores.push(() => { widget.value = selectedMode; });
        }
    }
    return restores;
}

function installQueueSeedHook() {
    if (app._naibaQwenRuntimeSeedHook) return;
    if (typeof app.queuePrompt !== "function") {
        setTimeout(installQueueSeedHook, 250);
        return;
    }
    const originalQueuePrompt = app.queuePrompt;
    app.queuePrompt = async function () {
        prepareRuntimeSeeds();
        const restores = prepareRuntimeSeedModes();
        try {
            return await originalQueuePrompt.apply(this, arguments);
        } finally {
            for (const restore of restores.reverse()) restore();
        }
    };
    app._naibaQwenRuntimeSeedHook = true;
}

// ========== 主扩展 ==========
app.registerExtension({
    name: "naiba.qwen_prompt_optimizer",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== NODE_NAME) return;
        installQueueSeedHook();

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            originalCreated?.apply(this, arguments);
            const node = this;

            // ---------- 本地 widget 引用 ----------
            const findWidget = (names) => node.widgets?.find((item) => names.has(item.name));
            const promptWidget = findWidget(PROMPT_WIDGET_NAMES);
            const langWidget = findWidget(LANG_WIDGET_NAMES);

            // ---------- 顶部容器:徽章条 + 依赖横幅 + 图像条带 + 提示词区 + 模型分区头 ----------
            const container = el("div", "display:flex;flex-direction:column;gap:6px;width:100%;box-sizing:border-box;padding:2px;");

            // --- 1. 模式徽章条 ---
            const modeBar = el("div", `background:${COLORS.cardBg};border:1px solid ${COLORS.border};border-radius:6px;padding:6px 10px;display:flex;justify-content:space-between;align-items:center;gap:8px;`);
            const modeBadge = el("span", "border-radius:4px;font-size:10px;padding:2px 8px;font-weight:500;white-space:nowrap;", "文生图 T2I");
            const statusArea = el("div", "display:flex;align-items:center;gap:6px;min-width:0;");
            const statusDot = el("span", `width:8px;height:8px;border-radius:50%;background:${COLORS.toggleOff};flex-shrink:0;`);
            const statusText = el("span", `font-size:10px;color:${COLORS.textDim};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;`, "llama-cpp 检测中…");
            statusArea.append(statusDot, statusText);
            modeBar.append(modeBadge, statusArea);
            container.appendChild(modeBar);

            const applyMode = () => {
                const connectedCount = (node.inputs || []).filter((slot) => isImageInput(slot) && slot.link != null).length;
                const mode = detectMode(connectedCount, promptWidget?.value);
                const style = MODE_BADGE_STYLE[mode.key];
                modeBadge.textContent = mode.label;
                modeBadge.style.background = style.background;
                modeBadge.style.border = `1px solid ${style.border}`;
                modeBadge.style.color = style.color;
                if (promptArea) promptArea.placeholder = PLACEHOLDER_BY_MODE[mode.key];
            };

            // --- 2. 依赖横幅(未安装时显示;就绪时隐藏) ---
            const depBanner = el("div", "display:none;background:rgba(255,165,2,.12);border:1px solid #ffa502;border-radius:6px;padding:8px 10px;font-size:11px;color:#ffd28a;line-height:1.6;flex-direction:column;gap:6px;");
            const depText = el("div", "", "");
            const depBtnRow = el("div", "display:flex;gap:6px;align-items:center;");
            const depBtn = el("button", `background:${COLORS.btnPrimary};color:#fff;border:none;border-radius:6px;padding:5px 10px;font-size:11px;cursor:pointer;`, "一键安装");
            const depManual = el("button", `background:transparent;color:${COLORS.textDim};border:none;border-radius:6px;padding:5px 6px;font-size:11px;cursor:pointer;text-decoration:underline;`, "手动安装指引");
            depBtnRow.append(depBtn, depManual);
            depBanner.append(depText, depBtnRow);
            container.appendChild(depBanner);

            const setLlamaStatus = (status) => {
                if (!status) return;
                if (status.needs_install) {
                    statusDot.style.background = COLORS.warning;
                    statusText.textContent = "llama-cpp 未就绪";
                    depText.textContent = `${status.reason}（需要 ${status.minimum_version}+，自动匹配 ${status.backend || status.system} wheel）`;
                    depBanner.style.display = "flex";
                    depBtn.disabled = status.supported !== true;
                    depBtn.style.opacity = status.supported === true ? "1" : "0.5";
                } else {
                    statusDot.style.background = COLORS.success;
                    statusText.textContent = "llama-cpp 就绪";
                    depBanner.style.display = "none";
                }
            };
            _llamaStatusListeners.add(setLlamaStatus);
            fetchLlamaStatus().then(setLlamaStatus);

            depBtn.addEventListener("click", async () => {
                const status = await fetchLlamaStatus(true);
                if (!status?.needs_install) { setLlamaStatus(status); return; }
                if (status.supported !== true) {
                    dependencyMessage(`${status.reason}\n请从以下地址手动安装：\n${status.release_url}`);
                    window.open(status.release_url, "_blank", "noopener,noreferrer");
                    return;
                }
                const confirmed = window.confirm(
                    `${status.installed_version ? `当前 llama-cpp-python 版本：${status.installed_version}` : "当前未安装 llama-cpp-python"}`
                    + `\n\n将使用当前 ComfyUI 的 Python 自动安装匹配 ${status.backend} 的最新官方 wheel。安装后必须完全重启 ComfyUI。`
                    + "此安装需从 GitHub 下载轮子，请确保网络能正常访问 GitHub。是否继续？",
                );
                if (!confirmed) return;
                depBtn.disabled = true;
                depBtn.textContent = "安装中…";
                try {
                    const response = await api.fetchApi(LLAMA_INSTALL_ROUTE, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ confirm: true }),
                    });
                    const result = await response.json();
                    if (!response.ok || !result?.success) throw new Error(result?.message || `HTTP ${response.status}`);
                    dependencyMessage(`${result.message}\n\n已安装：${result.wheel}`, true);
                } catch (error) {
                    dependencyMessage(`llama-cpp-python 安装失败：\n${error?.message || error}\n\n可前往发布页手动安装：\n${status.release_url}`);
                } finally {
                    depBtn.disabled = false;
                    depBtn.textContent = "一键安装";
                    setLlamaStatus(await fetchLlamaStatus(true));
                }
            });
            depManual.addEventListener("click", async () => {
                const status = await fetchLlamaStatus(true);
                window.open(status?.release_url || "https://github.com/JamePeng/llama-cpp-python/releases", "_blank", "noopener,noreferrer");
            });

            // --- 3. 图像条带 ---
            const strip = el("div", `background:${COLORS.contentBg};border:1px solid ${COLORS.border};border-radius:6px;padding:6px 8px;display:flex;flex-direction:column;gap:6px;`);
            const stripHead = el("div", "display:flex;justify-content:space-between;align-items:center;");
            const stripLabel = el("span", `font-size:10px;color:${COLORS.textDim};letter-spacing:1px;`, "输入图像 0/10");
            const addBtn = el("button", `background:transparent;border:1px dashed ${COLORS.border};border-radius:6px;color:${COLORS.textDim};font-size:11px;padding:2px 8px;cursor:pointer;`, "＋ 加端口");
            stripHead.append(stripLabel, addBtn);
            const chipRow = el("div", "display:flex;flex-wrap:wrap;gap:6px;");
            strip.append(stripHead, chipRow);
            container.appendChild(strip);

            const renderChips = () => {
                chipRow.textContent = "";
                const imageSlots = (node.inputs || []).filter((slot) => isImageInput(slot));
                let connected = 0;
                imageSlots.forEach((slot, index) => {
                    const isConnected = slot.link != null;
                    if (isConnected) connected += 1;
                    const chip = el("div", `width:44px;height:44px;border-radius:6px;background:${COLORS.inputBg};border:1px solid ${isConnected ? COLORS.success : COLORS.border};${isConnected ? `box-shadow:0 0 0 2px rgba(46,213,115,.25);` : ""}overflow:hidden;display:flex;align-items:center;justify-content:center;position:relative;flex-shrink:0;`);
                    chip.title = isConnected ? `图像 ${index + 1}（已连接）` : `图像 ${index + 1}（未连接）`;
                    const src = isConnected ? upstreamImageSrc(node, slot) : null;
                    if (src) {
                        const img = document.createElement("img");
                        img.src = src;
                        img.style.cssText = "width:100%;height:100%;object-fit:cover;display:block;pointer-events:none;";
                        chip.appendChild(img);
                    } else {
                        const tag = el("span", `font-size:10px;color:${isConnected ? COLORS.success : COLORS.textDim};`, isConnected ? "已连" : `图${index + 1}`);
                        chip.appendChild(tag);
                    }
                    chipRow.appendChild(chip);
                });
                stripLabel.textContent = `输入图像 ${connected}/${MAX_IMAGES}`;
                addBtn.disabled = imageSlots.length >= MAX_IMAGES;
                addBtn.style.opacity = addBtn.disabled ? "0.35" : "1";
                applyMode();
            };
            addBtn.addEventListener("click", () => {
                const count = (node.inputs || []).filter((slot) => isImageInput(slot)).length;
                if (count >= MAX_IMAGES) return;
                node.addInput(imageName(count), "IMAGE");
                syncImagePorts(node);
                renderChips();
            });

            // --- 4. 提示词区 ---
            const promptCard = el("div", `background:${COLORS.contentBg};border:1px solid ${COLORS.border};border-radius:6px;padding:8px;display:flex;flex-direction:column;gap:6px;`);
            const promptHead = el("div", "display:flex;justify-content:space-between;align-items:center;");
            const promptTitle = el("span", `font-size:10px;color:${COLORS.textDim};letter-spacing:1px;`, "提示词");
            const clearBtn = el("button", `background:${COLORS.btnDanger};color:#fff;border:none;border-radius:6px;padding:3px 10px;font-size:11px;cursor:pointer;`, "清空");
            promptHead.append(promptTitle, clearBtn);
            const promptArea = document.createElement("textarea");
            promptArea.rows = 3;
            promptArea.placeholder = PLACEHOLDER_BY_MODE.t2i;
            promptArea.style.cssText = `background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:5px;color:${COLORS.text};font-size:13px;line-height:1.55;padding:8px 10px;min-height:${MIN_PROMPT_HEIGHT}px;max-height:${MAX_PROMPT_HEIGHT}px;resize:none;overscroll-behavior:contain;box-sizing:border-box;width:100%;font-family:inherit;`;
            promptArea.addEventListener("focus", () => { promptArea.style.borderColor = COLORS.accent; });
            promptArea.addEventListener("blur", () => { promptArea.style.borderColor = COLORS.border; });
            const metaRow = el("div", "display:flex;justify-content:space-between;align-items:center;gap:8px;");
            const charCount = el("span", `font-size:10px;color:${COLORS.textDim};`, "0 字");
            const langWrap = el("div", "display:flex;align-items:center;gap:6px;");
            const langLabel = el("span", `font-size:10px;color:${COLORS.textDim};`, "语言");
            const langSelect = document.createElement("select");
            langSelect.style.cssText = `background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:5px;color:${COLORS.text};font-size:11px;padding:3px 6px;cursor:pointer;`;
            for (const option of ["自动", "中文", "English"]) {
                const opt = document.createElement("option");
                opt.value = option;
                opt.textContent = option;
                langSelect.appendChild(opt);
            }
            langWrap.append(langLabel, langSelect);
            metaRow.append(charCount, langWrap);
            promptCard.append(promptHead, promptArea, metaRow);
            container.appendChild(promptCard);

            const syncPromptFromWidget = () => {
                const value = String(promptWidget?.value ?? "");
                if (promptArea.value !== value) {
                    promptArea.value = value;
                    charCount.textContent = `${value.length} 字`;
                    applyMode();
                }
            };
            promptArea.addEventListener("input", () => {
                if (promptWidget) {
                    promptWidget.value = promptArea.value;
                    promptWidget.callback?.(promptArea.value);
                }
                charCount.textContent = `${promptArea.value.length} 字`;
                // 自适应长高
                promptArea.style.height = "auto";
                promptArea.style.height = `${Math.min(MAX_PROMPT_HEIGHT, Math.max(MIN_PROMPT_HEIGHT, promptArea.scrollHeight))}px`;
                applyMode();
                node.graph?.change();
            });
            clearBtn.addEventListener("click", () => {
                promptArea.value = "";
                if (promptWidget) {
                    promptWidget.value = "";
                    promptWidget.callback?.("");
                }
                charCount.textContent = "0 字";
                applyMode();
                node.graph?.change();
            });
            langSelect.addEventListener("change", () => {
                if (langWidget) {
                    langWidget.value = langSelect.value;
                    langWidget.callback?.(langSelect.value);
                }
                node.graph?.change();
            });
            const syncLangFromWidget = () => {
                const value = String(langWidget?.value ?? "自动");
                if (langSelect.value !== value) langSelect.value = value;
            };

            // --- 5. 「模型」分区头(作为容器最后一行,视觉上衔接下方原生下拉) ---
            const modelSection = el("div", "display:flex;align-items:center;gap:6px;margin-top:2px;");
            modelSection.append(
                el("span", `width:3px;height:10px;background:${COLORS.accent};border-radius:2px;flex-shrink:0;`),
                el("span", `color:${COLORS.textDim};font-size:10px;letter-spacing:1px;`, "模型"),
                el("span", `flex:1;height:1px;background:${COLORS.border};`),
            );
            container.appendChild(modelSection);

            // ---------- 注册 DOM widget 并防塌缩 ----------
            const measureContainerHeight = () => {
                const h = Math.ceil(container.scrollHeight || 0);
                return h > 0 ? h : 200;
            };
            const domWidget = node.addDOMWidget("naiba_qwen_top_container", "NAIBA_QWEN_TOP_CONTAINER", container, {
                getValue() { return ""; },
                setValue() {},
                getMinHeight() { return measureContainerHeight(); },
            });
            const panelEl = domWidget.element || container;
            [panelEl, container].forEach((elx) => {
                if (!elx) return;
                elx.classList.remove("h-full");
                elx.style.height = "auto";
                elx.style.minHeight = "max-content";
            });
            domWidget.computeSize = (w) => [w, measureContainerHeight()];

            // ---------- 「参数」分区头 DOM widget(插在透明背景前) ----------
            const paramSection = el("div", "display:flex;align-items:center;gap:6px;padding:0 2px;");
            paramSection.append(
                el("span", `width:3px;height:10px;background:${COLORS.accent};border-radius:2px;flex-shrink:0;`),
                el("span", `color:${COLORS.textDim};font-size:10px;letter-spacing:1px;`, "参数"),
                el("span", `flex:1;height:1px;background:${COLORS.border};`),
            );
            const paramWidget = node.addDOMWidget("naiba_qwen_param_section", "NAIBA_QWEN_PARAM_SECTION", paramSection, {
                getValue() { return ""; },
                setValue() {},
                getMinHeight() { return 18; },
            });
            const paramPanelEl = paramWidget.element || paramSection;
            [paramPanelEl, paramSection].forEach((elx) => {
                if (!elx) return;
                elx.classList.remove("h-full");
                elx.style.height = "auto";
                elx.style.minHeight = "max-content";
            });
            paramWidget.computeSize = (w) => [w, 18];

            // ---------- 隐藏被 DOM 接管的原生 widget(留在数组里保序列化) ----------
            for (const widget of [promptWidget, langWidget]) {
                if (!widget) continue;
                widget.hidden = true;
                if (widget.inputEl) widget.inputEl.style.display = "none";
            }

            // ---------- 🎲 随机按钮 ----------
            const seedWidgetRef = findWidget(SEED_WIDGET_NAMES);
            const diceWidget = node.addWidget("button", "🎲 随机种子", null, () => {
                const seedWidget = findWidget(SEED_WIDGET_NAMES);
                const modeWidget = findWidget(SEED_MODE_WIDGET_NAMES);
                if (seedWidget) {
                    seedWidget.value = nextRandomSeed();
                    seedWidget.callback?.(seedWidget.value);
                }
                if (modeWidget) {
                    modeWidget.value = "随机";
                    modeWidget.callback?.("随机");
                }
                node.graph?.change();
                node.setDirtyCanvas?.(true, true);
            });
            diceWidget.serialize = false;
            diceWidget.options = { ...(diceWidget.options || {}), serialize: false };

            // ---------- widget 排序:顶部容器 → 模型下拉 → 参数分区 → 参数(dice 插在种子值后) → 隐藏 widget ----------
            const managed = new Set([domWidget, paramWidget, diceWidget]);
            const modelNames = new Set(["文生图模型", "图生图模型", "视觉模型"]);
            const rest = (node.widgets || []).filter((w) => !managed.has(w));
            const ordered = [domWidget, ...rest.filter((w) => modelNames.has(w.name)), paramWidget];
            for (const w of rest) {
                if (modelNames.has(w.name)) continue;
                ordered.push(w);
                if (w === seedWidgetRef) ordered.push(diceWidget);
            }
            node.widgets.length = 0;
            for (const w of ordered) node.widgets.push(w);

            // ---------- 尺寸收敛(tag_picker 套路,只收高度不劫持宽度) ----------
            node.minWidth = 320;
            node.minHeight = 320;
            const applyContainerHeight = () => {
                if (typeof node.computeSize !== "function") return;
                const cs = node.computeSize();
                if (!cs || !cs[1]) return;
                if (Math.abs((node.size?.[1] || 0) - cs[1]) > 4) {
                    node.setSize?.([node.size?.[0] || 360, cs[1]]);
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

            // ---------- 连接变化 → 端口同步 + chips 刷新(挂实例,供原型钩子调用) ----------
            let _syncQueued = false;
            let _chipTimers = [];
            const scheduleSync = () => {
                if (_syncQueued) return;
                _syncQueued = true;
                requestAnimationFrame(() => {
                    _syncQueued = false;
                    syncImagePorts(node);
                    renderChips();
                    applyContainerHeight();
                });
                // 预览图加载是异步的,延迟两次刷新拿缩略
                for (const timer of _chipTimers) clearTimeout(timer);
                _chipTimers = [600, 1600].map((delay) => setTimeout(renderChips, delay));
            };
            node._naibaQwenScheduleSync = scheduleSync;
            node._naibaQwenSyncViews = () => {
                syncPromptFromWidget();
                syncLangFromWidget();
            };
            node._naibaQwenTeardown = () => {
                _llamaStatusListeners.delete(setLlamaStatus);
                for (const timer of _chipTimers) clearTimeout(timer);
                _chipTimers = [];
                if (_resizeRaf) cancelAnimationFrame(_resizeRaf);
            };

            // ---------- 初始化 ----------
            requestAnimationFrame(() => {
                syncImagePorts(node);
                renderChips();
                syncPromptFromWidget();
                syncLangFromWidget();
                promptArea.style.height = `${Math.min(MAX_PROMPT_HEIGHT, Math.max(MIN_PROMPT_HEIGHT, promptArea.scrollHeight))}px`;
                applyContainerHeight();
            });
        };

        // ---------- 原型级钩子(beforeRegisterNodeDef 只走一次,不随实例叠加) ----------
        const origOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            origOnConnectionsChange?.apply(this, arguments);
            this._naibaQwenScheduleSync?.();
        };

        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            origOnConfigure?.apply(this, arguments);
            this._naibaQwenScheduleSync?.();
            this._naibaQwenSyncViews?.();
        };

        const origOnExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            origOnExecuted?.apply(this, arguments);
            const seed = Array.isArray(message?.seed) ? message.seed[0] : message?.seed;
            const seedWidget = this.widgets?.find((item) => SEED_WIDGET_NAMES.has(item.name));
            if (seedWidget && Number.isFinite(Number(seed))) {
                seedWidget.value = Number(seed);
                seedWidget.callback?.(seedWidget.value);
            }
            if (this._naibaQueuedSeedMode) {
                this._naibaLastExecutedSeedMode = this._naibaQueuedSeedMode;
                this.properties = this.properties || {};
                this.properties[LAST_SEED_MODE_PROPERTY] = this._naibaQueuedSeedMode;
            }
        };

        const origOnRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            this._naibaQwenTeardown?.();
            return origOnRemoved?.apply(this, arguments);
        };
    },
});
