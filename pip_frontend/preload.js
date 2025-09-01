// preload.js
const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    // vorhanden
    resizeWindow: (h) => ipcRenderer.send('resize-window', h),

    // neu
    log: (msg) => ipcRenderer.send('log', msg),
    agentStart: (cfg) => ipcRenderer.invoke('agent:start', cfg),
    agentStop: () => ipcRenderer.invoke('agent:stop'),
    agentList: () => ipcRenderer.invoke('agent:list'),
    agentStatus: () => ipcRenderer.invoke('agent:status'),
    getPlatform: () => ipcRenderer.invoke('env:platform'),
});
