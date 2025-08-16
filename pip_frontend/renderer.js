import {Inviter, Registerer, SessionState, UserAgent} from "./vendor/sip.js/lib/index.js"; // <— relativer Pfad, bleibt 'self'

/* ========= KONFIG ========= */
const SIP_WSS = "wss://ws.nexmo.com";
const SIP_DOMAIN = "mike-wegele.sip-eu.vonage.com";
const SIP_USER = "mike-wegele";
const SIP_PASS = "4hA=39ptg!u6F1WnevVu";
const SIP_URI_STRING = `sip:${SIP_USER}@${SIP_DOMAIN}`;
const SIP_URI = UserAgent.makeURI(SIP_URI_STRING);
if (!SIP_URI) {
    throw new Error(`Ungültige SIP-URI: ${SIP_URI_STRING}`);
}
const ASK_URL = "http://localhost:8000/ask";
const TL_URL = "http://localhost:8000/trafficLight";
const TR_URL = "http://localhost:8000/transcribe";
const CUSTOMER_URL = "http://localhost:8000/customer?phone=";
/* ========================== */

/* ---- Logging: Renderer -> Main (Terminal) ---- */
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

const __origLog = console.log.bind(console);
console.log = (...args) => {
    __origLog(...args);
    forwardLog(...args);
};

/* ---- UI: fehlende Elemente dynamisch nachrüsten ---- */
function ensureEl(tag, id, attrs = {}, parent = document.body) {
    let el = document.getElementById(id);
    if (!el) {
        el = document.createElement(tag);
        el.id = id;
        Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
        parent.appendChild(el);
    }
    return el;
}

const wrap = document.querySelector(".wrap") || document.body;
const uiRow = document.querySelector(".row") || wrap;
const dial = ensureEl("input", "dial", {placeholder: "+4930..."}, wrap);
const callBtn = ensureEl("button", "call", {}, wrap);
const hangBtn = ensureEl("button", "hangup", {}, wrap);
const audioEl = ensureEl("audio", "remoteAudio", {autoplay: "true"}, wrap);
const popDiv = ensureEl("div", "screenpop", {}, wrap);
callBtn.textContent = "📞";
hangBtn.textContent = "🛑";

/* ---- Bestehende Buttons aus deinem HTML ---- */
const dot = document.getElementById("dot");
const s1 = document.getElementById("s1");
const s2 = document.getElementById("s2");
const s3 = document.getElementById("s3");
const recBt = document.getElementById("rec");
const closeBt = document.getElementById("close");

/* ---- Statusdot ---- */
function setDotColor(jsonStr) {
    try {
        const trafficLightColor = JSON.parse(jsonStr).response;
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
    } catch {
        dot.style.color = "#d9d9d9";
        dot.style.background = "rgba(217,217,217,0.6)";
    }
}

function statusSet(value) {
    setDotColor(JSON.stringify({response: value}));
}

/* ---- Suggestions ---- */
function makeSuggestionsFrom(text) {
    if (!text) return [];
    if (Array.isArray(text)) return text.slice(0, 3).map(s => String(s).trim()).filter(Boolean);
    try {
        const first = text.indexOf('['), last = text.lastIndexOf(']');
        if (first !== -1 && last !== -1 && last > first) {
            const arr = JSON.parse(text.slice(first, last + 1));
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
    const ids = ["s1", "s2", "s3"];
    ids.forEach((id, i) => {
        const el = document.getElementById(id);
        const full = sugg[i];
        if (full && full.length) {
            el.style.display = "inline-block";
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
        const wrap = document.querySelector(".wrap") || document.body;
        const neededHeight = wrap.scrollHeight + 40;
        window.electronAPI?.resizeWindow?.(neededHeight);
    }, 50);
}

/* ---- Backend Calls ---- */
let fullTranscript = "";

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
    statusSet(tl.response);                // dot aktualisieren
    renderSuggestions(makeSuggestionsFrom(ask.response));
    return ask.response;
}

async function sendUserText(text) {
    if (!text || !text.trim()) return;
    fullTranscript += `User: ${text}\n`;
    ["s1", "s2", "s3"].forEach(id => {
        const b = document.getElementById(id);
        if (b) b.disabled = true;
    });
    const resp = await askBackend(fullTranscript);
    fullTranscript += resp ? `Assistant: ${resp}\n` : "";
}

/* ---- Audio Aufnahme (für Nachbearbeitung) ---- */
let mediaRecorder = null, chunks = [], recording = false, streamRef = null, isStarting = false;

async function transcribeAndSend(blob) {
    const fd = new FormData();
    fd.append("file", blob, "recording.webm");
    const tr = await fetch(TR_URL, {method: "POST", body: fd}).then(r => r.json());
    if (tr && tr.text) await sendUserText(tr.text);
}

async function startRecording() {
    if (isStarting || recording) return;
    isStarting = true;
    try {
        streamRef = await navigator.mediaDevices.getUserMedia({audio: true});
        mediaRecorder = new MediaRecorder(streamRef);
        chunks = [];
        mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) chunks.push(e.data);
        };
        mediaRecorder.start();
        recording = true;
        if (recBt) recBt.textContent = "⏹";
    } catch (e) {
        console.log("🎤 getUserMedia failed:", e);
        recording = false;
        if (recBt) recBt.textContent = "⏺";
    } finally {
        isStarting = false;
    }
}

async function stopRecording() {
    if (!recording || !mediaRecorder) return;
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
            if (recBt) recBt.textContent = "⏺";
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

/* ---- Events deiner vorhandenen Buttons ---- */
if (s1) s1.onclick = () => {
    const t = s1.textContent;
    if (t) sendUserText(t);
};
if (s2) s2.onclick = () => {
    const t = s2.textContent;
    if (t) sendUserText(t);
};
if (s3) s3.onclick = () => {
    const t = s3.textContent;
    if (t) sendUserText(t);
};
if (recBt) recBt.onclick = () => toggleRecording();
if (closeBt) closeBt.onclick = () => window.close();

/* ======================
   SIP.js + Call Handling
   ====================== */
let ua = null, registerer = null, currentSession = null, pc = null;
let callIdSeq = 0;
let callMetrics = null;

function newCallId() {
    callIdSeq += 1;
    return `call-${Date.now()}-${callIdSeq}`;
}

function logEvent(ev, payload) {
    forwardLog(JSON.stringify({ev, ...payload}));
}

async function screenPop(number) {
    try {
        const r = await fetch(CUSTOMER_URL + encodeURIComponent(number));
        const data = r.ok ? await r.json() : {name: "Unbekannt", phone: number};
        popDiv.textContent = `${data.name || "Unbekannt"} • ${data.phone || number}`;
    } catch {
        popDiv.textContent = number;
    }
}

async function createPeerConnection() {
    if (pc) pc.close();
    pc = new RTCPeerConnection();
    pc.ontrack = (e) => {
        if (e.streams && e.streams[0]) audioEl.srcObject = e.streams[0];
    };
    const local = await navigator.mediaDevices.getUserMedia({audio: true});
    local.getTracks().forEach(t => pc.addTrack(t, local));
    return pc;
}

/* Call-Recording: mix local+remote → STT → LLM */
let callRecorder = null, callChunks = [];

function startCallRecorder(localStream, remoteStream) {
    const mix = new MediaStream();
    localStream.getAudioTracks().forEach(t => mix.addTrack(t));
    remoteStream.getAudioTracks().forEach(t => mix.addTrack(t));
    callChunks = [];
    callRecorder = new MediaRecorder(mix);
    callRecorder.ondataavailable = e => {
        if (e.data.size > 0) callChunks.push(e.data);
    };
    callRecorder.start();
}

async function stopCallRecorderAndProcess() {
    if (!callRecorder) return;
    await new Promise(res => {
        callRecorder.addEventListener("stop", res, {once: true});
        callRecorder.stop();
    });
    const blob = new Blob(callChunks, {type: "audio/webm"});
    callChunks = [];
    await transcribeAndSend(blob);
}

async function handleIncoming(invitation, callId) {
    const local = await navigator.mediaDevices.getUserMedia({audio: true});
    pc = await createPeerConnection();
    currentSession = invitation;
    statusSet("ringing");
    await invitation.accept({sessionDescriptionHandlerOptions: {constraints: {audio: true, video: false}}});
    invitation.stateChange.addListener(async (state) => {
        if (state === SessionState.Established) {
            callMetrics.answered = Date.now();
            statusSet("in_call");
            const remote = audioEl.srcObject || new MediaStream();
            startCallRecorder(local, remote);
            const fromNum = invitation.remoteIdentity.uri.user || "";
            await screenPop(fromNum);
            logEvent("call.established", {callId, from: fromNum});
        }
        if (state === SessionState.Terminated) {
            callMetrics.ended = Date.now();
            callMetrics.ringMs = (callMetrics.answered || callMetrics.ended) - callMetrics.start;
            callMetrics.talkMs = callMetrics.answered ? callMetrics.ended - callMetrics.answered : 0;
            logEvent("call.terminated", callMetrics);
            await stopCallRecorderAndProcess();
            currentSession = null;
            if (pc) {
                pc.close();
                pc = null;
            }
            statusSet("after_call_work");
            setTimeout(() => statusSet("green"), 8000);
        }
    });
}

async function outboundDial(e164) {
    const callId = newCallId();
    callMetrics = {callId, direction: "outbound", start: Date.now(), to: e164};
    const targetString = `sip:${e164}@${SIP_DOMAIN}`;
    const target = UserAgent.makeURI(targetString);
    if (!target) {
        console.log("❌ Ungültiges Ziel:", targetString);
        return;
    }
    const inviter = new Inviter(ua, target);
    pc = await createPeerConnection();
    currentSession = inviter;
    logEvent("call.dial", {callId, to: e164});
    statusSet("yellow");
    await inviter.invite();
    inviter.stateChange.addListener(async (state) => {
        if (state === SessionState.Established) {
            callMetrics.answered = Date.now();
            statusSet("in_call");
            const local = await navigator.mediaDevices.getUserMedia({audio: true});
            const remote = audioEl.srcObject || new MediaStream();
            startCallRecorder(local, remote);
            await screenPop(e164);
            logEvent("call.established", {callId, to: e164});
        }
        if (state === SessionState.Terminated) {
            callMetrics.ended = Date.now();
            callMetrics.ringMs = (callMetrics.answered || callMetrics.ended) - callMetrics.start;
            callMetrics.talkMs = callMetrics.answered ? callMetrics.ended - callMetrics.answered : 0;
            logEvent("call.terminated", callMetrics);
            await stopCallRecorderAndProcess();
            currentSession = null;
            if (pc) {
                pc.close();
                pc = null;
            }
            statusSet("after_call_work");
            setTimeout(() => statusSet("green"), 8000);
        }
    });
}

function hangup() {
    if (!currentSession) return;
    try {
        currentSession.terminate();
    } catch {
    }
}

/* SIP UA starten */
async function startUA() {
    ua = new UserAgent({
        uri: SIP_URI,
        transportOptions: {server: SIP_WSS},
        authorizationUsername: SIP_USER,
        authorizationPassword: SIP_PASS
    });
    registerer = new Registerer(ua);
    ua.delegate = {
        onInvite: async (invitation) => {
            const callId = newCallId();
            callMetrics = {callId, direction: "inbound", start: Date.now()};
            logEvent("call.ringing", {callId, from: invitation.remoteIdentity.uri.user});
            await handleIncoming(invitation, callId);
        }
    };
    await ua.start();
    await registerer.register();
    statusSet("green");
    console.log("✅ SIP registered");
}

startUA();

/* UI Handlers */
callBtn.onclick = async () => {
    const num = (dial.value || "").trim();
    if (num) await outboundDial(num);
};
hangBtn.onclick = () => hangup();
