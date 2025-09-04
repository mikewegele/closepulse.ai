// index.js
import {el} from "./state.js";
import {initTheme} from "./ui/theme.js";
import {initToolbar} from "./ui/toolbar.js";
import {autoStartAgentProc} from "./audio/autostart_agentproc.js";
import {connectSuggestionsWithRetry} from "./backend/suggestClient.js";
import {log} from "./logger.js";
import {setDotColor} from "./ui/dot.js";

initTheme();
initToolbar();

const WS = (window.__API_BASE || '').replace(/^http/, 'ws');
const EXT = window.__CALL_ID || 'EXT_FIXED_ID';

let prevAgentOn = null;

function setDot(on) {
    const dot = document.getElementById('dot');
    if (dot) dot.classList.toggle('on', !!on);
    if (on !== prevAgentOn) {
        log(on ? 'agent:on' : 'agent:off'); // nur bei Zustandswechsel
        prevAgentOn = on;
    }
}

function setSuggestions({s1, s2, s3, trafficLight}) {
    if (el.s1) el.s1.textContent = s1 || '';
    if (el.s2) el.s2.textContent = s2 || '';
    if (el.s3) el.s3.textContent = s3 || '';
    setDotColor(trafficLight.response);
}

async function ensureAgentOn(timeoutMs = 10000) {
    // Agent (falls nötig) starten
    await autoStartAgentProc({
        ws: WS,
        ext: EXT,
        lang: 'de',
        loopback: 'BlackHole 2ch'
    }).then(() => log('agent:start:ok'))
        .catch(e => log(`agent:start:err ${e}`));

    // Warten bis agentStatus === true
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        try {
            const ok = await window.electronAPI.agentStatus();
            setDot(ok);
            if (ok) return true;
        } catch {
        }
        await new Promise(r => setTimeout(r, 250));
    }
    throw new Error('Agent did not come up in time');
}

async function boot() {
    log('boot');

    try {
        await ensureAgentOn();
    } catch (e) {
        log(`agent:timeout ${e?.message || e}`);
        // Du kannst hier ggf. trotzdem einen Retry für den WS versuchen.
    }

    // Jetzt – und erst jetzt – den Suggest-WS öffnen
    // connectSuggestions(WS, EXT, setSuggestions);
    // Falls du lieber robust mit Retry willst:
    connectSuggestionsWithRetry(WS, EXT, setSuggestions, {maxRetries: 10});
}

boot();

// Optional: leichtes Status-Polling, aber ohne Spam
async function pollStatus() {
    try {
        const ok = await window.electronAPI.agentStatus();
        setDot(ok);
    } catch {
    }
    setTimeout(pollStatus, 2000);
}

pollStatus();
