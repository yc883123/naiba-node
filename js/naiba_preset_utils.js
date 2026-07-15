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

    // 封面状态提示
    const coverStatus = document.createElement("div");
    coverStatus.style.cssText = `color:${COLORS.textDim};font-size:11px;text-align:center;min-height:14px;`;
    content.appendChild(coverStatus);

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

    const setCoverBtn = createBtn("设置封面", "#ff9f43", "#ffb366");

    const btnGroup2 = document.createElement("div");
    btnGroup2.style.cssText = `display:flex;gap:6px;`;
    btnGroup2.appendChild(exportBtn);
    btnGroup2.appendChild(importFileBtn);
    btnGroup2.appendChild(setCoverBtn);
    content.appendChild(btnGroup2);

    modal.appendChild(content);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // ========== 内部状态 ==========
    let selectedPreset = null;
    let presetItems = [];
    let stagedCoverFile = null; // 待保存时上传的封面文件

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

    // ========== 上传预设封面 ==========
    async function uploadCover(name, file) {
        const fd = new FormData();
        fd.append("name", name);
        fd.append("file", file);
        const resp = await api.fetchApi("/naiba/presets/upload-image", { method: "POST", body: fd });
        return resp.json();
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

            if (result.presets.length === 0) {
                const emptyMsg = document.createElement("div");
                emptyMsg.textContent = "暂无预设";
                emptyMsg.style.cssText = `color:${COLORS.textDim};text-align:center;padding:20px;font-size:12px;grid-column:1/-1;`;
                presetList.appendChild(emptyMsg);
                return;
            }

            for (const name of result.presets) {
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
                    justify-content:center;
                `;
                const coverImg = document.createElement("img");
                coverImg.style.cssText = "width:100%;height:100%;object-fit:contain;display:block;";
                coverImg.src = `/naiba/presets/image?name=${encodeURIComponent(name)}`;
                coverImg.onerror = () => {
                    cover.innerHTML = `<div style="color:${COLORS.textDim};font-size:11px;text-align:center;padding:4px;">无封面</div>`;
                };
                cover.appendChild(coverImg);
                item._coverImg = coverImg;
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
                    if (item._selected) return;
                    item.style.background = COLORS.listItemHover;
                    item.style.borderColor = COLORS.border;
                });
                item.addEventListener("mouseleave", () => {
                    if (item._selected) return;
                    item.style.background = COLORS.listItemBg;
                    item.style.borderColor = "transparent";
                });
                item.addEventListener("click", () => {
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
                });

                // 双击重命名
                item.addEventListener("dblclick", () => {
                    startRename(item, name);
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
                    if (item._coverImg) {
                        item._coverImg.src = `/naiba/presets/image?name=${encodeURIComponent(newName)}&t=${Date.now()}`;
                    }
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

    // 封面文件输入（隐藏）
    const coverFileInput = document.createElement("input");
    coverFileInput.type = "file";
    coverFileInput.accept = "image/*";
    coverFileInput.style.display = "none";
    content.appendChild(coverFileInput);

    setCoverBtn.addEventListener("click", () => { coverFileInput.click(); });
    coverFileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        coverFileInput.value = "";
        if (selectedPreset) {
            // 直接应用到已选预设
            try {
                const r = await uploadCover(selectedPreset, file);
                if (r.success) {
                    showStatus("封面已更新: " + selectedPreset);
                    await loadPresetList();
                } else {
                    showStatus(r.error || "封面上传失败", true);
                }
            } catch (err) {
                showStatus("封面上传失败: " + err.message, true);
            }
        } else {
            // 暂存，保存预设时一并上传
            stagedCoverFile = file;
            coverStatus.textContent = `已选择封面: ${file.name}（保存时应用）`;
            coverStatus.style.color = COLORS.accent;
        }
    });

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

            showShaProgress();
            try {
                // 按 sha256 重定位改名文件（非破坏性：无 sha256 或本地无匹配则保留原名）
                const resolved = await resolvePreset(result.data);
                // 无论本地是否有所，完整套用所有条目（缺失项由选择器以 (missing) 显示）
                setNodeData(resolved);
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

    // 保存预设
    saveBtn.addEventListener("click", async () => {
        const name = prompt("请输入预设名称:");
        if (!name || !name.trim()) return;

        const data = getCurrentData();
        if (data.length === 0) {
            showStatus("当前没有 LoRA 配置可保存", true);
            return;
        }

        const trimmedName = name.trim();

        try {
            // 若有暂存封面，先上传
            if (stagedCoverFile) {
                try {
                    const up = await uploadCover(trimmedName, stagedCoverFile);
                    if (!up.success) {
                        showStatus("封面上传失败: " + (up.error || "未知错误"), true);
                    }
                } catch (coverErr) {
                    showStatus("封面上传失败: " + coverErr.message, true);
                }
                stagedCoverFile = null;
                coverStatus.textContent = "";
            }

            showShaProgress();
            try {
                const resp = await api.fetchApi("/naiba/presets/save", {
                    method: "POST",
                    body: JSON.stringify({ name: trimmedName, data }),
                });
                const result = await resp.json();

                if (result.error) {
                    showStatus(result.error, true);
                } else {
                    showStatus("预设保存成功");
                    await loadPresetList();
                }
            } finally {
                hideShaProgress();
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

        const item = presetItems.find((el) => el._name === selectedPreset || el._selected);
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

                showShaProgress();
                try {
                    // 按 sha256 重定位改名文件（非破坏性：无 sha256 或本地无匹配则保留原名）
                    const resolved = await resolvePreset(data);
                    // 无论本地是否有所，完整套用所有条目（缺失项由选择器以 (missing) 显示）
                    setNodeData(resolved);
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
