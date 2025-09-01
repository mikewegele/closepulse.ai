import {makeSuggestionsFrom, renderSuggestions} from "../ui/suggestions.js";
import {setDotColor} from "../ui/dot.js";

export async function requestSuggestionsOnDemand() {
    const API_BASE = window.__API_BASE || "";
    const callId = window.__CALL_ID || "";
    if (!callId) return;

    const btn = document.getElementById("cp-suggest");
    const prev = btn?.textContent;
    if (btn) {
        btn.textContent = "⏳";
        btn.style.opacity = "0.8";
        btn.style.pointerEvents = "none";
    }

    try {
        const res = await fetch(`${API_BASE}/suggest_audio?ext_id=${encodeURIComponent(callId)}&save=1`, {
            method: "POST",
            headers: {"x-conversation-id": callId}
        }).then(r => r.json());

        const sugg = makeSuggestionsFrom(res?.suggestions);
        renderSuggestions(sugg);
        const tl = (res?.trafficLight?.response || "").toString().toLowerCase();
        if (tl) setDotColor(tl);
    } finally {
        if (btn) {
            btn.textContent = prev || "💡";
            btn.style.opacity = "1";
            btn.style.pointerEvents = "";
        }
    }
}