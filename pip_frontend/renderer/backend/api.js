import {ANALYZE_FAST_URL, MAX_TURNS} from "../../config.js";
import {state} from "../state.js";
import {convoToString, pushTurn, safeJson} from "../utils.js";
import {makeSuggestionsFrom, renderSuggestions} from "../ui/suggestions.js";
import {setDotColor} from "../ui/dot.js";

export async function sendUserText(text) {
    if (!text?.trim()) return;
    pushTurn(state, MAX_TURNS, "user", text);
    try {
        const body = JSON.stringify([{role: "user", content: convoToString(state.turns)}]);
        const res = await fetch(ANALYZE_FAST_URL, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body
        }).then(safeJson);
        if (res.suggestions) pushTurn(state, MAX_TURNS, "assistant", res.suggestions);
        renderSuggestions(makeSuggestionsFrom(res.suggestions));
        const tl = (res?.trafficLight?.response || "").trim().replace(/['"]/g, "");
        setDotColor(tl);
    } catch (e) {
        console.log("analyze failed:", e?.message || e);
    }
}
