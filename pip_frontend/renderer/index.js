// renderer/index.js
import {el} from "./state.js";
import {initTheme} from "./ui/theme.js";
import {initToolbar} from "./ui/toolbar.js";
import {initLatency} from "./ui/latency.js";
import {sendUserText} from "./backend/api.js";
import {toggleRecording} from "./audio/recorder.js";

// Init UI
initTheme();
initToolbar();
initLatency();

// Wire suggestion buttons (keine else-if-Kette)
if (el.s1) {
    el.s1.onclick = () => {
        const t = (el.s1.textContent || "").trim();
        if (t) sendUserText(t);
    };
}
if (el.s2) {
    el.s2.onclick = () => {
        const t = (el.s2.textContent || "").trim();
        if (t) sendUserText(t);
    };
}
if (el.s3) {
    el.s3.onclick = () => {
        const t = (el.s3.textContent || "").trim();
        if (t) sendUserText(t);
    };
}

// Recorder + Close
if (el.rec) el.rec.onclick = () => toggleRecording();
if (el.close) el.close.onclick = () => window.close();
