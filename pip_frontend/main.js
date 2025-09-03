// main.js (ESM)
import {app, BrowserWindow, ipcMain} from 'electron';
import {spawn} from 'child_process';
import path from 'path';
import {fileURLToPath} from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// --- Single Instance Lock ---
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
let agentStarting = false; // Start erlauben; Guard greift erst während Start

function createWindow() {
    const win = new BrowserWindow({
        width: 360,
        height: 500,
        frame: false,
        transparent: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.cjs'), // <— wichtig: .cjs
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

async function startAgent({ws, ext, mic, spk, loopback, lang}) {
    if (agentProc || agentStarting) return true;
    agentStarting = true;
    try {
        const {cmd, args} = resolveAgentCommand();
        const full = [...args, '--ws', ws, '--ext', ext];
        if (mic) full.push('--mic', mic);
        if (spk) full.push('--spk', spk);
        if (loopback) full.push('--loopback', loopback);
        if (lang) full.push('--lang', lang);

        const env = {...process.env};
        agentProc = spawn(cmd, full, {
            stdio: ['ignore', 'pipe', 'pipe'],
            env,
            detached: process.platform !== 'win32', // eigene Prozessgruppe auf Unix
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

// IPC
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

app.whenReady().then(() => {
    setupSignalHandlers();
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
