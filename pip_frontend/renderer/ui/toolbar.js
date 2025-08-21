import {el, state} from "../state.js";
import {applyTheme} from "./theme.js";
import {setLatencyVisible} from "./latency.js";
import {toggleRecording} from "../audio/recorder.js";

export function initToolbar() {
    let bar = document.getElementById("cp-toolbar");
    if (!bar) {
        bar = document.createElement("div");
        bar.id = "cp-toolbar";
        bar.className = "row";
        el.wrap.appendChild(bar); // statt prepend → jetzt unten
    }

    // Reihenfolge: 🎤 🌙/☀️ ⏱️ ❌
    const buttons = [
        {
            id: "cp-rec",
            emoji: "🎤",
            title: "Aufnahme starten/stoppen",
            onclick: () => toggleRecording(),
        },
        {
            id: "cp-theme",
            emoji: () => (state.theme === "dark" ? "☀️" : "🌙"),
            title: "Theme umschalten",
            onclick: () => {
                applyTheme(state.theme === "dark" ? "light" : "dark");
                syncTheme();
            },
        },
        {
            id: "cp-latency",
            emoji: "⏱️",
            title: () =>
                state.showLatency
                    ? "Latenz-Panel ausblenden"
                    : "Latenz-Panel einblenden",
            onclick: () => {
                setLatencyVisible(!state.showLatency);
                syncLatency();
            },
        },
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
    const syncLatency = () => {
        const btn = document.getElementById("cp-latency");
        if (btn) btn.title = state.showLatency ? "Latenz-Panel ausblenden" : "Latenz-Panel einblenden";
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
    });

    // initial sync
    syncTheme();
    syncLatency();
}
