/**
 * Preset Folder Reader - 前端扩展
 * 在节点上添加『刷新预设列表』按钮，重新扫描 presets/ 文件夹并更新下拉选项。
 */

import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Naiba.PresetFolderReader",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "Preset Folder Reader") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

            const btn = this.addWidget(
                "button",
                "🔄 刷新预设列表",
                null,
                async () => {
                    try {
                        const resp = await api.fetchApi("/naiba/presets/list");
                        const result = await resp.json();
                        const files = (result.presets && result.presets.length)
                            ? result.presets
                            : ["(无预设文件)"];
                        const w = this.widgets.find((x) => x.name === "preset_name");
                        if (w) {
                            w.options.values = files;
                            if (!files.includes(w.value)) {
                                w.value = files[0];
                            }
                        }
                    } catch (e) {
                        console.error("[PresetFolderReader] 刷新失败:", e);
                    }
                }
            );
            if (btn) btn.tooltip = "重新扫描 presets 文件夹";

            return r;
        };
    },
});
