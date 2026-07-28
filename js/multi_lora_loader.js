/**
 * Multi LoRA Loader - 前端UI扩展
 * 使用ComfyUI标准ES module导入
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { createPresetsModal } from "./naiba_preset_utils.js";

// ========== 颜色常量 ==========
const C = {
    card: "#16213e",
    cardBorder: "#2a3a5c",
    accent: "#6c5ce7",
    danger: "#ff6b6b",
    text: "#e0e0e0",
    textDim: "#888",
    inputBg: "#0f1729",
    inputBorder: "#2a3a5c",
    btnBorder: "#2a3a5c",
};

// ========== 模块级单例浮动预览（卡片与下拉选项共用） ==========
// 仅创建一次 DOM 浮层，悬停切换时只改 img.src（浏览器按 URL 缓存），避免重复建DOM与多浮层叠加
let _loraFloatPreview = null;
let _lastPreviewEvent = { clientX: 0, clientY: 0 };
function getPreviewEl() {
    if (!_loraFloatPreview) {
        const wrap = document.createElement("div");
        wrap.style.cssText = `
            position:fixed;z-index:10004;pointer-events:none;display:none;
            width:160px;border-radius:6px;overflow:hidden;
            background:rgba(15,23,41,0.95);border:1px solid ${C.accent};
            box-shadow:0 6px 24px rgba(0,0,0,0.6);
        `;
        const img = document.createElement("img");
        img.style.cssText = "width:100%;display:block;";
        const ph = document.createElement("div");
        ph.textContent = "无预览图";
        ph.style.cssText = `display:none;padding:12px;color:${C.textDim};font-size:11px;text-align:center;`;
        wrap.appendChild(img);
        wrap.appendChild(ph);
        img.onerror = () => { img.style.display = "none"; ph.style.display = "block"; placeLoraFloatPreview(_lastPreviewEvent); };
        img.onload = () => {
            img.style.display = "block"; ph.style.display = "none";
            // 图片加载完成后高度才确定，需用最后鼠标位置重新定位，避免被顶到屏幕外
            placeLoraFloatPreview(_lastPreviewEvent);
        };
        wrap._img = img;
        document.body.appendChild(wrap);
        _loraFloatPreview = wrap;
    }
    return _loraFloatPreview;
}

function showLoraFloatPreview(name) {
    if (!name) return;
    const wrap = getPreviewEl();
    if (wrap._name !== name) {
        wrap._name = name;
        wrap._img.src = `/naiba/lora/preview?name=${encodeURIComponent(name)}`;
    }
    wrap.style.display = "block";
    // 若图片已在缓存中立即定位，避免等下一帧才出现/错位
    if (wrap._img.complete) placeLoraFloatPreview(_lastPreviewEvent);
}

function placeLoraFloatPreview(e) {
    const wrap = _loraFloatPreview;
    if (!wrap || wrap.style.display === "none") return;
    if (e) _lastPreviewEvent = { clientX: e.clientX, clientY: e.clientY };
    const px = _lastPreviewEvent.clientX;
    const py = _lastPreviewEvent.clientY;
    const rect = wrap.getBoundingClientRect();
    const w = rect.width || 160;
    const h = rect.height || 0;
    // 水平：优先右侧，空间不足翻左侧
    let x = px + 16;
    if (x + w > window.innerWidth - 8) x = px - w - 16;
    x = Math.max(4, Math.min(x, window.innerWidth - w - 8));
    // 垂直：优先下方，空间不足翻上方，再不足夹到顶部（避免被顶到屏幕最下方被裁切）
    let y = py + 16;
    if (y + h > window.innerHeight - 8) y = py - h - 16;
    if (y < 4) y = 4;
    if (y + h > window.innerHeight - 8) y = Math.max(4, window.innerHeight - h - 8);
    wrap.style.left = x + "px";
    wrap.style.top = y + "px";
}

// 用 requestAnimationFrame 节流高频 mousemove 定位，避免频繁强制重排导致卡顿
let _placeRaf = null;
function requestPlacePreview() {
    if (_placeRaf) return;
    _placeRaf = requestAnimationFrame(() => {
        _placeRaf = null;
        placeLoraFloatPreview(_lastPreviewEvent);
    });
}
function movePreview(e) {
    if (e) _lastPreviewEvent = { clientX: e.clientX, clientY: e.clientY };
    requestPlacePreview();
}

// 悬停延迟计时器：悬停一小段时间后才显示预览，避免快速划过时闪现
let _previewShowTimer = null;

function cancelScheduledPreview() {
    if (_previewShowTimer) {
        clearTimeout(_previewShowTimer);
        _previewShowTimer = null;
    }
}

function scheduleLoraFloatPreview(name, e, delay = 320) {
    if (!name) return;
    cancelScheduledPreview();
    // 记录触发时的坐标（mousemove 期间会被持续刷新为最新位置）
    _lastPreviewEvent = { clientX: e.clientX, clientY: e.clientY };
    _previewShowTimer = setTimeout(() => {
        _previewShowTimer = null;
        showLoraFloatPreview(name);
        // 用最新坐标（非进入时的旧 cx/cy），避免延迟期间移动后初次显示错位
        placeLoraFloatPreview(_lastPreviewEvent);
    }, delay);
}

function hideLoraFloatPreview() {
    cancelScheduledPreview();
    const wrap = _loraFloatPreview;
    if (wrap) {
        wrap.style.display = "none";
        wrap._name = null;
    }
}

// ========== 工具函数 ==========

function createToggle(initial, onChange) {
    const el = document.createElement("div");
    el.style.cssText = `
        position:relative;width:36px;height:20px;border-radius:10px;
        cursor:pointer;transition:background 0.2s;flex-shrink:0;
        background:${initial ? C.accent : "#3a3a5a"};
    `;
    const knob = document.createElement("div");
    knob.style.cssText = `
        position:absolute;top:2px;left:${initial ? "18" : "2"}px;
        width:16px;height:16px;background:#fff;border-radius:50%;
        transition:left 0.2s;pointer-events:none;
    `;
    el.appendChild(knob);

    let val = initial;
    const update = () => {
        el.style.background = val ? C.accent : "#3a3a5a";
        knob.style.left = val ? "18px" : "2px";
    };

    el.addEventListener("click", () => { val = !val; update(); onChange(val); });

    return { el, getValue: () => val, setValue: (v) => { val = v; update(); } };
}

function createNumberInput(value, min, max, step, onChange) {
    const wrap = document.createElement("div");
    wrap.style.cssText = `
        display:flex;align-items:center;background:${C.inputBg};
        border:1px solid ${C.inputBorder};border-radius:4px;overflow:hidden;
        width:52px;flex-shrink:0;
    `;
    const input = document.createElement("input");
    input.type = "number";
    input.value = value;
    input.min = min;
    input.max = max;
    input.step = step;
    input.style.cssText = `
        width:100%;background:transparent;border:none;color:${C.text};
        padding:3px 2px;font-size:12px;text-align:center;outline:none;
        -moz-appearance:textfield;
    `;
    // 使用change事件而不是input事件，避免小数点输入时被重置
    input.addEventListener("change", () => {
        let v = parseFloat(input.value);
        if (isNaN(v)) v = 0;
        v = Math.max(min, Math.min(max, v));
        input.value = v;
        onChange(v);
    });
    // 滚轮快速调整权重（阻止画布滚动/缩放）
    input.addEventListener("wheel", (e) => {
        e.preventDefault();
        const dir = e.deltaY < 0 ? 1 : -1;
        let v = parseFloat(input.value);
        if (isNaN(v)) v = 0;
        v = Math.max(min, Math.min(max, v + dir * step));
        v = parseFloat(v.toFixed(4)); // 修正浮点误差
        input.value = v;
        onChange(v);
    }, { passive: false });
    wrap.appendChild(input);
    return { el: wrap, getValue: () => parseFloat(input.value), setValue: (v) => { input.value = v; } };
}

function createRemoveButton(onClick) {
    const btn = document.createElement("div");
    btn.textContent = "\u2715";
    btn.title = "Delete";
    btn.style.cssText = `
        color:${C.danger};cursor:pointer;font-size:14px;
        padding:2px 4px;border-radius:4px;line-height:1;transition:all 0.15s;
    `;
    btn.addEventListener("mouseenter", () => { btn.style.background = "rgba(255,100,100,0.15)"; });
    btn.addEventListener("mouseleave", () => { btn.style.background = "none"; });
    btn.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
    return btn;
}

// ========== Lora 目录树（按文件夹分级显示） ==========
function buildLoraTree(names) {
    const root = { dirs: new Map(), files: [] };
    for (const name of names) {
        if (!name) continue;
        const parts = name.split(/[/\\]/);
        if (parts.length === 1) {
            root.files.push({ name: parts[0], fullPath: name, isDir: false });
        } else {
            let cur = root;
            for (let i = 0; i < parts.length - 1; i++) {
                const seg = parts[i];
                if (!cur.dirs.has(seg)) cur.dirs.set(seg, { dirs: new Map(), files: [], name: seg });
                cur = cur.dirs.get(seg);
            }
            cur.files.push({ name: parts[parts.length - 1], fullPath: name, isDir: false });
        }
    }
    const sortNode = (n) => {
        n.files.sort((a, b) => a.name.localeCompare(b.name));
        n.dirs = new Map([...n.dirs.entries()].sort((a, b) => a[0].localeCompare(b[0])));
        for (const d of n.dirs.values()) sortNode(d);
    };
    sortNode(root);
    return root;
}

function countTreeItems(node) {
    let c = node.files.length;
    for (const d of node.dirs.values()) c += countTreeItems(d);
    return c;
}

function createFilterableSelect(options, selected, onChange, node) {
    const container = document.createElement("div");
    container.style.cssText = `
        flex:1;position:relative;min-width:0;
    `;
    
    // 文本输入框用于过滤
    const filterInput = document.createElement("input");
    filterInput.type = "text";
    filterInput.placeholder = "Select or filter LoRA";
    filterInput.style.cssText = `
        width:100%;background:${C.inputBg};border:1px solid ${C.inputBorder};
        border-radius:4px;color:${C.text};padding:5px 6px;font-size:12px;
        min-width:0;outline:none;cursor:pointer;box-sizing:border-box;
    `;
    
    // 下拉列表容器（在触发输入框右侧就地展开）
    const dropdown = document.createElement("div");
    dropdown.style.cssText = `
        position:fixed;z-index:10001;overflow-y:auto;
        background:${C.inputBg};border:1px solid ${C.inputBorder};
        box-shadow:0 8px 30px rgba(0,0,0,0.5);border-radius:6px;
        display:none;flex-direction:column;box-sizing:border-box;padding-top:4px;
    `;

    // 选项容器
    const optionsContainer = document.createElement("div");
    optionsContainer.style.cssText = `
        display:flex;flex-direction:column;
    `;
    dropdown.appendChild(optionsContainer);
    document.body.appendChild(dropdown);

    container.appendChild(filterInput);
    
    let currentValue = selected || "";
    let isOpen = false;
    const loraTree = buildLoraTree(options);
    const folderFlyouts = [];
    const FOLDER_INITIAL_HOVER_DELAY = 80;
    const FOLDER_SWITCH_HOVER_DELAY = 45;
    const FOLDER_CLOSE_DELAY = 120;
    let activeFolderFlyout = null;

    // 快速划过搜索结果时不立即高亮，并按帧合并最终状态，避免多行拖影。
    const HOVER_INTENT_DELAY = 50;
    let activeHoverOption = null;
    let candidateHoverOption = null;
    let pendingHighlightOption = null;
    let hoverIntentTimer = null;
    let hoverRaf = null;
    const commitOptionHighlight = (optionEl) => {
        pendingHighlightOption = optionEl;
        if (hoverRaf !== null) return;
        hoverRaf = requestAnimationFrame(() => {
            hoverRaf = null;
            if (activeHoverOption && activeHoverOption !== pendingHighlightOption) {
                activeHoverOption.style.background = "transparent";
            }
            activeHoverOption = pendingHighlightOption;
            if (activeHoverOption) {
                activeHoverOption.style.background = "rgba(108,92,231,0.15)";
            }
        });
    };
    const requestOptionHighlight = (optionEl) => {
        candidateHoverOption = optionEl;
        if (hoverIntentTimer !== null) clearTimeout(hoverIntentTimer);
        hoverIntentTimer = setTimeout(() => {
            hoverIntentTimer = null;
            if (candidateHoverOption === optionEl) commitOptionHighlight(optionEl);
        }, HOVER_INTENT_DELAY);
    };
    const clearOptionHighlight = (optionEl = null) => {
        if (!optionEl || candidateHoverOption === optionEl) {
            candidateHoverOption = null;
            if (hoverIntentTimer !== null) clearTimeout(hoverIntentTimer);
            hoverIntentTimer = null;
        }
        if (!optionEl || activeHoverOption === optionEl || pendingHighlightOption === optionEl) {
            commitOptionHighlight(null);
        }
    };
    const resetOptionHighlight = () => {
        if (hoverIntentTimer !== null) clearTimeout(hoverIntentTimer);
        hoverIntentTimer = null;
        if (hoverRaf !== null) cancelAnimationFrame(hoverRaf);
        hoverRaf = null;
        if (activeHoverOption) activeHoverOption.style.background = "transparent";
        activeHoverOption = null;
        candidateHoverOption = null;
        pendingHighlightOption = null;
    };

    // 创建单个文件选项（可嵌套缩进）
    function makeFileOption(fullPath, depth) {
        const optEl = document.createElement("div");
        const fname = fullPath.split(/[/\\]/).pop();
        optEl.textContent = fname;
        const indent = 8 + depth * 14;
        optEl.title = fullPath;
        optEl.style.cssText = `padding:6px 8px 6px ${indent}px;cursor:pointer;font-size:12px;color:${C.text};${fullPath === currentValue ? `background:rgba(108,92,231,0.2);` : ""}`;
        optEl.addEventListener("mouseenter", (e) => {
            if (fullPath !== currentValue) requestOptionHighlight(optEl);
            if (fullPath && node._previewEnabled) scheduleLoraFloatPreview(fullPath, e);
        });
        optEl.addEventListener("mousemove", (e) => { if (fullPath) movePreview(e); });
        optEl.addEventListener("mouseleave", () => {
            if (fullPath !== currentValue) clearOptionHighlight(optEl);
            cancelScheduledPreview();
            hideLoraFloatPreview();
        });
        optEl.addEventListener("click", () => {
            currentValue = fullPath;
            updateDisplay();
            onChange(fullPath);
            closeDropdown();
        });
        return optEl;
    }

    // 创建文件夹树节点：左侧目录树（点击 ▸ 展开子目录），悬停时向右飞出该目录的直接 LORA
    function makeFolderGroup(dirNode, depth, isRoot) {
        isRoot = !!isRoot;
        const group = document.createElement("div");
        group.style.cssText = "display:flex;flex-direction:column;";
        const header = document.createElement("div");
        const indent = 8 + depth * 16;
        header.style.cssText = `padding:6px 8px 6px ${indent}px;cursor:pointer;font-size:12px;color:${C.accent};display:flex;align-items:center;gap:4px;background:rgba(108,92,231,0.08);border-radius:4px;`;
        const tri = document.createElement("span");
        tri.textContent = isRoot ? "" : "▸";
        tri.style.cssText = "font-size:10px;transition:transform 0.15s;display:inline-block;width:10px;text-align:center;";
        const label = document.createElement("span");
        label.textContent = isRoot ? "📁 根目录" : (dirNode.name + " /");
        header.appendChild(tri);
        header.appendChild(label);
        const count = document.createElement("span");
        count.textContent = `(${countTreeItems(dirNode)})`;
        count.style.cssText = `color:${C.textDim};font-size:10px;margin-left:auto;`;
        header.appendChild(count);
        group.appendChild(header);

        // 飞出面板：显示本目录的直接 LORA（鼠标移到目录上才展开）
        const flyout = document.createElement("div");
        flyout.style.cssText = `
            position:fixed;z-index:10003;display:none;overflow-y:auto;flex-direction:column;
            background:${C.inputBg};border:1px solid ${C.inputBorder};
            box-shadow:0 8px 30px rgba(0,0,0,0.5);border-radius:6px;
            box-sizing:border-box;padding:4px;min-width:260px;
        `;
        document.body.appendChild(flyout);

        let built = false;
        let expanded = false;
        let openTimer = null;
        let closeTimer = null;
        let flyoutController = null;
        const buildChildren = () => {
            if (built) return;
            built = true;
            for (const f of dirNode.files) flyout.appendChild(makeFileOption(f.fullPath, 0));
        };
        const positionFlyout = () => {
            const rect = header.getBoundingClientRect();
            const w = 300;
            let left = rect.right + 4;
            if (left + w > window.innerWidth - 4) left = Math.max(4, rect.left - w - 4);
            flyout.style.width = w + "px";
            flyout.style.maxHeight = (window.innerHeight - 10) + "px";
            const h = flyout.offsetHeight;
            let top = rect.top + rect.height / 2 - h / 2;
            top = Math.max(4, Math.min(top, window.innerHeight - h - 4));
            flyout.style.left = left + "px";
            flyout.style.top = top + "px";
        };
        const expand = () => {
            if (openTimer) { clearTimeout(openTimer); openTimer = null; }
            if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
            if (activeFolderFlyout && activeFolderFlyout !== flyoutController) {
                activeFolderFlyout.collapse();
            }
            buildChildren();
            if (!expanded) {
                expanded = true;
                flyout.style.display = "flex";
                header.style.background = "rgba(108,92,231,0.2)";
                positionFlyout();
            }
            activeFolderFlyout = flyoutController;
        };
        const collapse = () => {
            if (openTimer) { clearTimeout(openTimer); openTimer = null; }
            if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
            if (expanded) {
                expanded = false;
                flyout.style.display = "none";
                header.style.background = "rgba(108,92,231,0.08)";
            }
            if (activeFolderFlyout === flyoutController) activeFolderFlyout = null;
        };
        const scheduleExpand = () => {
            if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
            if (expanded || openTimer) return;
            const delay = activeFolderFlyout
                ? FOLDER_SWITCH_HOVER_DELAY
                : FOLDER_INITIAL_HOVER_DELAY;
            openTimer = setTimeout(expand, delay);
        };
        const scheduleCollapse = () => {
            if (openTimer) { clearTimeout(openTimer); openTimer = null; }
            if (!expanded) return;
            if (closeTimer) clearTimeout(closeTimer);
            closeTimer = setTimeout(collapse, FOLDER_CLOSE_DELAY);
        };
        header.addEventListener("mouseenter", scheduleExpand);
        header.addEventListener("mouseleave", scheduleCollapse);
        flyout.addEventListener("mouseenter", () => { if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; } });
        flyout.addEventListener("mouseleave", scheduleCollapse);
        flyoutController = {
            collapse,
            destroy: () => {
                collapse();
                if (flyout.parentNode) flyout.parentNode.removeChild(flyout);
            }
        };
        folderFlyouts.push(flyoutController);

        // 左侧目录树：点击 ▸ 展开/收起子目录（根目录不渲染子目录树，子目录单独成行）
        const childrenWrap = document.createElement("div");
        childrenWrap.style.cssText = "display:none;flex-direction:column;";
        let treeBuilt = false;
        let treeExpanded = false;
        const buildTreeChildren = () => {
            if (treeBuilt) return;
            treeBuilt = true;
            for (const d of dirNode.dirs.values()) childrenWrap.appendChild(makeFolderGroup(d, depth + 1, false));
        };
        if (!isRoot) {
            const toggleTree = () => {
                buildTreeChildren();
                if (treeExpanded) {
                    treeExpanded = false;
                    childrenWrap.style.display = "none";
                    tri.style.transform = "rotate(0deg)";
                } else {
                    treeExpanded = true;
                    childrenWrap.style.display = "flex";
                    tri.style.transform = "rotate(90deg)";
                }
            };
            header.addEventListener("click", (e) => { e.stopPropagation(); toggleTree(); });
        }
        group.appendChild(childrenWrap);

        return group;
    }

    const destroyFolderFlyouts = () => {
        for (const flyout of folderFlyouts) flyout.destroy();
        folderFlyouts.length = 0;
        activeFolderFlyout = null;
    };
    
    // 更新显示文本
    const updateDisplay = () => {
        if (currentValue) {
            filterInput.value = currentValue;
            const missing = !options.includes(currentValue);
            filterInput.style.color = missing ? C.danger : C.text;
            filterInput.title = missing ? `本地未匹配: ${currentValue}` : currentValue;
        } else {
            filterInput.value = "";
            filterInput.style.color = C.accent;
            filterInput.title = "";
        }
    };
    
    // 过滤并显示选项
    const filterOptions = (filterText) => {
        resetOptionHighlight();
        destroyFolderFlyouts();
        optionsContainer.innerHTML = "";
        const lowerFilter = filterText.toLowerCase();
        
        // 添加空选项
        const emptyOpt = document.createElement("div");
        emptyOpt.textContent = "-- Select LoRA --";
        emptyOpt.style.cssText = `
            padding:6px 8px;cursor:pointer;font-size:12px;
            color:${C.textDim};transition:background 0.1s;
        `;
        emptyOpt.addEventListener("mouseenter", () => { emptyOpt.style.background = "rgba(108,92,231,0.15)"; });
        emptyOpt.addEventListener("mouseleave", () => { emptyOpt.style.background = "transparent"; });
        emptyOpt.addEventListener("click", () => {
            currentValue = "";
            updateDisplay();
            onChange("");
            closeDropdown();
        });
        optionsContainer.appendChild(emptyOpt);
        
        if (!lowerFilter) {
            // 左侧目录树：根目录行 + 各子目录（点击展开子目录，悬停向右飞出该目录 LORA）
            const rootNode = { name: "根目录", dirs: new Map(), files: loraTree.files };
            optionsContainer.appendChild(makeFolderGroup(rootNode, 0, true));
            for (const d of loraTree.dirs.values()) optionsContainer.appendChild(makeFolderGroup(d, 0, false));
            if (loraTree.files.length === 0 && loraTree.dirs.size === 0) {
                const none = document.createElement("div");
                none.textContent = "No LoRA available";
                none.style.cssText = "padding:6px 8px;font-size:12px;color:${C.textDim};font-style:italic;";
                optionsContainer.appendChild(none);
            }
        } else {
            // 过滤模式：扁平显示匹配项（带完整相对路径，便于区分同名文件）
            const filteredOptions = options.filter(opt =>
                opt.toLowerCase().includes(lowerFilter)
            );
            for (const opt of filteredOptions) {
                const optEl = document.createElement("div");
                optEl.textContent = opt;
                optEl.title = opt;
                optEl.style.cssText = `
                    padding:6px 8px;cursor:pointer;font-size:12px;
                    color:${C.text};
                    ${opt === currentValue ? `background:rgba(108,92,231,0.2);` : ""}
                `;
                optEl.addEventListener("mouseenter", (e) => { 
                    if (opt !== currentValue) requestOptionHighlight(optEl);
                    if (opt && node._previewEnabled) {
                        scheduleLoraFloatPreview(opt, e);
                    }
                });
                optEl.addEventListener("mousemove", (e) => { 
                    if (opt) movePreview(e); 
                });
                optEl.addEventListener("mouseleave", () => { 
                    if (opt !== currentValue) clearOptionHighlight(optEl);
                    hideLoraFloatPreview();
                });
                optEl.addEventListener("click", () => {
                    currentValue = opt;
                    updateDisplay();
                    onChange(opt);
                    closeDropdown();
                });
                optionsContainer.appendChild(optEl);
            }
            if (filteredOptions.length === 0) {
                const noMatch = document.createElement("div");
                noMatch.textContent = "No matching LoRA found";
                noMatch.style.cssText = `
                    padding:6px 8px;font-size:12px;color:${C.textDim};
                    font-style:italic;
                `;
                optionsContainer.appendChild(noMatch);
            }
        }
        
        // 如果有选中项但不在列表中（缺失的LoRA）
        if (currentValue && !options.includes(currentValue)) {
            const missingOpt = document.createElement("div");
            missingOpt.textContent = currentValue + " (missing)";
            missingOpt.style.cssText = `
                padding:6px 8px;cursor:pointer;font-size:12px;
                color:#ff6b6b;transition:background 0.1s;
            `;
            missingOpt.addEventListener("mouseenter", () => { missingOpt.style.background = "rgba(255,100,100,0.15)"; });
            missingOpt.addEventListener("mouseleave", () => { missingOpt.style.background = "transparent"; });
            missingOpt.addEventListener("click", () => {
                // 保持当前值不变
                closeDropdown();
            });
            // 插入到第一个位置（空选项之后）
            if (optionsContainer.children.length > 1) {
                optionsContainer.insertBefore(missingOpt, optionsContainer.children[1]);
            } else {
                optionsContainer.appendChild(missingOpt);
            }
        }

        // 每次过滤后重新按输入框中心垂直居中，使下拉框随匹配数量围绕 LORA 框对称展开/收缩
        if (isOpen) positionDropdown();
    };
    
    // 下拉框定位：垂直居中于输入框中心，水平锚定输入框右侧（空间不足翻左侧）
    // 每次过滤后调用，使下拉框随匹配数量围绕 LORA 框对称展开/收缩
    const positionDropdown = () => {
        if (dropdown.style.display === "none") return;
        const rect = filterInput.getBoundingClientRect();
        const width = 380;
        let left = rect.right + 4;
        if (left + width > window.innerWidth - 4) {
            // 右侧空间不足时翻到输入框左侧
            left = Math.max(4, rect.left - width - 4);
        }
        dropdown.style.width = width + "px";
        dropdown.style.maxHeight = Math.max(120, window.innerHeight - 10) + "px";
        const h = dropdown.offsetHeight;
        let top = rect.top + rect.height / 2 - h / 2;
        top = Math.max(4, Math.min(top, window.innerHeight - h - 4));
        dropdown.style.left = left + "px";
        dropdown.style.top = top + "px";
    };

    const openDropdown = () => {
        if (isOpen) return;
        isOpen = true;
        filterInput.select(); // 选中文本方便输入
        filterOptions("");
        dropdown.style.display = "flex";
        // 显示后再测量高度并定位（垂直居中于输入框）
        positionDropdown();
    };
    
    const closeDropdown = () => {
        if (!isOpen) return;
        isOpen = false;
        resetOptionHighlight();
        dropdown.style.display = "none";
        hideLoraFloatPreview(); // 避免浮层残留
        // 销毁所有飞出子菜单，避免残留
        destroyFolderFlyouts();
        updateDisplay(); // 恢复显示当前值
    };
    
    // 事件监听 - 使用 pointerdown 避免 focus/click 冲突，支持触摸设备
    filterInput.addEventListener("pointerdown", (e) => {
        e.preventDefault(); // 阻止默认的 focus 行为
        if (!isOpen) {
            openDropdown();
            filterInput.focus(); // 手动触发 focus
        } else {
            closeDropdown();
        }
    });
    
    filterInput.addEventListener("input", () => {
        const filterText = filterInput.value;
        filterOptions(filterText);
        if (!isOpen) {
            openDropdown();
        }
    });
    
    filterInput.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeDropdown();
            filterInput.blur();
        } else if (e.key === "Enter") {
            // 如果只有一个匹配项，直接选择
            const filterText = filterInput.value.toLowerCase();
            const filtered = options.filter(opt => opt.toLowerCase().includes(filterText));
            if (filtered.length === 1) {
                currentValue = filtered[0];
                updateDisplay();
                onChange(filtered[0]);
                closeDropdown();
            }
        }
    });
    
    // 点击外部关闭下拉列表（抽屉已挂在 body 上，需排除其自身）
    document.addEventListener("click", (e) => {
        if (!container.contains(e.target) && !dropdown.contains(e.target)) {
            closeDropdown();
        }
    });
    
    // 鼠标滚轮滚动下拉列表
    dropdown.addEventListener("wheel", (e) => {
        // 允许默认滚动行为
    });
    
    updateDisplay();
    
    return { 
        el: container, 
        getValue: () => currentValue, 
        setValue: (v) => { 
            currentValue = v; 
            updateDisplay(); 
        } 
    };
}

// ========== 注册扩展 ==========

app.registerExtension({
    name: "naiba.MultiLoraLoader",

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "MultiLoraLoader") return;

        // 获取Lora文件列表
        let loraList = [];
        try {
            const resp = await api.fetchApi("/object_info/LoraLoader");
            const info = await resp.json();
            if (info.LoraLoader?.input?.required?.lora_name) {
                loraList = info.LoraLoader.input.required.lora_name[0] || [];
            }
        } catch (e) {
            console.warn("[MultiLoraLoader] Cannot fetch Lora list:", e);
        }

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            const node = this;
            node._loraEntries = [];
            node._loraUIInitialized = false;
            node._previewEnabled = true; // 悬停封面预览开关（默认开启）

            // 查找 lora_data 控件
            const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
            
            // 如果找到了，确保隐藏它
            if (loraDataWidget) {
                loraDataWidget.hidden = true;
                if (loraDataWidget.inputEl) loraDataWidget.inputEl.style.display = "none";
                if (loraDataWidget.element) loraDataWidget.element.style.display = "none";
                // 显式让 ComfyUI 布局忽略该隐藏多行文本控件的高度，避免其把节点矩形撑高/压低
                loraDataWidget.computeSize = () => [0, 0];
            }

            // 序列化
            node._serializeLoraData = function () {
                const data = node._loraEntries.map((e) => ({
                    ...e.source,
                    name: e.name,
                    strength_model: e.strengthModel,
                    strength_clip: e.strengthClip,
                    enabled: e.enabled,
                }));
                if (loraDataWidget) loraDataWidget.value = JSON.stringify(data);
            };

            // 反序列化
            node._deserializeLoraData = function () {
                if (!loraDataWidget) return [];
                try { return JSON.parse(loraDataWidget.value || "[]"); }
                catch { return []; }
            };

            // ========== DOM面板 ==========
            const panel = document.createElement("div");
            panel.style.cssText = "display:flex;flex-direction:column;gap:6px;padding:8px 6px;width:100%;box-sizing:border-box";

            // 工具栏
            const toolbar = document.createElement("div");
            toolbar.style.cssText = "display:flex;align-items:center;justify-content:space-between;padding:0 2px;width:100%;box-sizing:border-box";

            const leftGroup = document.createElement("div");
            leftGroup.style.cssText = "display:flex;align-items:center;gap:8px";

            const titleEl = document.createElement("span");
            titleEl.textContent = "LoRA Stack";
            titleEl.style.cssText = `color:${C.text};font-size:13px;font-weight:600`;
            leftGroup.appendChild(titleEl);

            const badge = document.createElement("span");
            badge.style.cssText = `
                background:${C.accent};color:#fff;font-size:10px;
                padding:1px 6px;border-radius:8px;font-weight:600;
                min-width:18px;text-align:center;display:none;
            `;
            badge.textContent = "0";
            leftGroup.appendChild(badge);

            const updateBadge = () => {
                badge.textContent = String(node._loraEntries.length);
                badge.style.display = node._loraEntries.length > 0 ? "" : "none";
            };

            toolbar.appendChild(leftGroup);

            const rightGroup = document.createElement("div");
            rightGroup.style.cssText = "display:flex;align-items:center;gap:8px";

            const toggleAllLabel = document.createElement("span");
            toggleAllLabel.textContent = "All";
            toggleAllLabel.style.cssText = `color:${C.textDim};font-size:11px`;
            rightGroup.appendChild(toggleAllLabel);

            const toggleAll = createToggle(true, (val) => {
                for (const e of node._loraEntries) {
                    e.enabled = val;
                    e.enabledToggle.setValue(val);
                    e._updateDim();
                }
                node._serializeLoraData();
            });
            rightGroup.appendChild(toggleAll.el);

            const clearBtn = document.createElement("span");
            clearBtn.textContent = "Clear";
            clearBtn.title = "Clear all LoRAs";
            clearBtn.style.cssText = `
                color:${C.danger};font-size:10px;cursor:pointer;
                padding:2px 6px;border-radius:4px;transition:all 0.15s;
            `;
            clearBtn.addEventListener("mouseenter", () => { clearBtn.style.background = "rgba(255,100,100,0.15)"; });
            clearBtn.addEventListener("mouseleave", () => { clearBtn.style.background = "none"; });
            clearBtn.addEventListener("click", () => {
                if (node._loraEntries.length === 0) return;
                if (!confirm(`Clear all ${node._loraEntries.length} LoRAs?`)) return;
                node._clearAllEntries();
                updateBadge();
            });
            rightGroup.appendChild(clearBtn);

            // 悬停封面预览开关
            const previewLabel = document.createElement("span");
            previewLabel.textContent = "预览";
            previewLabel.title = "悬停显示LoRA封面预览";
            previewLabel.style.cssText = `color:${C.textDim};font-size:11px`;
            rightGroup.appendChild(previewLabel);

            const previewToggle = createToggle(true, (val) => {
                node._previewEnabled = val;
                if (!val) hideLoraFloatPreview(); // 关闭时立即收起可能残留的浮层
            });
            rightGroup.appendChild(previewToggle.el);

            // 预设按钮
            const presetBtn = document.createElement("span");
            presetBtn.textContent = "预设";
            presetBtn.title = "预设管理";
            presetBtn.style.cssText = `
                color:${C.accent};font-size:10px;cursor:pointer;
                padding:2px 6px;border-radius:4px;transition:all 0.15s;
                margin-left:4px;
            `;
            presetBtn.addEventListener("mouseenter", () => { presetBtn.style.background = "rgba(108,92,231,0.15)"; });
            presetBtn.addEventListener("mouseleave", () => { presetBtn.style.background = "none"; });
            presetBtn.addEventListener("click", () => {
                createPresetsModal(node);
            });
            rightGroup.appendChild(presetBtn);

            toolbar.appendChild(rightGroup);
            panel.appendChild(toolbar);

            // 条目容器
            const entriesContainer = document.createElement("div");
            entriesContainer.style.cssText = "display:flex;flex-direction:column;gap:2px;width:100%;box-sizing:border-box";
            panel.appendChild(entriesContainer);

            // 添加按钮
            const addButton = document.createElement("div");
            addButton.textContent = "+ Add LoRA";
            addButton.style.cssText = `
                display:flex;align-items:center;justify-content:center;
                box-sizing:border-box;width:100%;padding:8px 0;background:transparent;
                border:1px dashed ${C.btnBorder};border-radius:6px;
                color:${C.textDim};font-size:12px;cursor:pointer;transition:all 0.2s;
            `;
            addButton.addEventListener("mouseenter", () => {
                addButton.style.borderColor = C.accent;
                addButton.style.color = C.accent;
                addButton.style.background = "rgba(108,92,231,0.08)";
            });
            addButton.addEventListener("mouseleave", () => {
                addButton.style.borderColor = C.btnBorder;
                addButton.style.color = C.textDim;
                addButton.style.background = "transparent";
            });
            panel.appendChild(addButton);

            // ========== 节点尺寸自适应（覆写 computeSize / setSize，参照成熟模式） ==========
            // 关键修复：本版本 ComfyUI 的 node.computeSize() 不会可靠地把 DOM 面板控件高度
            // 计入节点总高，导致节点被钉在过矮的高度、面板（含 + Add LoRA）溢出节点矩形。
            // 因此显式覆写 node.computeSize / node.setSize，以「面板 offsetTop + 面板真实高度」
            // 作为节点总高，不再依赖 node.size[1] 直写。
            const paddingBottom = 14;
            let panelHeight = 100;

            // 面板在节点 DOM 容器内的起始 y（DOM widget 元素相对节点容器的偏移）
            const getPanelTop = () => {
                if (panel && typeof panel.offsetTop === "number" && panel.offsetTop > 0) {
                    return panel.offsetTop;
                }
                return 40; // 兜底：控件区大致高度
            };

            // 计算目标节点高度 = 面板起始 y + 面板真实内容高度 + 底部留白
            const computeTargetHeight = () => {
                // 面板真实高度可读时才刷新缓存；否则沿用上一次有效高度，绝不写 0
                if (panel && panel.offsetHeight > 0) {
                    panelHeight = panel.offsetHeight;
                }
                return getPanelTop() + panelHeight + paddingBottom;
            };

            // 按当前节点宽度同步面板宽度（与控件区保持一致，避免条目横向溢出）
            const syncPanelWidth = () => {
                const nodePadding = 10;
                const panelWidth = Math.max(200, node.size[0] - nodePadding * 2);
                panel.style.width = panelWidth + "px";
                panel.style.maxWidth = panelWidth + "px";
            };

            // 覆写 computeSize：让 ComfyUI 内部布局以面板真实高度作为节点高度
            const origComputeSize = node.computeSize;
            node.computeSize = function () {
                const res = origComputeSize ? origComputeSize.apply(this, arguments) : [node.size[0] || 280, 200];
                const h = computeTargetHeight();
                res[0] = node.minWidth || 280;
                res[1] = Math.max(res[1], h);
                return res;
            };

            // 覆写 setSize：强制最小高度（内容高度），并把面板宽度同步到节点内容区；
            // 用户仍可拖大节点，只是不会被压到比内容更矮。
            const origSetSize = node.setSize;
            node.setSize = function (size) {
                const h = computeTargetHeight();
                size[1] = Math.max(size[1], h);
                if (origSetSize) origSetSize.call(this, size);
                else this.size = size;
                syncPanelWidth();
            };

            // 触发节点按内容重算高度
            const scheduleResize = () => {
                syncPanelWidth();
                const h = computeTargetHeight();
                if (node.size[1] !== h) {
                    node.setSize([node.size[0], h]);
                } else {
                    node.graph?.setDirtyCanvas(true, true);
                }
            };

            node.onResize = function () {
                syncPanelWidth();
            };

            // 监听面板尺寸变化（条目增删/恢复）驱动节点高度，从根上消除按钮溢出回归
            let _resizeRaf = null;
            const _onPanelResize = () => {
                if (_resizeRaf) cancelAnimationFrame(_resizeRaf);
                _resizeRaf = requestAnimationFrame(() => {
                    scheduleResize();
                });
            };
            if (typeof ResizeObserver !== "undefined") {
                const _ro = new ResizeObserver(_onPanelResize);
                _ro.observe(panel);
                node._loraPanelRO = _ro;
            }

            // ========== 创建Lora条目 ==========
            node._createLoraEntryDOM = function (data) {
                const d = data || { name: "", strength_model: 1.0, strength_clip: 1.0, enabled: true };
                const entry = {
                    source: { ...d },
                    name: d.name,
                    strengthModel: d.strength_model,
                    strengthClip: d.strength_clip,
                    enabled: d.enabled,
                    dom: null,
                    enabledToggle: null,
                };

                const card = document.createElement("div");
                const initialBg = d.enabled ? C.card : "rgba(22, 33, 62, 0.45)";
                const initialBorder = d.enabled ? C.cardBorder : "rgba(42, 58, 92, 0.45)";
                card.style.cssText = `
                    background:${initialBg};border:1px solid ${initialBorder};
                    border-radius:6px;padding:8px 10px;
                    transition:background 0.2s, border-color 0.2s;
                    width:100%;box-sizing:border-box;
                `;

                // Single row: select + M + C + toggle + remove
                const row = document.createElement("div");
                row.style.cssText = "display:flex;align-items:center;gap:4px;width:100%";

                const nameSelect = createFilterableSelect(loraList, d.name, (val) => {
                    entry.name = val;
                    node._serializeLoraData();
                }, node);
                row.appendChild(nameSelect.el);

                // 悬停封面预览：仅当鼠标停留在 LoRA 名选择框上时才显示（调权重/开关不触发），
                // 并加入 ~320ms 悬停延迟，避免快速划过节点时闪现预览
                nameSelect.el.addEventListener("mouseenter", (e) => {
                    if (entry.name && node._previewEnabled) {
                        scheduleLoraFloatPreview(entry.name, e);
                    }
                });
                nameSelect.el.addEventListener("mousemove", (e) => { movePreview(e); });
                nameSelect.el.addEventListener("mouseleave", () => { hideLoraFloatPreview(); });

                const mkLabel = (t) => {
                    const s = document.createElement("span");
                    s.textContent = t;
                    s.style.cssText = `color:${C.textDim};font-size:10px;min-width:10px;font-weight:600`;
                    return s;
                };

                row.appendChild(mkLabel("M"));
                const mw = createNumberInput(d.strength_model, -100, 100, 0.01, (v) => {
                    entry.strengthModel = v;
                    node._serializeLoraData();
                });
                row.appendChild(mw.el);

                row.appendChild(mkLabel("C"));
                const cw = createNumberInput(d.strength_clip, -100, 100, 0.01, (v) => {
                    entry.strengthClip = v;
                    node._serializeLoraData();
                });
                row.appendChild(cw.el);

                const et = createToggle(d.enabled, (v) => {
                    entry.enabled = v;
                    entry._updateDim();
                    node._serializeLoraData();
                });
                entry.enabledToggle = et;
                row.appendChild(et.el);

                row.appendChild(createRemoveButton(() => { node._removeLoraEntry(entry); }));
                card.appendChild(row);

                entry._updateDim = () => {
                    if (entry.enabled) {
                        card.style.background = C.card;
                        card.style.borderColor = C.cardBorder;
                        card.style.opacity = "1";
                    } else {
                        // 使用半透明背景和边框，保持内容不透明
                        card.style.background = "rgba(22, 33, 62, 0.45)";
                        card.style.borderColor = "rgba(42, 58, 92, 0.45)";
                        card.style.opacity = "1";
                    }
                };

                // 悬浮封面预览仅绑定在 LoRA 名选择框上（见上），此处不再对整卡触发，
                // 避免鼠标在权重输入框/开关区域移动时也弹出预览

                entry.dom = card;
                return entry;
            };

            // ========== 触发节点重绘 ==========
            const triggerResize = () => {
                // 使用 setTimeout 确保 DOM 已更新后再按内容重算节点高度
                setTimeout(() => {
                    scheduleResize();
                }, 50);
            };

            // ========== 条目管理 ==========
            node._addLoraEntry = function (data) {
                const entry = node._createLoraEntryDOM(data);
                node._loraEntries.push(entry);
                entriesContainer.appendChild(entry.dom);
                node._serializeLoraData();
                updateBadge();
                triggerResize();
            };

            node._removeLoraEntry = function (entry) {
                const idx = node._loraEntries.indexOf(entry);
                if (idx === -1) return;
                node._loraEntries.splice(idx, 1);
                if (entry.dom && entry.dom.parentNode) entry.dom.parentNode.removeChild(entry.dom);
                node._serializeLoraData();
                updateBadge();
                triggerResize();
            };

            node._clearAllEntries = function () {
                for (const e of node._loraEntries) {
                    if (e.dom && e.dom.parentNode) e.dom.parentNode.removeChild(e.dom);
                }
                node._loraEntries = [];
                node._serializeLoraData();
                updateBadge();
                triggerResize();
            };

            // 添加按钮事件
            addButton.addEventListener("click", () => {
                node._addLoraEntry();
            });

            // ========== 注册DOM控件 ==========
            const loraPanelWidget = node.addDOMWidget("lora_panel", "LORA_PANEL", panel, {
                getValue() { return ""; },
                setValue() {},
                getHeight() { return panelHeight; },
            });
            // 以缓存面板高度作为该 DOM 控件高度（非实时 offsetHeight），
            // 使 ComfyUI 内部 computeSize 永不读到 0，节点矩形稳定包住工具栏+条目+Add按钮
            loraPanelWidget.computeSize = (w) => [w, panelHeight];

            // 修复：ComfyUI 前端会给 DOM 面板自动加 h-full，而其父容器初始高度为 0，
            // 导致 panel.offsetHeight 只能测到极小值、节点高度计算错误。
            // 移除 h-full 并改为按内容自适应，节点边框随条目数量自动增减。
            panel.classList.remove("h-full");
            panel.style.height = "auto";
            panel.style.minHeight = "max-content";

            node.minWidth = 280;
            node.minHeight = 120;

            // ========== 初始化恢复数据 ==========
            setTimeout(() => {
                if (node._loraUIInitialized) return;
                node._loraUIInitialized = true;

                const saved = node._deserializeLoraData();
                if (saved.length > 0) {
                    for (const item of saved) {
                        node._addLoraEntry(item);
                    }
                    toggleAll.setValue(saved.every((d) => d.enabled));
                }
                updateBadge();
                triggerResize();
            }, 150);
        };
    },
});
