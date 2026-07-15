/**
 * Multi LoRA Loader (only model) - 前端UI扩展
 * 仅加载模型，不处理CLIP
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
let _loraFloatPreview = null;
function getPreviewEl() {
    if (!_loraFloatPreview) {
        const wrap = document.createElement("div");
        wrap.style.cssText = `
            position:fixed;z-index:10002;pointer-events:none;display:none;
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
        img.onerror = () => { img.style.display = "none"; ph.style.display = "block"; };
        img.onload = () => { img.style.display = "block"; ph.style.display = "none"; };
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
}

function placeLoraFloatPreview(e) {
    const wrap = _loraFloatPreview;
    if (!wrap || wrap.style.display === "none") return;
    const rect = wrap.getBoundingClientRect();
    const x = Math.min(e.clientX + 16, window.innerWidth - rect.width - 8);
    const y = Math.min(e.clientY + 16, window.innerHeight - rect.height - 8);
    wrap.style.left = x + "px";
    wrap.style.top = y + "px";
}

function hideLoraFloatPreview() {
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

function createFilterableSelect(options, selected, onChange, node) {
    const container = document.createElement("div");
    container.style.cssText = `
        flex:1;position:relative;min-width:0;
    `;
    
    // 文本输入框用于过滤
    const filterInput = document.createElement("input");
    filterInput.type = "text";
    filterInput.placeholder = "-- Select or filter LoRA --";
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
    
    // 更新显示文本
    const updateDisplay = () => {
        if (currentValue) {
            filterInput.value = currentValue;
            filterInput.style.color = C.text;
        } else {
            filterInput.value = "";
            filterInput.style.color = C.textDim;
        }
    };
    
    // 过滤并显示选项
    const filterOptions = (filterText) => {
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
        
        // 添加过滤后的选项
        const filteredOptions = options.filter(opt => 
            opt.toLowerCase().includes(lowerFilter)
        );
        
        for (const opt of filteredOptions) {
            const optEl = document.createElement("div");
            optEl.textContent = opt;
            optEl.style.cssText = `
                padding:6px 8px;cursor:pointer;font-size:12px;
                color:${C.text};transition:background 0.1s;
                ${opt === currentValue ? `background:rgba(108,92,231,0.2);` : ""}
            `;
            optEl.addEventListener("mouseenter", (e) => { 
                if (opt !== currentValue) optEl.style.background = "rgba(108,92,231,0.15)";
                if (opt && node._previewEnabled) {
                    showLoraFloatPreview(opt);
                    placeLoraFloatPreview(e);
                }
            });
            optEl.addEventListener("mousemove", (e) => { 
                if (opt) placeLoraFloatPreview(e); 
            });
            optEl.addEventListener("mouseleave", () => { 
                if (opt !== currentValue) optEl.style.background = "transparent";
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
        
        // 如果没有匹配项，显示提示
        if (filteredOptions.length === 0 && filterText) {
            const noMatch = document.createElement("div");
            noMatch.textContent = "No matching LoRA found";
            noMatch.style.cssText = `
                padding:6px 8px;font-size:12px;color:${C.textDim};
                font-style:italic;
            `;
            optionsContainer.appendChild(noMatch);
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
    };
    
    const openDropdown = () => {
        if (isOpen) return;
        isOpen = true;
        filterInput.select(); // 选中文本方便输入
        filterOptions("");
        dropdown.style.display = "flex";
        // 先显示再测量实际高度，使下拉框垂直中心对齐输入框中心
        const rect = filterInput.getBoundingClientRect();
        const width = 380;
        let left = rect.right + 4;
        if (left + width > window.innerWidth - 4) {
            // 右侧空间不足时翻到输入框左侧
            left = Math.max(4, rect.left - width - 4);
        }
        dropdown.style.maxHeight = Math.max(120, window.innerHeight - 10) + "px";
        const h = dropdown.offsetHeight;
        let top = rect.top + rect.height / 2 - h / 2;
        top = Math.max(4, Math.min(top, window.innerHeight - h - 4));
        dropdown.style.left = left + "px";
        dropdown.style.top = top + "px";
        dropdown.style.width = width + "px";
    };
    
    const closeDropdown = () => {
        if (!isOpen) return;
        isOpen = false;
        dropdown.style.display = "none";
        hideLoraFloatPreview(); // 避免浮层残留
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
    name: "naiba.MultiLoraLoaderOnlyModel",

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "MultiLoraLoaderOnlyModel") return;

        // 获取Lora文件列表
        let loraList = [];
        try {
            const resp = await api.fetchApi("/object_info/LoraLoader");
            const info = await resp.json();
            if (info.LoraLoader?.input?.required?.lora_name) {
                loraList = info.LoraLoader.input.required.lora_name[0] || [];
            }
        } catch (e) {
            console.warn("[MultiLoraLoaderOnlyModel] Cannot fetch Lora list:", e);
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
            }

            // 序列化（仅模型强度，无CLIP强度）
            node._serializeLoraData = function () {
                const data = node._loraEntries.map((e) => ({
                    name: e.name,
                    strength_model: e.strengthModel,
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
            titleEl.textContent = "LoRA Stack (Model Only)";
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

            // ========== 节点尺寸自适应（直接测量面板真实渲染高度） ==========
            const measureAndResize = () => {
                let [w, h] = node.size;

                // 更新panel宽度以适应节点宽度
                const nodePadding = 10;
                const panelWidth = Math.max(200, w - nodePadding * 2);
                panel.style.width = panelWidth + "px";
                panel.style.maxWidth = panelWidth + "px";

                // widget 高度（排除面板自身）
                let widgetHeight = 0;
                if (node.widgets) {
                    for (const widget of node.widgets) {
                        if (widget.name === "lora_panel") continue;
                        widgetHeight += (widget.computeSize ? widget.computeSize(w)[1] : 26) + 4;
                    }
                }

                // 直接测量面板实际渲染高度（含 padding、gap、子元素），
                // 避免逐项硬编码漏算 flex gap 导致节点偏低、Add 按钮溢出
                const panelHeight = panel.offsetHeight;
                const minPanelHeight = 80;
                const actualPanelHeight = Math.max(panelHeight, minPanelHeight);

                const targetHeight = widgetHeight + actualPanelHeight + 10;

                // 始终贴合内容高度（确保 Add 按钮被节点矩形完整包裹）
                node.size = [w, targetHeight];
            };

            node.onResize = function () {
                measureAndResize();
            };

            // ========== 监听面板尺寸变化（条目增删/恢复）驱动节点高度 ==========
            let _resizeRaf = null;
            const _onPanelResize = () => {
                if (_resizeRaf) cancelAnimationFrame(_resizeRaf);
                _resizeRaf = requestAnimationFrame(() => {
                    measureAndResize();
                    node.graph?.setDirtyCanvas(true, true);
                });
            };
            if (typeof ResizeObserver !== "undefined") {
                const _ro = new ResizeObserver(_onPanelResize);
                _ro.observe(panel);
                node._loraPanelRO = _ro;
            }

            // ========== 创建Lora条目（仅模型强度） ==========
            node._createLoraEntryDOM = function (data) {
                const d = data || { name: "", strength_model: 1.0, enabled: true };
                const entry = {
                    name: d.name,
                    strengthModel: d.strength_model,
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

                // Single row: select + M + toggle + remove
                const row = document.createElement("div");
                row.style.cssText = "display:flex;align-items:center;gap:4px;width:100%";

                const nameSelect = createFilterableSelect(loraList, d.name, (val) => {
                    entry.name = val;
                    node._serializeLoraData();
                }, node);
                row.appendChild(nameSelect.el);

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

                // 悬浮封面预览（复用单例浮层 /naiba/lora/preview）
                card.addEventListener("mouseenter", (e) => {
                    if (entry.name && node._previewEnabled) {
                        showLoraFloatPreview(entry.name);
                        placeLoraFloatPreview(e);
                    }
                });
                card.addEventListener("mousemove", (e) => { placeLoraFloatPreview(e); });
                card.addEventListener("mouseleave", () => { hideLoraFloatPreview(); });

                entry.dom = card;
                return entry;
            };

            // ========== 触发节点重绘 ==========
            const triggerResize = () => {
                // 使用setTimeout确保DOM已经更新
                setTimeout(() => {
                    node.onResize?.();
                    node.graph?.setDirtyCanvas(true, true);
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
                getHeight() { return panel.offsetHeight; },
            });
            // 让 ComfyUI 以面板真实渲染高度作为该 DOM 控件高度，
            // 使节点矩形自动包住工具栏+条目+Add按钮（修复按钮溢出节点外）
            loraPanelWidget.computeSize = (w) => [w, panel.offsetHeight];

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
