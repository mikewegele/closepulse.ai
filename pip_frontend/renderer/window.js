import {BrowserWindow} from 'electron';
import path from 'path';

let mainWin = null;

export function createWindow({baseDir}) {
    mainWin = new BrowserWindow({
        width: 360,
        height: 500,
        frame: false,
        transparent: true,
        webPreferences: {
            preload: path.join(baseDir, 'preload.cjs'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    if (process.platform === 'darwin') {
        mainWin.setAlwaysOnTop(true, 'screen-saver');
        mainWin.setVisibleOnAllWorkspaces(true, {visibleOnFullScreen: true});
        mainWin.setFullScreenable(false);
    } else {
        mainWin.setAlwaysOnTop(true);
    }
    mainWin.loadFile(path.join(baseDir, 'index.html'));
    return mainWin;
}

export function getMainWindow() {
    return mainWin && !mainWin.isDestroyed() ? mainWin : null;
}
