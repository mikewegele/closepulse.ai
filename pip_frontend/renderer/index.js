// renderer/index.js
import {el} from "./state.js";
import {initTheme} from "./ui/theme.js";
import {initToolbar} from "./ui/toolbar.js";
import {sendUserText} from "./backend/api.js";

// Init UI
initTheme();
initToolbar();

// Buttons für Vorschläge
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

// ---- Agent Auto-Start + Statusanzeige ----
const WS = (window.__API_BASE || '').replace(/^http/, 'ws');
const EXT = window.__CALL_ID || 'EXT_FIXED_ID';

async function ensureAgentRunning() {
    try {
        const plat = await window.electronAPI.getPlatform(); // 'darwin' | 'win32' | ...
        // macOS: prüfen ob BlackHole da ist (nur Hinweis)
        if (plat === 'darwin') {
            const info = await window.electronAPI.agentList();
            const hasBH = JSON.stringify(info || {}).toLowerCase().includes('blackhole 2ch');
            if (!hasBH) {
                console.warn('BlackHole 2ch nicht gefunden. Bitte via Homebrew installieren: brew install blackhole-2ch und Multi-Output-Device einrichten.');
            }
        }
        await window.electronAPI.agentStart({
            ws: WS,
            ext: EXT,
            // mic: optional Name-Substring, z.B. "MacBook Pro Microphone"
            spk: (plat === 'darwin') ? 'BlackHole 2ch' : undefined // Windows: leer lassen = erstes WASAPI-Output
        });
    } catch (e) {
        console.error('Agent start failed:', e);
    }
}

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

ensureAgentRunning();
pollStatus();
