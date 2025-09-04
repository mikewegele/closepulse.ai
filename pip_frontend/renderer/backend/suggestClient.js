// src/backend/suggestClient.js

export function connectSuggestions(wsBase, ext, onSuggestions, onDots) {
    if (!wsBase) return;
    const wsBaseWS = wsBase.replace(/^http(s?):\/\//, 'ws$1://').replace(/\/$/, '');
    const url = `${wsBaseWS}/ws/transcript?ext=${encodeURIComponent(ext || 'default')}`;
    console.log('[Renderer] WS URL:', url);
    const ws = new WebSocket(url);

    ws.onopen = () => console.log('[Renderer] suggest WS open', url);
    ws.onmessage = (evt) => {
        console.log("[Renderer] suggest WS message:", evt.data);
        try {
            const data = JSON.parse(evt.data || '{}');
            const trafficLight = data.trafficLight;
            const list = Array.isArray(data.suggestions) ? data.suggestions : [];
            const [s1, s2, s3] = list;
            onSuggestions?.({s1, s2, s3, trafficLight});
        } catch (e) {
            console.error('[Renderer] suggest parse error', e);
        }
    };
    ws.onclose = (evt) => console.log('[Renderer] suggest WS closed', evt?.code, evt?.reason);
    ws.onerror = (e) => console.error('[Renderer] suggest WS error', e);

    return ws;
}

export function connectSuggestionsWithRetry(wsBase, ext, onSuggestions, {maxRetries = 10} = {}) {
    if (!wsBase) return () => {
    };
    let attempt = 0;
    let ws;

    const open = () => {
        attempt++;
        ws = connectSuggestions(wsBase, ext, onSuggestions);
        if (!ws) return;

        let opened = false;

        const origOpen = ws.onopen;
        ws.onopen = (evt) => {
            opened = true;
            origOpen?.(evt);
        };

        const origClose = ws.onclose;
        ws.onclose = (evt) => {
            origClose?.(evt);
            if (!opened && attempt < maxRetries) {
                const backoff = Math.min(1000 * Math.pow(2, attempt - 1), 8000);
                setTimeout(open, backoff);
            }
        };
    };

    open();
    return () => ws && ws.close();
}
