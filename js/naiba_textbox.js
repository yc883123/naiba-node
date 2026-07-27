import { app } from "../../scripts/app.js";

// Naiba Textbox 前端：把 passthrough 进入的字符串回显到节点的 customtext 预览框
// （print_to_screen=True 会把 text 输入渲染成 customtext 控件，需要 onExecuted 手动写入）
app.registerExtension({
    name: "naiba_textbox",

    beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "NaibaTextbox") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);

            const overrideWidget = this.widgets?.find(
                (widget) => widget.name === "allow_passthrough_override"
            );
            if (overrideWidget) {
                overrideWidget.label = "允许透传覆盖";
            }
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);

            if (!message || !("text" in message) || message.text == null) return;

            const text = Array.isArray(message.text)
                ? message.text.join("")
                : String(message.text);

            for (const widget of this.widgets) {
                if (widget.type === "customtext") {
                    widget.value = text;
                }
            }

            this.onResize?.(this.size);
            app.graph?.setDirtyCanvas(true, true);
        };
    },
});
