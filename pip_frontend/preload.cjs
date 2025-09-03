// preload.cjs
const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    resizeWindow: (h) => ipcRenderer.send('resize-window', h),

    log: (msg) => ipcRenderer.send('log', msg),

    agentStart: (cfg) => ipcRenderer.invoke('agent:start', cfg),
    agentStop: () => ipcRenderer.invoke('agent:stop'),
    agentList: () => ipcRenderer.invoke('agent:list'),
    agentStatus: () => ipcRenderer.invoke('agent:status'),

    getPlatform: () => ipcRenderer.invoke('env:platform'),
});
