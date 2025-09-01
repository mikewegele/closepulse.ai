// main.js
const {app, BrowserWindow, ipcMain} = require('electron');
const {spawn} = require('child_process');
const path = require('path');

let agentProc = null;

function createWindow() {
    const win = new BrowserWindow({
        width: 360,
        height: 500,
        frame: false,
        transparent: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });
    win.loadFile('index.html');
}

// ---- Agent Control ----
function resolveAgentCommand() {
    if (!app.isPackaged) {
        return {
            cmd: process.env.PYTHON || 'python3',
            args: [path.join(__dirname, 'closepulse_agent.py')],
        };
    }
    const bin = process.platform === 'win32'
        ? path.join(process.resourcesPath, 'closepulse_agent_win.exe')
        : path.join(process.resourcesPath, 'closepulse_agent_mac');
    return {cmd: bin, args: []};
}

function startAgent({ws, ext, mic, spk}) {
    if (agentProc) return true;
    const {cmd, args} = resolveAgentCommand();
    const full = [...args, '--ws', ws, '--ext', ext];
    if (mic) full.push('--mic', mic);
    if (spk) full.push('--spk', spk);

    agentProc = spawn(cmd, full, {stdio: ['ignore', 'pipe', 'pipe']});
    agentProc.stdout.on('data', d => console.log('[agent]', d.toString().trim()));
    agentProc.stderr.on('data', d => console.error('[agent-err]', d.toString().trim()));
    agentProc.on('exit', (code, sig) => {
        console.log(`agent exited code=${code} sig=${sig}`);
        agentProc = null;
    });
    return true;
}

function stopAgent() {
    if (!agentProc) return true;
    agentProc.kill('SIGTERM');
    agentProc = null;
    return true;
}

function listDevices() {
    return new Promise((resolve, reject) => {
        const {cmd, args} = resolveAgentCommand();
        const child = spawn(cmd, [...args, '--list-devices']);
        let out = '', err = '';
        child.stdout.on('data', d => (out += d.toString()));
        child.stderr.on('data', d => (err += d.toString()));
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

// ---- IPC ----
ipcMain.on('log', (_event, msg) => {
    console.log('[Renderer]', msg);
});
ipcMain.on('resize-window', (event, height) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win && Number.isFinite(height)) {
        const [w] = win.getSize();
        win.setSize(w, Math.ceil(height));
    }
});

ipcMain.handle('agent:start', async (_e, cfg) => startAgent(cfg));
ipcMain.handle('agent:stop', async () => stopAgent());
ipcMain.handle('agent:list', async () => listDevices());
ipcMain.handle('agent:status', async () => agentStatus());
ipcMain.handle('env:platform', async () => process.platform);

// ---- App lifecycle ----
app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
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
