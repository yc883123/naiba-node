/**
 * Lora Testing Converter - 前端扩展
 * 为 LoraTestingConverter 节点添加预览和自动切换功能
 */

import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "naiba.LoraTestingConverter",
    async beforeRegisterNodeType(nodeType, nodeData) {
        if (nodeData.name === "LoraTestingConverter") {
            // 保存原始的 onNodeCreated
            const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
            
            nodeType.prototype.onNodeCreated = function() {
                const result = originalOnNodeCreated?.apply(this, arguments);
                const node = this;
                
                // 添加预览区域
                const previewWidget = node.addWidget("text", "preview", "", (v) => {}, {
                    multiline: true,
                    readonly: true
                });
                previewWidget.inputEl.style.cssText = `
                    font-size: 11px;
                    color: #888;
                    background: #1a1a2e;
                    border: none;
                    max-height: 100px;
                    overflow-y: auto;
                `;
                previewWidget.inputEl.placeholder = "转换结果预览（只读）";
                
                // 获取相关 widget
                const sourceWidget = node.widgets.find(w => w.name === "preset_source");
                const presetWidget = node.widgets.find(w => w.name === "preset_name");
                const pathWidget = node.widgets.find(w => w.name === "file_path");
                
                // 根据来源方式显示/隐藏相关 widget
                function updateVisibility() {
                    if (!sourceWidget) return;
                    
                    const isFromDropdown = sourceWidget.value === "从下拉框选择";
                    
                    if (presetWidget) {
                        presetWidget.hidden = !isFromDropdown;
                    }
                    if (pathWidget) {
                        pathWidget.hidden = isFromDropdown;
                    }
                    
                    // 触发节点重新计算大小
                    node.setSize(node.computeSize());
                }
                
                // 监听来源方式变化
                if (sourceWidget) {
                    const originalCallback = sourceWidget.callback;
                    sourceWidget.callback = function(value) {
                        if (originalCallback) {
                            originalCallback.apply(this, arguments);
                        }
                        updateVisibility();
                    };
                    updateVisibility();
                }
                
                // 监听预设选择变化，更新预览
                if (presetWidget) {
                    const originalPresetCallback = presetWidget.callback;
                    presetWidget.callback = function(value) {
                        if (originalPresetCallback) {
                            originalPresetCallback.apply(this, arguments);
                        }
                        updatePreview();
                    };
                }
                
                // 监听路径输入变化
                if (pathWidget) {
                    const originalPathCallback = pathWidget.callback;
                    pathWidget.callback = function(value) {
                        if (originalPathCallback) {
                            originalPathCallback.apply(this, arguments);
                        }
                        updatePreview();
                    };
                }
                
                // 更新预览函数
                function updatePreview() {
                    setTimeout(() => {
                        const outputWidget = node.widgets.find(w => w.name === "lora_data");
                        if (outputWidget && outputWidget.value) {
                            try {
                                const data = JSON.parse(outputWidget.value);
                                if (data.length > 0) {
                                    const preview = data.map((lora, i) => {
                                        const status = lora.enabled ? "✓" : "✗";
                                        return `${i+1}. ${status} ${lora.name} (M:${lora.strength_model} C:${lora.strength_clip})`;
                                    }).join("\n");
                                    previewWidget.value = `共 ${data.length} 个 LoRA:\n${preview}`;
                                } else {
                                    previewWidget.value = "(无数据)";
                                }
                            } catch (e) {
                                previewWidget.value = "(解析中...)";
                            }
                        } else {
                            previewWidget.value = "";
                        }
                    }, 200);
                }
                
                // 初始更新
                updatePreview();
                
                return result;
            };
        }
    }
});
