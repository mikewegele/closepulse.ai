import {el} from "./state.js";
import {initTheme} from "./ui/theme.js";
import {initToolbar} from "./ui/toolbar.js";
import {sendUserText} from "./backend/api.js";
import {autoStartAgentProc} from "./audio/autostart_agentproc.js";
import {connectSuggestions} from "./backend/suggestClient.js";
import {log} from "./logger.js";

initTheme();
initToolbar();

[el.s1, el.s2, el.s3].forEach(btn => {
    if (!btn) return;
    btn.onclick = () => {
        const t = (btn.textContent || '').trim();
        if (t) sendUserText(t);
        log(`picked "${t.slice(0, 60)}"`);
    };
});

const WS = (window.__API_BASE || '').replace(/^http/, 'ws');
const EXT = window.__CALL_ID || 'EXT_FIXED_ID';

function setDot(on) {
    const dot = document.getElementById('dot');
    if (!dot) return;
    dot.classList.toggle('on', !!on);
    log(on ? 'agent:on' : 'agent:off');
}

function setSuggestions({s1, s2, s3}) {
    if (el.s1) el.s1.textContent = s1 || '';
    if (el.s2) el.s2.textContent = s2 || '';
    if (el.s3) el.s3.textContent = s3 || '';
    const hint = [s1, s2, s3].filter(Boolean).map(s => `"${s.slice(0, 40)}"`).join(' | ');
    log(`suggest ${hint}`);
}

log('boot');
autoStartAgentProc({ws: WS, ext: EXT}).then(() => log('agent:start:ok')).catch(e => log(`agent:start:err ${e}`));
connectSuggestions(WS, EXT, setSuggestions);

async function pollStatus() {
    try {
        const ok = await window.electronAPI.agentStatus();
        setDot(ok);
    } catch {
    }
    setTimeout(pollStatus, 1200);
}

pollStatus();
