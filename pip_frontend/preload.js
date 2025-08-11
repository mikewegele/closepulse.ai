const {contextBridge, ipcRenderer} = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
    resizeWindow: (h) => ipcRenderer.send("resize-window", h)
});
