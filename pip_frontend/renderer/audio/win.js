import {execFile} from 'child_process';
import fs from 'fs';
import path from 'path';

function firstExisting(paths) {
    for (const p of paths) {
        try {
            if (fs.existsSync(p)) return p;
        } catch {
        }
    }
    return null;
}

function switchOutputToWindows(name) {
    return new Promise((resolve) => {
        const svv = firstExisting([
            path.join(process.resourcesPath || '', 'SoundVolumeView.exe'),
            'C:\\Program Files\\NirSoft\\SoundVolumeView\\SoundVolumeView.exe',
            'C:\\Program Files (x86)\\NirSoft\\SoundVolumeView\\SoundVolumeView.exe',
        ]);
        if (svv) {
            return execFile(svv, ['/SetDefault', name, 'all'], {windowsHide: true}, (err) => resolve(!err));
        }
        const nircmd = firstExisting([
            path.join(process.resourcesPath || '', 'nircmd.exe'),
            'C:\\Windows\\nircmd.exe',
            'C:\\Windows\\System32\\nircmd.exe',
        ]);
        if (nircmd) {
            return execFile(nircmd, ['setdefaultsounddevice', name, '1'], {windowsHide: true}, (err) => resolve(!err));
        }
        resolve(false);
    });
}

function guessBuiltinOutputNameWindows() {
    const common = ['Speakers', 'Lautsprecher', 'Headphones', 'Headset', 'Speakers (High Definition Audio Device)'];
    return common[0];
}

export async function ensureAudioSetupWin() {
    const target = 'CP MultiOutput';
    const ok = await switchOutputToWindows(target);
    if (ok) return true;
    const fb = guessBuiltinOutputNameWindows();
    const ok2 = await switchOutputToWindows(fb);
    return !!ok2;
}
