// renderer/audio/autostart_agentproc.js
import {log} from "../logger.js";

export async function autoStartAgentProc({ws, ext, lang = 'de'}) {
    const plat = await window.electronAPI.getPlatform();
    const info = await window.electronAPI.agentList();

    const arr = (o, keys) => {
        for (const k of keys) {
            const v = o?.[k];
            if (Array.isArray(v) && v.length) return v;
            if (Array.isArray(v?.list) && v.list.length) return v.list;
            if (Array.isArray(v?.devices) && v.devices.length) return v.devices;
        }
        if (Array.isArray(o)) return o;
        return [];
    };

    const inputs = arr(info, ["inputs", "input", "audio_in", "audioInputs", "mic", "mics", "devices_in"]);
    const outputs = arr(info, ["outputs", "output", "audio_out", "audioOutputs", "speakers", "devices_out"]);

    const rx = {
        loopback: [/blackhole/i, /stereo mix/i, /vb[- ]?cable/i, /monitor/i],
        micGood: [/headset/i, /jabra/i, /plantronics/i, /airpods/i, /bose/i, /shure/i, /rode/i, /yeti/i, /built[- ]?in/i, /macbook.*microphone/i],
        spkGood: [/headset/i, /jabra/i, /plantronics/i, /airpods/i, /bose/i, /sony|wh[- ]?\d{3,}/i, /speaker/i],
    };

    const pick = (list, prefs = [], exclude = []) => {
        const ex = s => exclude.some(r => r.test(s || ""));
        for (const r of prefs) {
            const f = list.find(s => r.test(s || "") && !ex(s || ""));
            if (f) return f;
        }
        const f = list.find(s => s && !ex(s));
        return f || list[0] || "";
    };

    const loopback = inputs.find(s => rx.loopback.some(r => r.test(s || ""))) || "";
    const mic = pick(inputs, rx.micGood, rx.loopback);
    const spk = pick(outputs, rx.spkGood, []); // wird unten eh nicht gesendet

    log(`devices mic="${mic}" loop="${loopback}" spk="${spk}" plat=${plat}`);

    const cfg = {ws, ext, lang};
    if (loopback) {
        cfg.loopback = loopback;
    } else if (mic) {
        cfg.mic = mic;
    }

    // spk im STT-only nicht nötig
    await window.electronAPI.agentStart(cfg);
}
