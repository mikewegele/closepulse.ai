export function connectSuggestions(wsBase, ext, onSuggestions) {
    const ws = new WebSocket(`${wsBase}/ws/suggest?ext=${encodeURIComponent(ext)}`);
    ws.onmessage = (e) => {
        try {
            const d = JSON.parse(e.data);
            onSuggestions && onSuggestions(d);
        } catch {
        }
    };
    return ws;
}
