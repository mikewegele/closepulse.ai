// main.js (ESM)
import {app, BrowserWindow, ipcMain} from 'electron';
import {execFile, spawn} from 'child_process';
import path from 'path';
import {fileURLToPath} from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
    app.quit();
    process.exit(0);
} else {
    app.on('second-instance', () => {
        const win = BrowserWindow.getAllWindows()[0];
        if (win) {
            if (win.isMinimized()) win.restore();
            win.focus();
        }
    });
}

let agentProc = null;
let agentStarting = true;

function createWindow() {
    const win = new BrowserWindow({
        width: 360,
        height: 500,
        frame: false,
        transparent: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.cjs'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    win.loadFile('index.html');
}

function resolveAgentCommand() {
    if (!app.isPackaged) {
        return {
            cmd: process.env.PYTHON || 'python3',
            args: [path.join(__dirname, 'closepulse_agent.py')],
        };
    }
    const bin =
        process.platform === 'win32'
            ? path.join(process.resourcesPath, 'closepulse_agent_win.exe')
            : path.join(process.resourcesPath, 'closepulse_agent_mac');
    return {cmd: bin, args: []};
}

function killProcessTree(p) {
    if (!p || !p.pid) return;
    try {
        if (process.platform !== 'win32') {
            try {
                process.kill(-p.pid, 'SIGTERM');
            } catch {
            }
            setTimeout(() => {
                try {
                    process.kill(-p.pid, 'SIGKILL');
                } catch {
                }
            }, 800);
        } else {
            try {
                p.kill('SIGTERM');
            } catch {
            }
            setTimeout(() => {
                try {
                    p.kill('SIGKILL');
                } catch {
                }
            }, 800);
        }
    } catch {
    }
}

async function runOsascript(lines) {
    return new Promise((resolve, reject) => {
        execFile('/usr/bin/osascript', ['-e', ...lines], (err, stdout, stderr) => {
            if (err) return reject(err);
            resolve((stdout || '').toString().trim());
        });
    });
}

async function tryCreateMultiViaAppleScript(builtinName) {
    try {
        // Öffnet Audio-MIDI-Setup, klickt Multi-Output, hakt BlackHole + Built-in an, benennt um, setzt Default
        await runOsascript([
            `tell application "Audio MIDI Setup" to activate`,
            `delay 0.6`,
            `tell application "System Events"`,
            `tell process "Audio MIDI Setup"`,
            // Seitenleiste: + Button -> Multi-Output-Gerät erstellen
            `click menu item "Multi-Output Device" of menu 1 of button 1 of window 1`,
            `delay 0.4`,
            // Umbenennen auf "MultiOutput CP"
            `set value of text field 1 of group 1 of window 1 to "MultiOutput CP"`,
            `delay 0.2`,
            // Häkchen setzen (BlackHole + Built-in)
            `-- Achtung: UI-Struktur variiert je nach macOS. Ggf. anpassen.`,
            `end tell`,
            `end tell`,
            `delay 0.3`,
            // Standard-Ausgabe setzen (geht auch über Tastaturkürzel; notfalls manuell)
        ]);
        console.log('[audioctl] AppleScript-Fallback versucht.');
    } catch (e) {
        console.warn('[audioctl] AppleScript-Fallback fehlgeschlagen', e.message || e);
    }
}


async function runAudioctl(args = []) {
    const bin = app.isPackaged
        ? path.join(process.resourcesPath, 'audioctl')
        : path.join(__dirname, '..', 'native', 'audioctl', '.build', 'release', 'audioctl');

    return new Promise((resolve, reject) => {
        const p = spawn(bin, args, {stdio: ['ignore', 'pipe', 'pipe']});
        let out = '', err = '';
        p.stdout.on('data', d => out += d.toString());
        p.stderr.on('data', d => err += d.toString());
        p.on('exit', c => c === 0 ? resolve(out.trim()) : reject(new Error(err || `exit ${c}\n${out}`)));
    });
}

// einfache Helper
async function listAudioNames() {
    try {
        const out = await runAudioctl(['list']); // audioctl list -> eine Zeile pro Device-Name
        return out.split('\n').map(s => s.trim()).filter(Boolean);
    } catch (e) {
        console.error('[audioctl:list] failed', e.message || e);
        return [];
    }
}

function guessBuiltin(names) {
    const rx = [
        /macbook.*lautsprecher/i,
        /^lautsprecher$/i,
        /built[- ]?in.*output/i,
        /internal.*speaker/i
    ];
    return names.find(n => rx.some(r => r.test(n))) || 'MacBook Pro-Lautsprecher';
}

async function ensureAudioSetup() {
    try {
        const names = await listAudioNames();
        const bh = names.find(n => /blackhole.*2ch/i.test(n));
        if (!bh) {
            console.warn('[audioctl] BlackHole nicht gefunden – Installer/MDM nötig. Überspringe Setup.');
            return;
        }
        const builtin = guessBuiltin(names);

        // 1) Anlegen (idempotent) + Default setzen
        const ensureOut = await runAudioctl([
            'ensure',
            '--title', 'MultiOutput CP',
            '--bh', 'BlackHole 2ch',
            '--builtin', builtin
            // audioctl ensure setzt default automatisch, wenn nicht --no-default
        ]);
        console.log('[audioctl:ensure]', ensureOut);

        // 2) Verifizieren
        const after = await listAudioNames();
        const haveMulti = after.some(n => n === 'MultiOutput CP');
        if (!haveMulti) {
            console.warn('[audioctl] MultiOutput CP wurde nicht angelegt (dein audioctl erzeugt evtl. noch nichts). Fallback versuche ich gleich.');
            await tryCreateMultiViaAppleScript(builtin); // nur als temporärer Fallback, s.u.
        }
    } catch (e) {
        console.error('[audioctl] ensureAudioSetup failed', e.message || e);
    }
}

async function startAgent({ws, ext, mic, spk, loopback, lang}) {
    if (agentProc || agentStarting) return true;
    agentStarting = true;
    try {
        if (loopback) mic = undefined;
        const {cmd, args} = resolveAgentCommand();
        const full = [...args, '--ws', ws, '--ext', ext];
        if (mic) full.push('--mic', mic);
        if (loopback) full.push('--loopback', loopback);
        if (lang) full.push('--lang', lang);
        const env = {...process.env};
        agentProc = spawn(cmd, full, {
            stdio: ['ignore', 'pipe', 'pipe'],
            env,
            detached: process.platform !== 'win32',
        });
        agentProc.stdout.on('data', (d) => console.log('[agent]', d.toString().trim()));
        agentProc.stderr.on('data', (d) => console.error('[agent-err]', d.toString().trim()));
        agentProc.once('error', (err) => {
            console.error('[agent] spawn error', err);
        });
        agentProc.once('exit', (code, sig) => {
            console.log(`agent exited code=${code} sig=${sig}`);
            agentProc = null;
        });
        return true;
    } finally {
        agentStarting = false;
    }
}

function stopAgent() {
    if (!agentProc) return true;
    const p = agentProc;
    agentProc = null;
    return new Promise((resolve) => {
        let resolved = false;
        const done = () => {
            if (!resolved) {
                resolved = true;
                resolve(true);
            }
        };
        p.once('exit', done);
        killProcessTree(p);
        setTimeout(done, 1500);
    });
}

function listDevices() {
    return new Promise((resolve, reject) => {
        const {cmd, args} = resolveAgentCommand();
        const child = spawn(cmd, [...args, '--list-devices'], {env: {...process.env}});
        let out = '', err = '';
        child.stdout.on('data', (d) => (out += d.toString()));
        child.stderr.on('data', (d) => (err += d.toString()));
        child.on('exit', () => {
            if (err) console.error('[agent-list-err]', err.trim());
            try {
                resolve(JSON.parse(out || '{}'));
            } catch (e) {
                reject(e);
            }
        });
    });
}

function agentStatus() {
    return !!agentProc;
}

ipcMain.on('log', (_event, msg) => console.log('[Renderer]', msg));
ipcMain.on('resize-window', (event, height) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win && Number.isFinite(height)) {
        const [w] = win.getSize();
        win.setSize(w, Math.ceil(height));
    }
});
ipcMain.handle('agent:start', async (_e, cfg) => {
    console.log('[E] agent:start', cfg);
    if (agentProc || agentStarting) return true;
    return startAgent(cfg);
});
ipcMain.handle('agent:stop', async () => {
    console.log('[E] agent:stop');
    return stopAgent();
});
ipcMain.handle('agent:list', async () => {
    console.log('[E] agent:list');
    return listDevices();
});
ipcMain.handle('agent:status', async () => agentStatus());
ipcMain.handle('env:platform', async () => process.platform);

function setupSignalHandlers() {
    const shutdown = async () => {
        try {
            await stopAgent();
        } catch {
        }
        process.exit(0);
    };
    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
    process.on('uncaughtException', (e) => {
        console.error('[main] uncaught', e);
        shutdown();
    });
    process.on('exit', () => {
        try {
            stopAgent();
        } catch {
        }
    });
}

app.whenReady().then(async () => {
    setupSignalHandlers();
    await ensureAudioSetup();
    createWindow();
});

app.on('window-all-closed', () => {
    try {
        stopAgent();
    } catch {
    }
    if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on('before-quit', () => {
    try {
        stopAgent();
    } catch {
    }
});
app.on('will-quit', () => {
    try {
        stopAgent();
    } catch {
    }
});
