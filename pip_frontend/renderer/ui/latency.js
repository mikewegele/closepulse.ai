import {el, state} from "../state.js";
import {fmtMs} from "../utils.js";

function ensureLatencyPanel() {
    let panel = document.getElementById("latency");
    if (!panel) {
        panel = document.createElement("div");
        panel.id = "latency";
        el.wrap.prepend(panel);
    }
    return panel;
}

export function setLatencyVisible(visible) {
    state.showLatency = visible;
    localStorage.setItem("cp_showLatency", JSON.stringify(visible));
    ensureLatencyPanel().style.display = visible ? "block" : "none";
}

export function initLatency() {
    setLatencyVisible(state.showLatency);
}

export function renderLatency(data) {
    if (!state.showLatency) return;
    const panel = ensureLatencyPanel();
    const lines = [];
    if (data.phase) lines.push(`Phase: ${data.phase}`);
    if (data.total != null) lines.push(`Gesamt: ${fmtMs(data.total)}`);
    if (data.transcribe != null) lines.push(`Transcribe: ${fmtMs(data.transcribe)}`);
    if (data.ask != null) lines.push(`Ask: ${fmtMs(data.ask)}`);
    if (data.trafficLight != null) lines.push(`TrafficLight: ${fmtMs(data.trafficLight)}`);
    if (typeof data.backend === 'string') lines.push(`Backend: ${data.backend}`);
    panel.textContent = lines.join("\n");
}