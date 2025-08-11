// renderer.js
const ASK_URL = "http://localhost:8000/ask";
const TL_URL = "http://localhost:8000/trafficLight";
const TR_URL = "http://localhost:8000/transcribe";

// ---- Logging: Renderer -> Main (Terminal) ----
function stringifyArg(a) {
    try {
        if (typeof a === 'string') return a;
        return JSON.stringify(a);
    } catch {
        return String(a);
    }
}

function forwardLog(...args) {
    const line = args.map(stringifyArg).join(' ');
    window.electronAPI?.log?.(line);
}

// DevTools + Terminal parallel
const __origLog = console.log.bind(console);
console.log = (...args) => {
    __origLog(...args);
    forwardLog(...args);
};
// ----------------------------------------------

let fullTranscript = "";
let mediaRecorder = null;
let chunks = [];
let recording = false;
let streamRef = null;
let isStarting = false;

function setDotColor(ampel) {
    const dot = document.getElementById("dot");
    // Farbe setzen
    console.log(ampel)
    const trafficLightColor = JSON.parse(ampel).response;
    if (trafficLightColor === "red") {
        dot.style.color = "#e53935";
        dot.style.background = "#e53935";
    } else if (trafficLightColor === "yellow") {
        dot.style.color = "#fdd835";
        dot.style.background = "#fdd835";
    } else if (trafficLightColor === "green") {
        dot.style.color = "#43a047";
        dot.style.background = "#43a047";
    } else {
        dot.style.color = "#d9d9d9";
        dot.style.background = "rgba(217,217,217,0.6)";
    }
}

function makeSuggestionsFrom(text) {
    if (!text) return [];

    // 1) Bereits ein Array? (falls Backend schon als Array liefert)
    if (Array.isArray(text)) {
        return text.slice(0, 3).map(s => String(s).trim()).filter(Boolean);
    }

    // 2) JSON-Array aus Text extrahieren und parsen
    try {
        const first = text.indexOf('[');
        const last = text.lastIndexOf(']');
        if (first !== -1 && last !== -1 && last > first) {
            const json = text.slice(first, last + 1);
            const arr = JSON.parse(json);
            if (Array.isArray(arr)) {
                return arr.slice(0, 3).map(s => String(s).trim()).filter(Boolean);
            }
        }
    } catch (_) {
    }

    // 3) Fallback: nur Zeilenanfang-Bullets matchen (vermeidet "E-Mail"-Probleme)
    const out = [];
    const re = /^\s*-\s+(.+?)\s*$/gm;
    let m;
    while ((m = re.exec(text)) && out.length < 3) out.push(m[1]);
    if (out.length) return out;

    // 4) Letzter Fallback: grob nach Sätzen splitten
    return (text || "")
        .split(/(?<=[.!?])\s+/)
        .map(t => t.trim())
        .filter(Boolean)
        .slice(0, 3);
}

function renderSuggestions(sugg) {
    const ids = ["s1", "s2", "s3"];
    ids.forEach((id, i) => {
        const el = document.getElementById(id);
        const full = sugg[i];
        if (full && full.length) {
            el.style.display = "block";
            el.disabled = false;
            el.title = full;
            el.textContent = full;
        } else {
            el.textContent = "";
            el.title = "";
            el.style.display = "none";
        }
    });
    setTimeout(() => {
        const wrap = document.querySelector(".wrap");
        const neededHeight = wrap.scrollHeight + 40;
        window.electronAPI?.resizeWindow(neededHeight);
    }, 50);
}

async function askBackend(conv) {
    if (!conv || !conv.trim()) return "";
    const ask = await fetch(ASK_URL, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify([{role: "user", content: conv}])
    }).then(r => r.json());

    const tl = await fetch(TL_URL, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify([{role: "user", content: conv}])
    }).then(r => r.json());

    console.log("✅ Antwort /trafficLight:", tl);
    setDotColor(tl.response);
    renderSuggestions(makeSuggestionsFrom(ask.response));
    return ask.response;
}

async function sendUserText(text) {
    if (!text || !text.trim()) return;
    fullTranscript += `User: ${text}\n`;
    ["s1", "s2", "s3"].forEach(id => {
        const b = document.getElementById(id);
        b.disabled = true;
    });
    const resp = await askBackend(fullTranscript);
    fullTranscript += resp ? `Assistant: ${resp}\n` : "";
}

async function transcribeAndSend(blob) {
    const fd = new FormData();
    fd.append("file", blob, "recording.webm");
    const tr = await fetch(TR_URL, {method: "POST", body: fd}).then(r => r.json());
    if (tr && tr.text) await sendUserText(tr.text);
}

async function startRecording() {
    if (isStarting || recording) return;
    isStarting = true;
    const btn = document.getElementById("rec");
    try {
        streamRef = await navigator.mediaDevices.getUserMedia({audio: true});
        mediaRecorder = new MediaRecorder(streamRef);
        chunks = [];
        mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) chunks.push(e.data);
        };
        mediaRecorder.start();
        recording = true;
        btn.textContent = "⏹";
    } catch (e) {
        console.log("🎤 getUserMedia failed:", e);
        recording = false;
        btn.textContent = "⏺";
    } finally {
        isStarting = false;
    }
}

async function stopRecording() {
    if (!recording || !mediaRecorder) return;
    const btn = document.getElementById("rec");
    return new Promise(resolve => {
        const onStop = async () => {
            const blob = new Blob(chunks, {type: "audio/webm"});
            chunks = [];
            if (streamRef) {
                streamRef.getTracks().forEach(t => t.stop());
                streamRef = null;
            }
            await transcribeAndSend(blob);
            mediaRecorder = null;
            recording = false;
            btn.textContent = "⏺";
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
    if (!recording) {
        startRecording();
    } else {
        stopRecording();
    }
}

document.getElementById("s1").onclick = () => {
    const t = document.getElementById("s1").textContent;
    if (t) sendUserText(t);
};
document.getElementById("s2").onclick = () => {
    const t = document.getElementById("s2").textContent;
    if (t) sendUserText(t);
};
document.getElementById("s3").onclick = () => {
    const t = document.getElementById("s3").textContent;
    if (t) sendUserText(t);
};
document.getElementById("rec").onclick = () => toggleRecording();
document.getElementById("close").onclick = () => window.close();