import {execFile} from 'child_process';
import fs from 'fs';

function systemProfilerAudio() {
    return new Promise((resolve) => {
        execFile('/usr/sbin/system_profiler', ['SPAudioDataType'], {timeout: 5000}, (_e, out) => resolve((out || '').toString()));
    });
}

async function deviceExists(name) {
    const text = await systemProfilerAudio();
    const rx = new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
    return rx.test(text);
}

function switchOutputTo(name) {
    return new Promise((resolve) => {
        const bins = ['/opt/homebrew/bin/SwitchAudioSource', '/usr/local/bin/SwitchAudioSource'];
        const bin = bins.find(b => {
            try {
                return fs.existsSync(b);
            } catch {
                return false;
            }
        });
        if (!bin) return resolve(false);
        execFile(bin, ['-s', name], (err) => resolve(!err));
    });
}

async function guessBuiltinOutputName() {
    const text = await systemProfilerAudio();
    const candidates = ['MacBook Pro-Lautsprecher', 'MacBook-Lautsprecher', 'Lautsprecher', 'Built-in Output', 'Internal Speakers'];
    return candidates.find(c => text.includes(c)) || 'MacBook Pro-Lautsprecher';
}

export async function ensureAudioSetupMac() {
    const text = await systemProfilerAudio();
    const hasBH = /BlackHole\s*2ch/i.test(text);
    if (!hasBH) return;
    const haveMulti = await deviceExists('CP MultiOutput');
    if (haveMulti) {
        const ok = await switchOutputTo('CP MultiOutput');
        return ok;
    }
    const builtin = await guessBuiltinOutputName();
    const ok = await switchOutputTo(builtin);
    return ok;
}
