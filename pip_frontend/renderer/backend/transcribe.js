import {TR_URL} from "../config.js";
import {safeJson} from "../utils.js";
import {renderLatency} from "../ui/latency.js";
import {sendUserText} from "./api.js";

export async function transcribeAndSend(blob) {
    const fd = new FormData();
    fd.append('file', blob, 'recording.webm');
    const t0 = performance.now();
    try {
        const tr = await fetch(TR_URL, {method: 'POST', body: fd}).then(safeJson);
        const total = (performance.now() - t0) / 1000;
        renderLatency({phase: 'Transkription', total, transcribe: tr?.duration ?? null});
        if (tr && tr.text) await sendUserText(tr.text);
    } catch (e) {
        const total = (performance.now() - t0) / 1000;
        renderLatency({phase: 'Transkription fehlgeschlagen', total});
        console.log('/transcribe failed:', e?.message || e);
    }
}