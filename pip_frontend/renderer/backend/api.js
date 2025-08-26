import {ASK_URL, MAX_TURNS, TL_URL} from "../config.js";
import {state} from "../state.js";
import {convoToString, pushTurn, safeJson} from "../utils.js";
import {makeSuggestionsFrom, renderSuggestions} from "../ui/suggestions.js";
import {setDotColor} from "../ui/dot.js";

export async function askBackend(conv) {
    if (!conv || !conv.trim()) return "";
    return askBackendSeparate(conv);
}

export async function sendUserText(text) {
    if (!text || !text.trim()) return;
    pushTurn(state, MAX_TURNS, 'user', text);
    disableSuggestionButtons(true);
    const resp = await askBackend(convoToString(state.turns));
    if (resp) pushTurn(state, MAX_TURNS, 'assistant', resp);
    disableSuggestionButtons(false);
}

function disableSuggestionButtons(disabled) {
    for (const id of ['s1', 's2', 's3']) {
        const b = document.getElementById(id);
        if (b) b.disabled = disabled;
    }
}

async function askBackendSeparate(conv) {
    if (state.askAborter) state.askAborter.abort();
    if (state.tlAborter) state.tlAborter.abort();
    state.askAborter = new AbortController();
    state.tlAborter = new AbortController();
    const headers = {'Content-Type': 'application/json', 'Connection': 'keep-alive'};
    const body = JSON.stringify([{role: 'user', content: conv}]);
    const askP = fetch(ASK_URL, {method: 'POST', headers, body, signal: state.askAborter.signal}).then(safeJson);
    const tlP = fetch(TL_URL, {method: 'POST', headers, body, signal: state.tlAborter.signal}).then(safeJson);

    tlP.then(tl => {
        try {
            console.log(tl)
            setDotColor(tl);
        } catch {
        }
        console.log('TL:', tl);
    }).catch(e => console.log('TL failed:', e?.message || e));

    try {
        const ask = await askP;
        renderSuggestions(makeSuggestionsFrom(ask.response));
        return ask.response;
    } catch (e) {
        console.log('ask failed:', e?.message || e);
        return '';
    }
}
