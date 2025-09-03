// renderer/audio/autostart.js
function pick(devices, kind, prefs = [], exclude = []) {
    const list = devices.filter(d => d.kind === kind);
    const ex = (label) => exclude.some(rx => rx.test(label));
    for (const rx of prefs) {
        const f = list.find(d => d.label && rx.test(d.label) && !ex(d.label));
        if (f) return f;
    }
    const f = list.find(d => d.label && !ex(d.label));
    return f || list[0];
}

async function getDevicesWithPermission() {
    const s = await navigator.mediaDevices.getUserMedia({audio: true});
    const devices = await navigator.mediaDevices.enumerateDevices();
    s.getTracks().forEach(t => t.stop());
    return devices;
}

export async function autoStartAgent({ws, ext}) {
    const plat = await window.electronAPI.getPlatform();
    const devices = await getDevicesWithPermission();

    const loopbackHints = plat === 'darwin'
        ? [/blackhole/i]
        : plat === 'win32'
            ? [/stereo mix/i, /vb[- ]?cable/i]
            : [/monitor/i, /pipewire/i, /pulse/i];

    const excludeLoopback = [/blackhole/i, /stereo mix/i, /vb[- ]?cable/i, /monitor/i];

    const micPrefs = [/headset/i, /jabra/i, /plantronics/i, /airpods/i, /bose/i, /shure/i, /yeti/i, /rode/i, /macbook.*microphone/i, /built[- ]?in/i];
    const spkPrefs = [/headset/i, /jabra/i, /plantronics/i, /airpods/i, /bose/i, /sony|wh[- ]?\d{3,}/i, /speaker/i];

    const mic = pick(devices, 'audioinput', micPrefs, excludeLoopback);
    const spk = pick(devices, 'audiooutput', spkPrefs, []);
    const loopback = devices.find(d => d.kind === 'audioinput' && loopbackHints.some(rx => rx.test(d.label || '')));

    const args = {ws, ext};
    if (mic?.label) args.mic = mic.label;
    if (spk?.label) args.spk = spk.label;
    if (loopback?.label) args.loopback = loopback.label;

    await window.electronAPI.agentStart(args);
}
