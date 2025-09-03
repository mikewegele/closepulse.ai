// renderer/index.js
import {el} from "./state.js";
import {initTheme} from "./ui/theme.js";
import {initToolbar} from "./ui/toolbar.js";
import {sendUserText} from "./backend/api.js";
import {autoStartAgent} from "./audio/autostart.js";

initTheme();
initToolbar();

if (el.s1) el.s1.onclick = () => {
    const t = (el.s1.textContent || "").trim();
    if (t) sendUserText(t);
};
if (el.s2) el.s2.onclick = () => {
    const t = (el.s2.textContent || "").trim();
    if (t) sendUserText(t);
};
if (el.s3) el.s3.onclick = () => {
    const t = (el.s3.textContent || "").trim();
    if (t) sendUserText(t);
};

const WS = (window.__API_BASE || '').replace(/^http/, 'ws');
const EXT = window.__CALL_ID || 'EXT_FIXED_ID';

function setDot(on) {
    const dot = document.getElementById('dot');
    if (!dot) return;
    dot.classList.toggle('on', !!on);
}

async function pollStatus() {
    try {
        const ok = await window.electronAPI.agentStatus();
        setDot(ok);
    } catch {
    }
    setTimeout(pollStatus, 1500);
}

autoStartAgent({ws: WS, ext: EXT});
pollStatus();
