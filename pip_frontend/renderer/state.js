export const el = {
    dot: document.getElementById("dot"),
    s1: document.getElementById("s1"),
    s2: document.getElementById("s2"),
    s3: document.getElementById("s3"),
    rec: document.getElementById("rec"),
    close: document.getElementById("close"),
    wrap: document.querySelector(".wrap"),
};

// app state (persisted where needed)
export const state = {
    showLatency: JSON.parse(localStorage.getItem("cp_showLatency") ?? "true"),
    theme: localStorage.getItem("cp_theme") || "light",
    analyzeSupported: true,
    turns: [],
    askAborter: null,
    tlAborter: null,
    recording: false,
    isStarting: false,
    mediaRecorder: null,
    chunks: [],
    streamRef: null,
};

// Resize to content
const ro = new ResizeObserver(() => {
    const neededHeight = el.wrap.scrollHeight + 40;
    window.electronAPI?.resizeWindow(neededHeight);
});
ro.observe(el.wrap);

// Console -> main process mirror (optional)
const __origLog = console.log.bind(console);

function stringifyArg(a) {
    try {
        if (typeof a === 'string') return a;
        return JSON.stringify(a);
    } catch {
        return String(a);
    }
}

function forwardLog(...args) {
    const line = args.map(stringifyArg).join(' ');
    window.electronAPI?.log?.(line);
}

console.log = (...args) => {
    __origLog(...args);
    forwardLog(...args);
};