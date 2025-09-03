export function log(...args) {
    const ts = new Date().toISOString().split('T')[1].replace('Z', '');
    const msg = `[R ${ts}] ${args.join(' ')}`;
    console.log(msg);
    if (window.electronAPI?.log) window.electronAPI.log(msg);
    const el = document.getElementById('last');
    if (el) el.textContent = msg;
}
