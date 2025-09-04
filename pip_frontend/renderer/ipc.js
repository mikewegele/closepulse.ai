import {BrowserWindow, ipcMain} from 'electron';
import {agentRunning, listDevices, startAgent, stopAgent} from './agent.js';
import {getMainWindow} from './window.js';

export function registerIpc() {
    ipcMain.on('log', (_e, msg) => console.log('[Renderer]', msg));
    ipcMain.on('resize-window', (event, height) => {
        const win = BrowserWindow.fromWebContents(event.sender);
        if (win && Number.isFinite(height)) {
            const [w] = win.getSize();
            win.setSize(w, Math.ceil(height));
        }
    });
    ipcMain.handle('agent:start', async (_e, cfg) => {
        if (agentRunning()) return true;
        return startAgent(cfg);
    });
    ipcMain.handle('agent:stop', async () => stopAgent());
    ipcMain.handle('agent:list', async () => listDevices());
    ipcMain.handle('agent:status', async () => agentRunning());
    ipcMain.handle('env:platform', async () => process.platform);
    ipcMain.handle('win:set-aot', (_e, on) => {
        const win = getMainWindow();
        if (!win) return false;
        const enable = !!on;
        if (process.platform === 'darwin') {
            win.setAlwaysOnTop(enable, 'screen-saver');
            win.setVisibleOnAllWorkspaces(enable, {visibleOnFullScreen: true});
            win.setFullScreenable(!enable);
        } else {
            win.setAlwaysOnTop(enable);
        }
        return win.isAlwaysOnTop();
    });
}
