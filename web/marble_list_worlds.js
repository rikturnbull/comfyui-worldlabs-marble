import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// "Marble: List Worlds" frontend.
//
// Clicking "Update" posts the node's api_key to the /marble/list_worlds route
// and fills the "world" combo with the returned world names. The names are the
// combo's values; the backend resolves a name back to an id on run, so there is
// no hidden id widget to leak into side panels.

// A busy cursor that survives LiteGraph. LiteGraph rewrites the canvas's inline
// `style.cursor` every frame, so setting it inline loses immediately. A
// stylesheet rule with !important beats that inline (non-important) style, and
// we just toggle a class on the canvas element.
(function injectBusyCursorStyle() {
    if (document.getElementById("marble-busy-cursor-style")) return;
    const style = document.createElement("style");
    style.id = "marble-busy-cursor-style";
    style.textContent = ".marble-busy-cursor { cursor: progress !important; }";
    document.head.appendChild(style);
})();

// Non-blocking notification. A native alert() is modal and synchronous: while
// it's up it freezes the JS thread, and after it closes the browser briefly
// suppresses focus/pointer events globally — which leaves every node's text
// widget (api_key, etc.) momentarily uneditable. ComfyUI's toast avoids that.
function notify(detail, severity = "error") {
    const toast = app.extensionManager?.toast;
    if (toast) {
        toast.add({ severity, summary: "Marble", detail, life: 5000 });
    } else {
        console[severity === "error" ? "error" : "log"]("[Marble]", detail);
    }
}

app.registerExtension({
    name: "marble.ListWorlds",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== "MarbleListWorlds") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            const node = this;

            const getWidget = (name) => node.widgets?.find((w) => w.name === name);
            const combo = getWidget("world");

            let busy = false;
            const canvasEl = () => app.canvas?.canvas;

            const setBusy = (on) => {
                busy = on;
                updateButton.name = on ? "Updating…" : "Update";
                updateButton.disabled = on; // litegraph dims disabled widgets
                const el = canvasEl();
                if (el) el.classList.toggle("marble-busy-cursor", on);
                node.setDirtyCanvas(true, true);
            };

            const updateButton = node.addWidget("button", "Update", "update", async () => {
                if (busy) return; // ignore clicks while a request is in flight
                if (!combo) return;
                const apiKey = getWidget("api_key")?.value ?? "";

                setBusy(true);
                try {
                    const resp = await api.fetchApi("/marble/list_worlds", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ api_key: apiKey }),
                    });
                    const data = await resp.json();
                    if (!resp.ok || data.error) {
                        notify(data.error || ("HTTP " + resp.status));
                        return;
                    }

                    // Names are already made unique server-side (worlds_to_items).
                    const names = (data.worlds || []).map((w) => w.name);
                    combo.options.values = names.length ? names : ["<no worlds found>"];
                    combo.value = combo.options.values[0];
                    node.setDirtyCanvas(true, true);
                } catch (e) {
                    notify("Failed to list worlds: " + e);
                } finally {
                    setBusy(false);
                }
            });

            return r;
        };
    },
});
