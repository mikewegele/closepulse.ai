// renderer.js
const ASK_URL = "http://localhost:8000/ask";
const TL_URL = "http://localhost:8000/trafficLight";
const TR_URL = "http://localhost:8000/transcribe";
const ANALYZE_URL = "http://localhost:8000/analyze";

function stringifyArg(a) {
    try {
        if (typeof a === "string") return a;
        return JSON.stringify(a);
    } catch {
        return String(a);
    }
}

function forwardLog(...args) {
    const line = args.map(stringifyArg).join(" ");
    window.electronAPI?.log?.(line);
}

const __origLog = console.log.bind(console);
console.log = (...args) => {
    __origLog(...args);
    forwardLog(...args);
};

const el = {
    dot: document.getElementById("dot"),
    s1: document.getElementById("s1"),
    s2: document.getElementById("s2"),
    s3: document.getElementById("s3"),
    rec: document.getElementById("rec"),
    close: document.getElementById("close"),
    wrap: document.querySelector(".wrap")
};

// ---------------- State & UI Controls ----------------
const state = {
    showLatency: JSON.parse(localStorage.getItem("cp_showLatency") ?? "true"),
    theme: localStorage.getItem("cp_theme") || "light",
    analyzeSupported: true
};

applyTheme(state.theme);
ensureToolbar();
ensureLatencyPanel();
updateLatencyVisibility();

function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("cp_theme", theme);
}

function ensureToolbar() {
    // Toolbar oben einfügen (nutzt deine .row und .icon Styles)
    let bar = document.getElementById("cp-toolbar");
    if (!bar) {
        bar = document.createElement("div");
        bar.id = "cp-toolbar";
        bar.className = "row";
        // Theme Button
        const themeBtn = document.createElement("div");
        themeBtn.id = "cp-theme";
        themeBtn.className = "icon";
        themeBtn.title = "Theme umschalten";
        themeBtn.textContent = state.theme === "dark" ? "☀️" : "🌙";
        themeBtn.onclick = () => {
            applyTheme(state.theme === "dark" ? "light" : "dark");
            themeBtn.textContent = state.theme === "dark" ? "☀️" : "🌙";
        };
        // Latency Button
        const latBtn = document.createElement("div");
        latBtn.id = "cp-latency-toggle";
        latBtn.className = "icon";
        latBtn.title = state.showLatency ? "Latenz-Panel ausblenden" : "Latenz-Panel einblenden";
        latBtn.textContent = "⏱️";
        latBtn.setAttribute("aria-pressed", String(state.showLatency));
        latBtn.onclick = () => {
            state.showLatency = !state.showLatency;
            localStorage.setItem("cp_showLatency", JSON.stringify(state.showLatency));
            latBtn.setAttribute("aria-pressed", String(state.showLatency));
            latBtn.title = state.showLatency ? "Latenz-Panel ausblenden" : "Latenz-Panel einblenden";
            updateLatencyVisibility();
        };

        bar.appendChild(themeBtn);
        bar.appendChild(latBtn);
        el.wrap.prepend(bar);
    } else {
        // Sync bestehende
        const themeBtn = document.getElementById("cp-theme");
        if (themeBtn) themeBtn.textContent = state.theme === "dark" ? "☀️" : "🌙";
    }
}

function ensureLatencyPanel() {
    let panel = document.getElementById("latency");
    if (!panel) {
        panel = document.createElement("div");
        panel.id = "latency";
        el.wrap.prepend(panel);
    }
    return panel;
}

function updateLatencyVisibility() {
    const panel = ensureLatencyPanel();
    panel.style.display = state.showLatency ? "block" : "none";
}

function fmtMs(x) {
    if (x == null || Number.isNaN(x)) return "–";
    const ms = x * 1000;
    if (ms < 1) return `${(ms).toFixed(2)} ms`;
    if (ms < 1000) return `${ms.toFixed(0)} ms`;
    return `${(ms / 1000).toFixed(2)} s`;
}

function renderLatency(data) {
    if (!state.showLatency) return;
    const panel = ensureLatencyPanel();
    const lines = [];
    if (data.phase) lines.push(`Phase: ${data.phase}`);
    if (data.total != null) lines.push(`Gesamt: ${fmtMs(data.total)}`);
    if (data.transcribe != null) lines.push(`Transcribe: ${fmtMs(data.transcribe)}`);
    if (data.ask != null) lines.push(`Ask: ${fmtMs(data.ask)}`);
    if (data.trafficLight != null) lines.push(`TrafficLight: ${fmtMs(data.trafficLight)}`);
    if (data.backend && typeof data.backend === "string") lines.push(`Backend: ${data.backend}`);
    panel.textContent = lines.join("\n");
}

// ---------------- Core UI helpers ----------------
function setDotColor(tlObj) {
    // nutzt direkt tlObj.response (Fix)
    const color = tlObj && typeof tlObj === "object" ? tlObj.response : undefined;
    if (!color) {
        el.dot.style.color = "#d9d9d9";
        el.dot.style.background = "rgba(217,217,217,0.6)";
        return;
    }
    if (color === "red") {
        el.dot.style.color = "#e53935";
        el.dot.style.background = "#e53935";
    } else if (color === "yellow") {
        el.dot.style.color = "#fdd835";
        el.dot.style.background = "#fdd835";
    } else if (color === "green") {
        el.dot.style.color = "#43a047";
        el.dot.style.background = "#43a047";
    } else {
        el.dot.style.color = "#d9d9d9";
        el.dot.style.background = "rgba(217,217,217,0.6)";
    }
}

function makeSuggestionsFrom(text) {
    if (!text) return [];
    if (Array.isArray(text)) return text.slice(0, 3).map(s => String(s).trim()).filter(Boolean);
    try {
        const first = text.indexOf("[");
        const last = text.lastIndexOf("]");
        if (first !== -1 && last !== -1 && last > first) {
            const json = text.slice(first, last + 1);
            const arr = JSON.parse(json);
            if (Array.isArray(arr)) return arr.slice(0, 3).map(s => String(s).trim()).filter(Boolean);
        }
    } catch {
    }
    const out = [];
    const re = /^\s*-\s+(.+?)\s*$/gm;
    let m;
    while ((m = re.exec(text)) && out.length < 3) out.push(m[1]);
    if (out.length) return out;
    return (text || "").split(/(?<=[.!?])\s+/).map(t => t.trim()).filter(Boolean).slice(0, 3);
}

function renderSuggestions(sugg) {
    const ids = [el.s1, el.s2, el.s3];
    ids.forEach((button, i) => {
        const full = sugg[i];
        if (full && full.length) {
            button.style.display = "block";
            button.disabled = false;
            button.title = full;
            button.textContent = full;
        } else {
            button.textContent = "";
            button.title = "";
            button.style.display = "none";
        }
    });
}

const ro = new ResizeObserver(() => {
    const neededHeight = el.wrap.scrollHeight + 40;
    window.electronAPI?.resizeWindow(neededHeight);
});
ro.observe(el.wrap);

function safeJson(res) {
    return res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`));
}

function convoToString(lastTurns) {
    return lastTurns.map(t => `${t.role === "user" ? "User" : "Assistant"}: ${t.content}`).join("\n");
}

// ---------------- Conversation state ----------------
const MAX_TURNS = 4;
let turns = [];

function pushTurn(role, content) {
    turns.push({role, content});
    if (turns.length > MAX_TURNS) turns = turns.slice(-MAX_TURNS);
}

// ---------------- Backend calls ----------------
let askAborter = null;
let tlAborter = null;

async function askBackendSeparate(conv, tStart) {
    if (askAborter) askAborter.abort();
    if (tlAborter) tlAborter.abort();
    askAborter = new AbortController();
    tlAborter = new AbortController();
    const headers = {"Content-Type": "application/json", "Connection": "keep-alive"};
    const body = JSON.stringify([{role: "user", content: conv}]);

    const askP = fetch(ASK_URL, {method: "POST", headers, body, signal: askAborter.signal}).then(safeJson);
    const tlP = fetch(TL_URL, {method: "POST", headers, body, signal: tlAborter.signal}).then(safeJson);

    let askDur = null, tlDur = null;

    tlP.then(tl => {
        try {
            setDotColor(tl);
        } catch {
        }
        tlDur = tl?.duration ?? null;
        const total = (performance.now() - tStart) / 1000;
        renderLatency({phase: "Antwort (parallel)", total, ask: askDur, trafficLight: tlDur});
        console.log("TL:", tl);
    }).catch(e => {
        console.log("TL failed:", e?.message || e);
    });

    try {
        const ask = await askP;
        askDur = ask?.duration ?? null;
        renderSuggestions(makeSuggestionsFrom(ask.response));
        const total = (performance.now() - tStart) / 1000;
        renderLatency({phase: "Antwort (parallel)", total, ask: askDur, trafficLight: tlDur});
        return ask.response;
    } catch (e) {
        console.log("ask failed:", e?.message || e);
        const total = (performance.now() - tStart) / 1000;
        renderLatency({phase: "Fehler", total});
        return "";
    }
}

async function askBackendAnalyze(conv, tStart) {
    const headers = {"Content-Type": "application/json", "Connection": "keep-alive"};
    const body = JSON.stringify([{role: "user", content: conv}]);
    try {
        const res = await fetch(ANALYZE_URL, {method: "POST", headers, body}).then(safeJson);
        try {
            setDotColor(res?.trafficLight);
        } catch {
        }
        renderSuggestions(makeSuggestionsFrom(res?.suggestions));
        const total = (performance.now() - tStart) / 1000;
        renderLatency({
            phase: "Antwort (combined)",
            total,
            ask: res?.durations?.ask ?? null,
            trafficLight: res?.durations?.trafficLight ?? null,
            backend: "analyze"
        });
        return Array.isArray(res?.suggestions) ? JSON.stringify(res.suggestions) : String(res?.suggestions ?? "");
    } catch (e) {
        state.analyzeSupported = false;
        console.log("/analyze not available, falling back:", e?.message || e);
        return askBackendSeparate(conv, tStart);
    }
}

async function askBackend(conv) {
    if (!conv || !conv.trim()) return "";
    const tStart = performance.now();
    renderLatency({phase: "Sende Anfrage..."});
    if (state.analyzeSupported) return askBackendAnalyze(conv, tStart);
    return askBackendSeparate(conv, tStart);
}

// ---------------- Send text / transcribe ----------------
async function sendUserText(text) {
    if (!text || !text.trim()) return;
    pushTurn("user", text);
    [el.s1, el.s2, el.s3].forEach(b => (b.disabled = true));
    const resp = await askBackend(convoToString(turns));
    if (resp) pushTurn("assistant", resp);
    [el.s1, el.s2, el.s3].forEach(b => (b.disabled = false));
}

async function transcribeAndSend(blob) {
    const fd = new FormData();
    fd.append("file", blob, "recording.webm");
    const t0 = performance.now();
    try {
        const tr = await fetch(TR_URL, {method: "POST", body: fd}).then(safeJson);
        const total = (performance.now() - t0) / 1000;
        renderLatency({phase: "Transkription", total, transcribe: tr?.duration ?? null});
        if (tr && tr.text) await sendUserText(tr.text);
    } catch (e) {
        const total = (performance.now() - t0) / 1000;
        renderLatency({phase: "Transkription fehlgeschlagen", total});
        console.log("/transcribe failed:", e?.message || e);
    }
}

// ---------------- Recording (timeslices) ----------------
let mediaRecorder = null;
let chunks = [];
let recording = false;
let streamRef = null;
let isStarting = false;

async function startRecording() {
    if (isStarting || recording) return;
    isStarting = true;
    try {
        streamRef = await navigator.mediaDevices.getUserMedia({audio: true});
        mediaRecorder = new MediaRecorder(streamRef, {mimeType: "audio/webm"});
        chunks = [];
        mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) chunks.push(e.data);
        };
        mediaRecorder.start(500); // 500ms Timeslices
        recording = true;
        el.rec.textContent = "⏹";
    } catch (e) {
        console.log("getUserMedia failed:", e);
        recording = false;
        el.rec.textContent = "⏺";
    } finally {
        isStarting = false;
    }
}

async function stopRecording() {
    if (!recording || !mediaRecorder) return;
    return new Promise(resolve => {
        const onStop = async () => {
            const approxBytesPerSec = 16000;
            const maxSeconds = 10;
            let size = 0, sel = [];
            for (let i = chunks.length - 1; i >= 0; i--) {
                size += chunks[i].size;
                sel.unshift(chunks[i]);
                if (size > approxBytesPerSec * maxSeconds) break;
            }
            const blob = new Blob(sel.length ? sel : chunks, {type: "audio/webm"});
            chunks = [];
            if (streamRef) {
                streamRef.getTracks().forEach(t => t.stop());
                streamRef = null;
            }
            await transcribeAndSend(blob);
            mediaRecorder = null;
            recording = false;
            el.rec.textContent = "⏺";
            resolve();
        };
        if (mediaRecorder.state !== "inactive") {
            mediaRecorder.addEventListener("stop", onStop, {once: true});
            mediaRecorder.stop();
        } else {
            onStop();
        }
    });
}

function toggleRecording() {
    if (!recording) startRecording(); else stopRecording();
}

// ---------------- Wire up buttons ----------------
el.s1.onclick = () => {
    const t = el.s1.textContent;
    if (t) sendUserText(t);
};
el.s2.onclick = () => {
    const t = el.s2.textContent;
    if (t) sendUserText(t);
};
el.s3.onclick = () => {
    const t = el.s3.textContent;
    if (t) sendUserText(t);
};
el.rec.onclick = () => toggleRecording();
el.close.onclick = () => window.close();
