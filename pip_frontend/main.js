import {app} from 'electron';
import path from 'path';
import {fileURLToPath} from 'url';
import {createWindow, getMainWindow} from './renderer/window.js';
import {ensureAudioSetup} from './renderer/audio/index.js';
import {registerIpc} from './renderer/ipc.js';
import {agentRunning, stopAgent} from './renderer/agent.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
    app.quit();
    process.exit(0);
} else {
    app.on('second-instance', () => {
        const win = getMainWindow();
        if (win) {
            if (win.isMinimized()) win.restore();
            win.focus();
        }
    });
}

let quitting = false;

async function gracefulAppQuit(code = 0) {
    if (quitting) return;
    quitting = true;
    try {
        if (agentRunning()) await stopAgent();
    } catch {
    }
    app.exit(code);
}

function setupSignals() {
    const shutdown = async () => {
        try {
            await stopAgent();
        } catch {
        }
        process.exit(0);
    };
    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
    process.on('uncaughtException', () => shutdown());
}

app.whenReady().then(async () => {
    setupSignals();
    try {
        await ensureAudioSetup();
    } catch {
    }
    createWindow({baseDir: __dirname});
    registerIpc();
});

app.on('before-quit', (e) => {
    if (agentRunning() && !quitting) {
        e.preventDefault();
        gracefulAppQuit(0);
    }
});
app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
    if (!getMainWindow()) createWindow({baseDir: __dirname});
});
