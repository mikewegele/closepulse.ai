import {TR_URL} from "../config.js";
import {safeJson} from "../utils.js";
import {sendUserText} from "./api.js";

export async function transcribeAndSend(blob) {
    const fd = new FormData();
    fd.append('file', blob, 'recording.webm');
    try {
        const tr = await fetch(TR_URL, {method: 'POST', body: fd}).then(safeJson);
        if (tr && tr.text) await sendUserText(tr.text);
    } catch (e) {
        console.log('/transcribe failed:', e?.message || e);
    }
}