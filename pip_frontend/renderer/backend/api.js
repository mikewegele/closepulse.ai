import {ANALYZE_URL, ASK_URL, MAX_TURNS, TL_URL} from "../config.js";
import {state} from "../state.js";
import {convoToString, pushTurn, safeJson} from "../utils.js";
import {renderLatency} from "../ui/latency.js";
import {makeSuggestionsFrom, renderSuggestions} from "../ui/suggestions.js";
import {setDotColor} from "../ui/dot.js";

export async function askBackend(conv) {
    if (!conv || !conv.trim()) return "";
    const tStart = performance.now();
    renderLatency({phase: 'Sende Anfrage...'});
    if (state.analyzeSupported) return askBackendAnalyze(conv, tStart);
    return askBackendSeparate(conv, tStart);
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

async function askBackendSeparate(conv, tStart) {
    if (state.askAborter) state.askAborter.abort();
    if (state.tlAborter) state.tlAborter.abort();
    state.askAborter = new AbortController();
    state.tlAborter = new AbortController();
    const headers = {'Content-Type': 'application/json', 'Connection': 'keep-alive'};
    const body = JSON.stringify([{role: 'user', content: conv}]);

    const askP = fetch(ASK_URL, {method: 'POST', headers, body, signal: state.askAborter.signal}).then(safeJson);
    const tlP = fetch(TL_URL, {method: 'POST', headers, body, signal: state.tlAborter.signal}).then(safeJson);

    let askDur = null, tlDur = null;

    tlP.then(tl => {
        try {
            setDotColor(tl);
        } catch {
        }
        tlDur = tl?.duration ?? null;
        const total = (performance.now() - tStart) / 1000;
        renderLatency({phase: 'Antwort (parallel)', total, ask: askDur, trafficLight: tlDur});
        console.log('TL:', tl);
    }).catch(e => console.log('TL failed:', e?.message || e));

    try {
        const ask = await askP;
        askDur = ask?.duration ?? null;
        renderSuggestions(makeSuggestionsFrom(ask.response));
        const total = (performance.now() - tStart) / 1000;
        renderLatency({phase: 'Antwort (parallel)', total, ask: askDur, trafficLight: tlDur});
        return ask.response;
    } catch (e) {
        console.log('ask failed:', e?.message || e);
        const total = (performance.now() - tStart) / 1000;
        renderLatency({phase: 'Fehler', total});
        return '';
    }
}

async function askBackendAnalyze(conv, tStart) {
    const headers = {'Content-Type': 'application/json', 'Connection': 'keep-alive'};
    const body = JSON.stringify([{role: 'user', content: conv}]);
    try {
        const res = await fetch(ANALYZE_URL, {method: 'POST', headers, body}).then(safeJson);
        try {
            setDotColor(res?.trafficLight);
        } catch {
        }
        renderSuggestions(makeSuggestionsFrom(res?.suggestions));
        const total = (performance.now() - tStart) / 1000;
        renderLatency({
            phase: 'Antwort (combined)',
            total,
            ask: res?.durations?.ask ?? null,
            trafficLight: res?.durations?.trafficLight ?? null,
            backend: 'analyze'
        });
        return Array.isArray(res?.suggestions) ? JSON.stringify(res.suggestions) : String(res?.suggestions ?? '');
    } catch (e) {
        state.analyzeSupported = false;
        console.log('/analyze not available, falling back:', e?.message || e);
        return askBackendSeparate(conv, tStart);
    }
}