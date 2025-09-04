// renderer/audio/autostart_agentproc.js
import {log} from "../logger.js";

function arr(o, keys) {
    for (const k of keys) {
        const v = o?.[k];
        if (Array.isArray(v) && v.length) return v;
        if (Array.isArray(v?.list) && v.list.length) return v.list;
        if (Array.isArray(v?.devices) && v.devices.length) return v.devices;
    }
    if (Array.isArray(o)) return o;
    return [];
}

function pick(list, prefs = [], exclude = []) {
    const ex = s => exclude.some(r => r.test(s || ""));
    for (const r of prefs) {
        const f = list.find(s => r.test(s || "") && !ex(s || ""));
        if (f) return f;
    }
    const f = list.find(s => s && !ex(s));
    return f || list[0] || "";
}

export async function autoStartAgentProc({ws, ext, lang = 'de'}) {
    const plat = await window.electronAPI.getPlatform();
    const info = await window.electronAPI.agentList().catch(() => ({}));

    const inputs = arr(info, ["inputs", "input", "audio_in", "audioInputs", "mic", "mics", "devices_in"]);
    const outputs = arr(info, ["outputs", "output", "audio_out", "audioOutputs", "speakers", "devices_out"]);

    const rx = {
        loopbackMac: [/blackhole/i, /soundflower/i, /loopback/i],
        loopbackWin: [/stereo\s*mix/i, /vb[- ]?audio/i, /voice\s*meeter/i, /cable.*output/i, /what.?you.?hear/i],
        micMacGood: [/macbook.*mikro|macbook.*micro/i, /built[- ]?in.*mic/i, /internal.*mic/i, /jabra/i, /plantronics/i, /airpods/i, /bose/i, /shure/i, /rode/i, /yeti/i],
        micWinGood: [/microphone/i, /mikrofon/i, /headset.*mic/i, /usb.*mic/i, /jabra/i, /plantronics/i, /bose/i, /shure/i, /rode/i, /yeti/i],
        spkGood: [/headset/i, /jabra/i, /plantronics/i, /airpods/i, /bose/i, /sony|wh[- ]?\d{3,}/i, /speaker|lautsprecher/i],
    };

    const loopback = pick(
        inputs,
        plat === 'darwin' ? rx.loopbackMac : plat === 'win32' ? rx.loopbackWin : [],
        []
    );

    const mic = pick(
        inputs,
        plat === 'darwin' ? rx.micMacGood : rx.micWinGood,
        [...rx.loopbackMac, ...rx.loopbackWin]
    );

    const spk = pick(outputs, rx.spkGood, []);

    log(`devices mic="${mic}" loop="${loopback}" spk="${spk}" plat=${plat}`);

    const cfg = {ws, ext, lang};
    if (loopback) cfg.loopback = loopback;
    else if (mic) cfg.mic = mic;

    return window.electronAPI.agentStart(cfg);
}
