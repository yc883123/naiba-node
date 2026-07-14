/**
 * Naiba Preset Utils - 共享预设模态框和工具函数
 * 供 Multi LoRA Loader 和 Multi LoRA Loader (only model) 使用
 */

import { api } from "../../scripts/api.js";

// ========== 颜色常量 ==========
const COLORS = {
    modalBg: "#1a1a2e",
    headerBg: "#16213e",
    contentBg: "#0f1729",
    accent: "#6c5ce7",
    accentHover: "#7c6cf7",
    danger: "#ff6b6b",
    dangerHover: "#ff8b8b",
    success: "#2ed573",
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

    // ========== 创建模态框容器 ==========
    const overlay = document.createElement("div");
    overlay.style.cssText = `
        position:fixed;top:0;left:0;width:100%;height:100%;
        background:rgba(0,0,0,0.6);z-index:10000;
        display:flex;align-items:center;justify-content:center;
    `;

    const modal = document.createElement("div");
    modal.style.cssText = `
        width:420px;max-height:70vh;background:${COLORS.modalBg};
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
    title.textContent = "LoRA 预设管理";
    title.style.cssText = `color:${COLORS.text};font-size:14px;font-weight:600;`;

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

    // ========== 内容区域 ==========
    const content = document.createElement("div");
    content.style.cssText = `
        flex:1;padding:12px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;
    `;

    // 预设列表
    const presetList = document.createElement("div");
    presetList.style.cssText = `
        display:flex;flex-direction:column;gap:4px;min-height:100px;max-height:200px;
        overflow-y:auto;border:1px solid ${COLORS.border};border-radius:4px;padding:4px;
        background:${COLORS.inputBg};
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

    const importBtn = createBtn("导入预设", COLORS.accent);
    const saveBtn = createBtn("保存预设", COLORS.success);
    const deleteBtn = createBtn("删除预设", COLORS.danger);
    const renameBtn = createBtn("重命名", COLORS.textDim);
    const exportBtn = createBtn("导出到文件", COLORS.accent);
    const importFileBtn = createBtn("从文件导入", COLORS.accent);

    btnGroup.appendChild(importBtn);
    btnGroup.appendChild(saveBtn);
    btnGroup.appendChild(deleteBtn);
    btnGroup.appendChild(renameBtn);
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

    // ========== 获取当前节点数据 ==========
    function getCurrentData() {
        const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
        if (!loraDataWidget) return [];
        try {
            return JSON.parse(loraDataWidget.value || "[]");
        } catch {
            return [];
        }
    }

    // ========== 设置节点数据 ==========
    function setNodeData(data) {
        const loraDataWidget = node.widgets?.find((w) => w.name === "lora_data");
        if (!loraDataWidget) return;

        // 清空现有条目（Multi LoRA Loader 节点）
        if (node._clearAllEntries) {
            node._clearAllEntries();
        }

        // 设置数据
        loraDataWidget.value = JSON.stringify(data);

        // 重建 UI（Multi LoRA Loader 节点）
        if (node._addLoraEntry && data.length > 0) {
            for (const item of data) {
                node._addLoraEntry(item);
            }
        }
        
        // 更新显示区域（Visual LoRA Loader 节点）
        if (node._updateVisualLoraDisplay) {
            node._updateVisualLoraDisplay();
        }
        
        // 触发节点重绘（Visual LoRA Loader 节点）
        if (node._triggerVisualLoraResize) {
            node._triggerVisualLoraResize();
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

            if (result.presets.length === 0) {
                const emptyMsg = document.createElement("div");
                emptyMsg.textContent = "暂无预设";
                emptyMsg.style.cssText = `color:${COLORS.textDim};text-align:center;padding:20px;font-size:12px;`;
                presetList.appendChild(emptyMsg);
                return;
            }

            for (const name of result.presets) {
                const item = document.createElement("div");
                item.textContent = name;
                item.style.cssText = `
                    padding:8px 10px;border-radius:4px;cursor:pointer;
                    color:${COLORS.text};font-size:12px;transition:all 0.15s;
                    background:${COLORS.listItemBg};
                `;
                item.addEventListener("mouseenter", () => {
                    if (item._selected) return;
                    item.style.background = COLORS.listItemHover;
                });
                item.addEventListener("mouseleave", () => {
                    if (item._selected) return;
                    item.style.background = COLORS.listItemBg;
                });
                item.addEventListener("click", () => {
                    // 取消其他选中
                    for (const pi of presetItems) {
                        pi._selected = false;
                        pi.style.background = COLORS.listItemBg;
                    }
                    // 选中当前
                    item._selected = true;
                    item.style.background = COLORS.listItemActive;
                    selectedPreset = name;
                });

                // 双击重命名
                item.addEventListener("dblclick", () => {
                    startRename(item, name);
                });

                item._selected = false;
                presetItems.push(item);
                presetList.appendChild(item);
            }
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
        `;

        item.textContent = "";
        item.appendChild(input);
        input.focus();
        input.select();

        const finishRename = async () => {
            const newName = input.value.trim();
            if (!newName || newName === oldName) {
                item.textContent = oldName;
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
                    item.textContent = oldName;
                } else {
                    item.textContent = newName;
                    showStatus("重命名成功");
                    if (selectedPreset === oldName) {
                        selectedPreset = newName;
                    }
                }
            } catch (e) {
                showStatus("重命名失败: " + e.message, true);
                item.textContent = oldName;
            }
        };

        input.addEventListener("blur", finishRename);
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") input.blur();
            if (e.key === "Escape") {
                item.textContent = oldName;
            }
        });
    }

    // ========== 按钮事件 ==========

    // 导入预设
    importBtn.addEventListener("click", async () => {
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

            setNodeData(result.data);
            showStatus(`已导入预设: ${selectedPreset}`);
            closeModal();
            // 调用导入回调（如果存在）
            if (typeof onImport === "function") {
                onImport();
            }
        } catch (e) {
            console.error("[Presets] Import error:", e);
            showStatus("导入失败: " + e.message, true);
        }
    });

    // 保存预设
    saveBtn.addEventListener("click", async () => {
        const name = prompt("请输入预设名称:");
        if (!name || !name.trim()) return;

        const data = getCurrentData();
        if (data.length === 0) {
            showStatus("当前没有 LoRA 配置可保存", true);
            return;
        }

        try {
            const resp = await api.fetchApi("/naiba/presets/save", {
                method: "POST",
                body: JSON.stringify({ name: name.trim(), data }),
            });
            const result = await resp.json();

            if (result.error) {
                showStatus(result.error, true);
            } else {
                showStatus("预设保存成功");
                await loadPresetList();
            }
        } catch (e) {
            showStatus("保存失败: " + e.message, true);
        }
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

        const item = presetItems.find((el) => el.textContent === selectedPreset || el._selected);
        if (item) {
            startRename(item, selectedPreset);
        }
    });

    // 导出到本地文件
    exportBtn.addEventListener("click", () => {
        const data = getCurrentData();
        if (data.length === 0) {
            showStatus("当前没有 LoRA 配置可导出", true);
            return;
        }

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `lora_preset_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showStatus("预设已导出到本地文件");
    });

    // 从本地文件导入
    importFileBtn.addEventListener("click", () => {
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

                setNodeData(data);
                showStatus("已从文件导入预设");
                closeModal();
                // 调用导入回调（如果存在）
                if (typeof onImport === "function") {
                    onImport();
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
