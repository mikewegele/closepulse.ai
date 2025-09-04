import {ensureAudioSetupMac} from './mac.js';
import {ensureAudioSetupWin} from './win.js';

export async function ensureAudioSetup() {
    if (process.platform === 'darwin') {
        try {
            await ensureAudioSetupMac();
        } catch {
        }
        return;
    }
    if (process.platform === 'win32') {
        try {
            await ensureAudioSetupWin();
        } catch {
        }
        return;
    }
}
