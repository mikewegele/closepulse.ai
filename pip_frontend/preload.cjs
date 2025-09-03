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

(function () {
    // verhindert doppeltes Boot/Interval
    if (window.__boot) return
    window.__boot = true

    window.electronAPI.log('boot')

    let prev = null

    async function tick() {
        try {
            const on = await window.electronAPI.agentStatus()
            if (on !== prev) {
                window.electronAPI.log(`agent:${on ? 'on' : 'off'}`)
                prev = on
            }
        } catch (e) {
            // ignorieren
        }
    }

    tick()
    setInterval(tick, 2000) // alle 2s Status checken
})()