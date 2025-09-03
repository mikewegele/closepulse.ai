// renderer/audio/pipeline.js
function pickByLabel(devices, kind, label) {
    const list = devices.filter(d => d.kind === kind);
    if (!list.length) throw new Error(`No devices of kind ${kind}`);
    if (!label) return list[0];
    const low = label.toLowerCase();
    return list.find(d => (d.label || '').toLowerCase() === low)
        || list.find(d => (d.label || '').includes(label))
        || list[0];
}

function recToWS(stream, url) {
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    let rec = null;

    ws.addEventListener("open", () => {
        rec = new MediaRecorder(stream, {mimeType: "audio/webm;codecs=opus", bitsPerSecond: 64000});
        rec.ondataavailable = e => e.data.arrayBuffer().then(b => ws.readyState === 1 && ws.send(b));
        rec.start(250); // ~250ms Chunks
    });
    ws.addEventListener("close", () => {
        try {
            rec && rec.state !== "inactive" && rec.stop();
        } catch {
        }
    });
    ws.addEventListener("error", () => {
        try {
            rec && rec.state !== "inactive" && rec.stop();
        } catch {
        }
    });

    return ws;
}

export async function startPipelines({ext, wsBase, micLabel, loopbackLabel, onStatus, onSuggestions}) {
    // Permission holen, sonst sind device labels leer
    const perm = await navigator.mediaDevices.getUserMedia({audio: true});
    const devices = await navigator.mediaDevices.enumerateDevices();
    perm.getTracks().forEach(t => t.stop());

    const mic = pickByLabel(devices, "audioinput", micLabel);
    const loop = pickByLabel(devices, "audioinput", loopbackLabel);

    const micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
            deviceId: mic?.deviceId ? {exact: mic.deviceId} : undefined,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
            channelCount: 1,
            sampleRate: 48000
        }
    });

    const custStream = await navigator.mediaDevices.getUserMedia({
        audio: {
            deviceId: loop?.deviceId ? {exact: loop.deviceId} : undefined,
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false,
            channelCount: 1,
            sampleRate: 48000
        }
    });

    const wsA = recToWS(micStream, `${wsBase}/ws/stt/agent?ext=${encodeURIComponent(ext)}`);
    const wsC = recToWS(custStream, `${wsBase}/ws/stt/customer?ext=${encodeURIComponent(ext)}`);

    const wsS = new WebSocket(`${wsBase}/ws/suggest?ext=${encodeURIComponent(ext)}`);
    wsS.onmessage = (e) => {
        try {
            const {s1, s2, s3} = JSON.parse(e.data);
            onSuggestions && onSuggestions({s1, s2, s3});
        } catch {
        }
    };

    const check = () => onStatus && onStatus(wsA.readyState === 1 && wsC.readyState === 1 && wsS.readyState === 1);
    const iv = setInterval(check, 800);
    [wsA, wsC, wsS].forEach(w => w.addEventListener("close", () => clearInterval(iv)));
    setTimeout(check, 1200);
}
