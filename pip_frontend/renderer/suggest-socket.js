// renderer/suggest-socket.js
import {el} from "./state.js";
import {renderSuggestions} from "./ui/suggestions.js";

export function renderTrafficLight(tl) {
    const node = el.trafficLight;
    if (!node) return;
    node.dataset.state = tl || "yellow";
    node.textContent = tl || "yellow";
}

function extractTL(tl) {
    if (!tl) return "yellow";
    if (typeof tl === "string") return ["green", "yellow", "red"].includes(tl) ? tl : "yellow";
    if (typeof tl === "object" && typeof tl.response === "string") {
        return ["green", "yellow", "red"].includes(tl.response) ? tl.response : "yellow";
    }
    return "yellow";
}

export function connectSuggestWS(url, ext = "default", convId) {
    const wsUrl = `${url}?ext=${encodeURIComponent(ext)}${convId ? `&conv=${encodeURIComponent(convId)}` : ""}`;
    const ws = new WebSocket(wsUrl);
    let ping = null;

    ws.onopen = () => {
        ping = setInterval(() => {
            try {
                ws.send("1");
            } catch {
            }
        }, 25000);
    };

    ws.onmessage = (ev) => {
        try {
            const data = JSON.parse(ev.data);
            const suggestions = Array.isArray(data?.suggestions) ? data.suggestions.slice(0, 3) : [];
            const tl = extractTL(data?.trafficLight);
            renderSuggestions(suggestions);
            renderTrafficLight(tl);
            // optional: durations anzeigen
            // console.debug("latency", data?.durations?.total);
        } catch (e) {
            console.warn("suggest parse error", e);
        }
    };

    ws.onclose = () => {
        if (ping) clearInterval(ping);
        setTimeout(() => connectSuggestWS(url, ext, convId), 1000);
    };

    ws.onerror = () => {
        try {
            ws.close();
        } catch {
        }
    };

    return ws;
}
