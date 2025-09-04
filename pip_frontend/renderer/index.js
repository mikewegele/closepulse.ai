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
        log(on ? 'agent:on' : 'agent:off');
        prevAgentOn = on;
    }
}

function setSuggestions({s1, s2, s3, trafficLight}) {
    if (el.s1) el.s1.textContent = s1 || '';
    if (el.s2) el.s2.textContent = s2 || '';
    if (el.s3) el.s3.textContent = s3 || '';
    setDotColor(trafficLight.response);
}

function findBySubstr(cands, available) {
    const L = (available || []).map(s => (s || '').toLowerCase());
    for (const c of cands) {
        const x = (c || '').toLowerCase();
        const hit = L.find(s => s.includes(x));
        if (hit) return available[L.indexOf(hit)];
    }
    return null;
}

async function pickInputDevices() {
    const platform = await window.electronAPI.getPlatform();
    const dev = await window.electronAPI.agentList().catch(() => ({}));
    const inputs = dev?.inputs || [];

    const loopbackMac = ['CP MultiOutput', 'BlackHole 2ch', 'BlackHole', 'Loopback', 'Soundflower (2ch)'];
    const loopbackWin = ['CABLE Output', 'VB-Audio Cable', 'VoiceMeeter Output', 'VoiceMeeter Aux Output', 'Stereo Mix'];
    const micMac = ['MacBook Pro-Mikrofon', 'MacBook-Mikrofon', 'Built-in Microphone', 'Internal Microphone'];
    const micWin = ['Microphone', 'Mikrofon', 'Headset Microphone', 'USB Microphone'];

    const loopback = platform === 'darwin'
        ? findBySubstr(loopbackMac, inputs)
        : platform === 'win32'
            ? findBySubstr(loopbackWin, inputs)
            : null;

    const mic = platform === 'darwin'
        ? findBySubstr(micMac, inputs)
        : platform === 'win32'
            ? findBySubstr(micWin, inputs)
            : null;

    return {platform, loopback, mic};
}

function pickLang() {
    const n = (navigator.language || 'de').toLowerCase();
    if (n.startsWith('de')) return 'de';
    if (n.startsWith('en')) return 'en';
    if (n.startsWith('fr')) return 'fr';
    if (n.startsWith('es')) return 'es';
    return 'de';
}

async function ensureAgentOn(timeoutMs = 10000) {
    const {loopback, mic} = await pickInputDevices();
    const lang = pickLang();

    await autoStartAgentProc({
        ws: WS,
        ext: EXT,
        lang,
        loopback: loopback || undefined,
        mic: loopback ? undefined : (mic || undefined)
    }).then(() => log('agent:start:ok'))
        .catch(e => log(`agent:start:err ${e}`));

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
    }
    connectSuggestionsWithRetry(WS, EXT, setSuggestions, {maxRetries: 10});
}

boot();

async function pollStatus() {
    try {
        const ok = await window.electronAPI.agentStatus();
        setDot(ok);
    } catch {
    }
    setTimeout(pollStatus, 2000);
}

pollStatus();
