// src/backend/suggestClient.js
export function connectSuggestions(wsBase, ext, onSuggestions) {
    if (!wsBase) return;
    const url = `${wsBase.replace(/\/$/, '')}/ws/suggest?ext=${encodeURIComponent(ext || 'default')}`;
    const ws = new WebSocket(url);

    ws.onopen = () => console.log('[Renderer] suggest WS open', url);

    ws.onmessage = (evt) => {
        try {
            const data = JSON.parse(evt.data || '{}');
            const list = Array.isArray(data.suggestions) ? data.suggestions : [];
            const [s1, s2, s3] = list;
            onSuggestions?.({s1, s2, s3, raw: data});
        } catch (e) {
            console.error('[Renderer] suggest parse error', e);
        }
    };

    ws.onclose = () => console.log('[Renderer] suggest WS closed');
    ws.onerror = (e) => console.error('[Renderer] suggest WS error', e);

    return ws;
}
