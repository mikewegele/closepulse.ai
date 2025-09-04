// main.js (ESM)
import {app, BrowserWindow, ipcMain} from 'electron';
import {execFile, spawn} from 'child_process';
import path from 'path';
import {fileURLToPath} from 'url';
import fs from 'fs';

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
let agentStarting = false;
let quitting = false;
let stoppingPromise = null;

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

    if (process.platform === 'win32') {
        const {spawn} = require('child_process');
        try {
            spawn('taskkill', ['/PID', String(p.pid), '/T', '/F'], {stdio: 'ignore'}).on('exit', () => {
            });
        } catch {
        }
    } else {
        try {
            process.kill(-p.pid, 'SIGTERM');
        } catch {
        }
        setTimeout(() => {
            try {
                process.kill(-p.pid, 'SIGKILL');
            } catch {
            }
        }, 1000);
    }
}

/* ---------- Audio: leises Umschalten ohne AppleScript ---------- */

function systemProfilerAudio() {
    return new Promise((resolve) => {
        execFile('/usr/sbin/system_profiler', ['SPAudioDataType'], {timeout: 5000}, (_e, out) => {
            resolve((out || '').toString());
        });
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
        const bin = bins.find(b => fs.existsSync(b));
        if (!bin) return resolve(false);
        execFile(bin, ['-s', name], (err) => resolve(!err));
    });
}

async function guessBuiltinOutputName() {
    const text = await systemProfilerAudio();
    const candidates = ['MacBook Pro-Lautsprecher', 'MacBook-Lautsprecher', 'Lautsprecher', 'Built-in Output', 'Internal Speakers'];
    return candidates.find(c => text.includes(c)) || 'MacBook Pro-Lautsprecher';
}

async function ensureAudioSetup() {
    if (process.platform !== 'darwin') return;

    const hasBH = /BlackHole\s*2ch/i.test(await systemProfilerAudio());
    if (!hasBH) {
        console.warn('[audio-setup] BlackHole 2ch nicht gefunden – Überspringe Umschalten.');
        return;
    }

    const haveMulti = await deviceExists('CP MultiOutput');
    if (haveMulti) {
        const ok = await switchOutputTo('CP MultiOutput');
        if (ok) console.log('[audio-setup] Ausgabe: CP MultiOutput');
        else console.warn('[audio-setup] SwitchAudioSource nicht gefunden – installiere: brew install switchaudio-osx');
        return;
    }

    const builtin = await guessBuiltinOutputName();
    const ok = await switchOutputTo(builtin);
    if (ok) console.log(`[audio-setup] Ausgabe: ${builtin} (CP MultiOutput fehlt)`);
    else console.warn('[audio-setup] SwitchAudioSource nicht gefunden – installiere: brew install switchaudio-osx');
}

/* -------------------------------------------------------------- */

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

        const env = {...process.env, PYTHONUNBUFFERED: '1'};

        agentProc = spawn(cmd, full, {
            stdio: ['ignore', 'pipe', 'pipe'],
            env,
            detached: process.platform !== 'win32',
            windowsHide: true,
        });

        agentProc.stdout.on('data', (d) => console.log('[agent]', d.toString().trim()));
        agentProc.stderr.on('data', (d) => console.error('[agent-err]', d.toString().trim()));
        agentProc.once('error', (err) => console.error('[agent] spawn error', err));
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
    if (!agentProc) return Promise.resolve(true);
    const p = agentProc;
    agentProc = null;

    return new Promise((resolve) => {
        let done = false;
        const finish = () => {
            if (!done) {
                done = true;
                resolve(true);
            }
        };

        p.once('exit', finish);
        p.once('close', finish);

        try {
            p.stdout?.removeAllListeners();
            p.stderr?.removeAllListeners();
        } catch {
        }
        try {
            p.unref?.();
        } catch {
        }

        killProcessTree(p);

        setTimeout(finish, 3000);
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

async function gracefulAppQuit(appExitCode = 0) {
    if (quitting) return;
    quitting = true;
    try {
        if (agentProc) {
            stoppingPromise = stopAgent();
            await stoppingPromise;
        }
    } catch {
    }
    app.exit(appExitCode);
}

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
}

app.whenReady().then(async () => {
    setupSignalHandlers();
    if (process.platform === 'darwin') {
        try {
            await ensureAudioSetup();
        } catch (e) {
            console.error('[audio-setup] failed', e);
        }
        app.on('browser-window-focus', async () => {
            try {
                await ensureAudioSetup();
            } catch {
            }
        });
    }
    createWindow();
});

app.on('before-quit', (e) => {
    if (agentProc && !quitting) {
        e.preventDefault();
        gracefulAppQuit(0);
    }
});
app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
