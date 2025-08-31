// main.js (relevante Auszüge)
const {app, BrowserWindow, ipcMain} = require('electron');
const path = require('path');

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

app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
