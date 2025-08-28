import {el, state} from "../state.js";
import {applyTheme} from "./theme.js";
import {toggleRecording} from "../audio/recorder.js";
import {requestSuggestionsOnDemand} from "../audio/analysis_on_demand.js";

export function initToolbar() {
    let bar = document.getElementById("cp-toolbar");
    if (!bar) {
        bar = document.createElement("div");
        bar.id = "cp-toolbar";
        bar.className = "row";
        el.wrap.appendChild(bar); // statt prepend → jetzt unten
    }

    const TELNYX_MODE = !!(window.__CALL_ID); // Auto: wenn CALL_ID gesetzt ist, kein Mic

    const buttons = [
        // 💡 Vorschläge holen (on demand)
        {
            id: "cp-suggest",
            emoji: "💡",
            title: "Vorschläge holen",
            onclick: () => requestSuggestionsOnDemand(),
        },
        // 🎤 Aufnahme (im Telnyx-Mode ausgeblendet)
        {
            id: "cp-rec",
            emoji: "🎤",
            title: "Aufnahme starten/stoppen",
            onclick: () => toggleRecording(),
            hidden: TELNYX_MODE, // Mic ausblenden, wenn Telnyx läuft
        },
        // 🌙/☀️ Theme
        {
            id: "cp-theme",
            emoji: () => (state.theme === "dark" ? "☀️" : "🌙"),
            title: "Theme umschalten",
            onclick: () => {
                applyTheme(state.theme === "dark" ? "light" : "dark");
                syncTheme();
            },
        },
        // ❌ Schließen
        {
            id: "cp-close",
            emoji: "❌",
            title: "Fenster schließen",
            onclick: () => window.close(),
        },
    ];

    // helper für theme & latency dynamisch
    const syncTheme = () => {
        const btn = document.getElementById("cp-theme");
        if (btn) btn.textContent = state.theme === "dark" ? "☀️" : "🌙";
    };

    // Buttons rendern
    buttons.forEach((cfg) => {
        let btn = document.getElementById(cfg.id);
        if (!btn) {
            btn = document.createElement("div");
            btn.id = cfg.id;
            btn.className = "icon";
            btn.textContent = typeof cfg.emoji === "function" ? cfg.emoji() : cfg.emoji;
            btn.title = typeof cfg.title === "function" ? cfg.title() : cfg.title;
            btn.onclick = cfg.onclick;
            bar.appendChild(btn);
        }
        btn.style.display = cfg.hidden ? "none" : "flex";
    });

    // initial sync
    syncTheme();
}
