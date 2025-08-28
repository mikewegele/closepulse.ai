import {state} from "../state.js";
import {MAX_AUDIO_SECONDS, TIMESLICE_MS} from "../../config.js";
import {transcribeAndSend} from "../backend/transcribe.js";

export async function startRecording() {
    if (state.isStarting || state.recording) return;
    state.isStarting = true;
    try {
        state.streamRef = await navigator.mediaDevices.getUserMedia({audio: true});
        state.mediaRecorder = new MediaRecorder(state.streamRef, {mimeType: 'audio/webm'});
        state.chunks = [];
        state.mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) state.chunks.push(e.data);
        };
        state.mediaRecorder.start(TIMESLICE_MS);
        state.recording = true;
    } catch (e) {
        console.log('getUserMedia failed:', e);
        state.recording = false;
    } finally {
        state.isStarting = false;
    }
}

export async function stopRecording() {
    if (!state.recording || !state.mediaRecorder) return;
    return new Promise(resolve => {
        const onStop = async () => {
            let size = 0, sel = [];
            for (let i = state.chunks.length - 1; i >= 0; i--) {
                size += state.chunks[i].size;
                sel.unshift(state.chunks[i]);
                if (size > 16000 * MAX_AUDIO_SECONDS) break;
            }
            const blob = new Blob(sel.length ? sel : state.chunks, {type: 'audio/webm'});
            state.chunks = [];
            if (state.streamRef) {
                state.streamRef.getTracks().forEach(t => t.stop());
                state.streamRef = null;
            }
            await transcribeAndSend(blob);
            state.mediaRecorder = null;
            state.recording = false;
            resolve();
        };
        if (state.mediaRecorder.state !== 'inactive') {
            state.mediaRecorder.addEventListener('stop', onStop, {once: true});
            state.mediaRecorder.stop();
        } else {
            onStop();
        }
    });
}

export function toggleRecording() {
    if (!state.recording) startRecording(); else stopRecording();
}