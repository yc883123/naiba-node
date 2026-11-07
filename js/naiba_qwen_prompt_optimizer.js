import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "NaibaQwenPromptOptimizer";
const STATUS_ROUTE = "/naiba/qwen_prompt_optimizer/llama_status";
const INSTALL_ROUTE = "/naiba/qwen_prompt_optimizer/install_llama";
const IMAGE_PREFIX = "图像_";
const PROMPT_NAMES = new Set(["用户提示词", "user_prompt"]);
const LANG_NAMES = new Set(["输出语言", "output_language"]);
const SEED_NAMES = new Set(["种子值", "seed"]);
const COLORS = { panel: "#18212b", surface: "#111820", border: "#34414d", text: "#e2e7eb", muted: "#9aa7b2", good: "#78a98b", warning: "#d4a75f", button: "#40545b" };
const MODE_LABELS = { t2i: "T2I · 文生图", i2i: "I2I · 图生图", reverse: "反推 · 图像理解" };

function element(tag, css, text) {
    const result = document.createElement(tag);
    if (css) result.style.cssText = css;
    if (text != null) result.textContent = text;
    return result;
}

function imageInputs(node) {
    return (node.inputs || []).filter((input) => String(input?.name || "").startsWith(IMAGE_PREFIX));
}

function randomSeed() {
    const value = new Uint32Array(1);
    globalThis.crypto?.getRandomValues?.(value);
    return value[0] || ((Math.floor(Math.random() * 0xffffffff) + 1) >>> 0);
}

function modeFor(node, promptWidget) {
    const hasImages = imageInputs(node).some((input) => input.link != null);
    if (!hasImages) return null;
    const promptConnected = (node.inputs || []).some((input) => PROMPT_NAMES.has(input?.name) && input.link != null);
    return promptConnected || String(promptWidget?.value || "").trim() ? "i2i" : "reverse";
}

function upstreamPreview(slot) {
    const link = slot?.link;
    const info = link == null ? null : app.graph?.links?.[link];
    const source = info ? app.graph?._nodes_by_id?.[info.origin_id] : null;
    return source?.imgs?.[0]?.src || null;
}

let statusCache = null;
const statusListeners = new Set();
async function fetchStatus(force = false) {
    if (statusCache && !force) return statusCache;
    try {
        const response = await api.fetchApi(STATUS_ROUTE, { cache: "no-store" });
        if (!response.ok) return statusCache;
        statusCache = await response.json();
        statusListeners.forEach((listener) => listener(statusCache));
    } catch {
        return statusCache;
    }
    return statusCache;
}

function showMessage(message, success = false) {
    const content = document.createElement("div");
    content.textContent = String(message || "未知错误");
    content.style.cssText = `color:${success ? COLORS.good : COLORS.text};white-space:pre-wrap;line-height:1.6;`;
    if (app.ui?.dialog?.show) app.ui.dialog.show(content);
    else window.alert(content.textContent);
}

app.registerExtension({
    name: "naiba.qwen_prompt_optimizer",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== NODE_NAME) return;

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            originalCreated?.apply(this, arguments);
            const node = this;
            const widget = (names) => node.widgets?.find((item) => names.has(item.name));
            const prompt = widget(PROMPT_NAMES);
            const language = widget(LANG_NAMES);
            const root = element("div", "display:flex;flex-direction:column;gap:7px;width:100%;box-sizing:border-box;padding:2px;");

            const modeBar = element("div", `display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 9px;background:${COLORS.panel};border:1px solid ${COLORS.border};border-radius:5px;`);
            const badge = element("span", "padding:3px 7px;border-radius:3px;background:#263741;color:#b8c8cc;font-size:11px;font-weight:600;white-space:nowrap;", MODE_LABELS.i2i);
            const dependency = element("span", `min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:${COLORS.muted};font-size:11px;`, "llama-cpp 检测中");
            modeBar.append(badge, dependency);
            root.appendChild(modeBar);

            const banner = element("div", `display:none;flex-direction:column;gap:7px;padding:8px 9px;background:#392f20;border:1px solid ${COLORS.warning};border-radius:5px;color:#ead2a5;font-size:11px;line-height:1.5;`);
            const bannerText = element("div");
            const actions = element("div", "display:flex;gap:7px;align-items:center;");
            const installButton = element("button", `padding:5px 9px;border:0;border-radius:4px;background:${COLORS.button};color:${COLORS.text};font-size:11px;cursor:pointer;`, "确认安装");
            const manualButton = element("button", `padding:5px 7px;border:0;background:transparent;color:${COLORS.muted};font-size:11px;text-decoration:underline;cursor:pointer;`, "手动安装");
            actions.append(installButton, manualButton);
            banner.append(bannerText, actions);
            root.appendChild(banner);

            const setStatus = (status) => {
                if (!status) return;
                if (status.needs_install) {
                    dependency.textContent = "llama-cpp 未就绪";
                    dependency.style.color = COLORS.warning;
                    bannerText.textContent = `${status.reason || "需要安装 llama-cpp-python"}（最低版本 ${status.minimum_version || "未知"}，匹配后端 ${status.backend || status.system || "未知"}）`;
                    banner.style.display = "flex";
                    installButton.disabled = status.supported !== true;
                    installButton.style.opacity = installButton.disabled ? "0.5" : "1";
                } else {
                    dependency.textContent = "llama-cpp 已就绪";
                    dependency.style.color = COLORS.good;
                    banner.style.display = "none";
                }
            };
            statusListeners.add(setStatus);
            fetchStatus().then(setStatus);

            installButton.addEventListener("click", async () => {
                const status = await fetchStatus(true);
                if (!status?.needs_install) { setStatus(status); return; }
                if (status.supported !== true) {
                    showMessage(`${status.reason || "当前环境不支持自动安装"}\n请从发布页手动安装：\n${status.release_url || ""}`);
                    if (status.release_url) window.open(status.release_url, "_blank", "noopener,noreferrer");
                    return;
                }
                const confirmed = window.confirm(
                    `${status.installed_version ? `当前版本：${status.installed_version}` : "当前未安装 llama-cpp-python"}`
                    + `\n\n将为当前 ComfyUI Python 安装匹配 ${status.backend} 的官方 wheel。完成后需要重启 ComfyUI。确认继续？`,
                );
                if (!confirmed) return;
                installButton.disabled = true;
                installButton.textContent = "安装中…";
                try {
                    const response = await api.fetchApi(INSTALL_ROUTE, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
                    const result = await response.json();
                    if (!response.ok || !result?.success) throw new Error(result?.message || `HTTP ${response.status}`);
                    showMessage(`${result.message}\n\n已安装：${result.wheel}`, true);
                } catch (error) {
                    showMessage(`安装失败：\n${error?.message || error}\n\n手动安装：${status.release_url || ""}`);
                } finally {
                    installButton.disabled = false;
                    installButton.textContent = "确认安装";
                    setStatus(await fetchStatus(true));
                }
            });
            manualButton.addEventListener("click", async () => {
                const status = await fetchStatus(true);
                if (status?.release_url) window.open(status.release_url, "_blank", "noopener,noreferrer");
            });

            const imageArea = element("div", `display:none;flex-direction:column;gap:6px;padding:7px 8px;background:${COLORS.surface};border:1px solid ${COLORS.border};border-radius:5px;`);
            const imageHeading = element("div", `font-size:10px;color:${COLORS.muted};`, "参考图像");
            const chips = element("div", "display:flex;flex-wrap:wrap;gap:6px;");
            imageArea.append(imageHeading, chips);
            root.appendChild(imageArea);

            const render = () => {
                const inputs = imageInputs(node);
                const connected = inputs.filter((input) => input.link != null);
                imageArea.style.display = connected.length ? "flex" : "none";
                chips.replaceChildren();
                for (const [index, input] of connected.entries()) {
                    const chip = element("div", `width:46px;height:46px;flex:0 0 46px;display:flex;align-items:center;justify-content:center;overflow:hidden;border:1px solid ${COLORS.good};border-radius:4px;background:${COLORS.panel};color:${COLORS.good};font-size:10px;`);
                    chip.title = `图像 ${index + 1} 已连接`;
                    const src = upstreamPreview(input);
                    if (src) {
                        const image = document.createElement("img");
                        image.src = src;
                        image.alt = "";
                        image.style.cssText = "width:100%;height:100%;object-fit:cover;";
                        chip.appendChild(image);
                    } else chip.textContent = `图像 ${index + 1}`;
                    chips.appendChild(chip);
                }
                const mode = modeFor(node, prompt);
                modeBar.style.display = mode ? "flex" : "none";
                if (mode) {
                    badge.textContent = MODE_LABELS[mode];
                    badge.style.color = mode === "reverse" ? "#e2c28b" : "#b8c8cc";
                    badge.style.background = mode === "reverse" ? "#3b3326" : "#263741";
                }
            };

            const domWidget = node.addDOMWidget("naiba_qwen_prompt_status", "NAIBA_QWEN_PROMPT_STATUS", root, {
                getValue() { return ""; }, setValue() {}, getMinHeight() { return Math.max(78, root.scrollHeight || 0); },
            });
            domWidget.computeSize = (width) => [width, Math.max(78, root.scrollHeight || 0)];
            const domElement = domWidget.element || root;
            domElement.style.height = "auto";
            domElement.style.minHeight = "max-content";

            if (prompt?.inputEl) {
                prompt.inputEl.style.removeProperty("min-height");
                prompt.inputEl.style.removeProperty("max-height");
                prompt.inputEl.style.removeProperty("resize");
                prompt.inputEl.style.removeProperty("box-sizing");
                prompt.inputEl.style.removeProperty("width");
                prompt.inputEl.placeholder = "描述要生成或修改的画面；连接图像并留空可反推提示词。";
            }

            const seedButton = node.addWidget("button", "随机种子", null, () => {
                const seed = widget(SEED_NAMES);
                if (seed) seed.value = randomSeed();
                node.graph?.change();
                node.setDirtyCanvas?.(true, true);
            });
            seedButton.serialize = false;
            seedButton.options = { ...(seedButton.options || {}), serialize: false };

            const resizeNode = () => {
                const size = node.computeSize?.();
                if (size?.[1] && Math.abs((node.size?.[1] || 0) - size[1]) > 4) node.setSize?.([node.size?.[0] || 360, size[1]]);
                node.setDirtyCanvas?.(true, true);
            };
            let resizeObserver = null;
            let resizeFrame = null;
            if (typeof ResizeObserver !== "undefined") {
                resizeObserver = new ResizeObserver(() => {
                    if (resizeFrame != null) cancelAnimationFrame(resizeFrame);
                    resizeFrame = requestAnimationFrame(() => { resizeFrame = null; resizeNode(); });
                });
                resizeObserver.observe(root);
            }
            let refreshFrame = null;
            const refresh = () => {
                if (refreshFrame != null) cancelAnimationFrame(refreshFrame);
                refreshFrame = requestAnimationFrame(() => { refreshFrame = null; render(); resizeNode(); });
            };
            node._naibaQwenRefresh = refresh;
            node._naibaQwenDispose = () => {
                statusListeners.delete(setStatus);
                resizeObserver?.disconnect();
                if (resizeFrame != null) cancelAnimationFrame(resizeFrame);
                if (refreshFrame != null) cancelAnimationFrame(refreshFrame);
            };
            requestAnimationFrame(() => {
                render();
                resizeNode();
                if (language?.inputEl) language.inputEl.title = "提示词输出语言";
            });
        };

        const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            originalConnectionsChange?.apply(this, arguments);
            this._naibaQwenRefresh?.();
        };
        const originalConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            originalConfigure?.apply(this, arguments);
            this._naibaQwenRefresh?.();
        };
        const originalRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            this._naibaQwenDispose?.();
            return originalRemoved?.apply(this, arguments);
        };
    },
});
