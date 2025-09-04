// src/backend/suggestClient.js

function toWsBase(u) {
    if (!u) return '';
    return u.replace(/^http(s?):\/\//, 'ws$1://').replace(/\/$/, '');
}

export function connectSuggestions(wsBase, ext, onSuggestions, onDots) {
    if (!wsBase) return;
    const url = `${toWsBase(wsBase)}/ws/transcript?ext=${encodeURIComponent(ext || 'default')}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
    };
    ws.onmessage = (evt) => {
        try {
            const data = JSON.parse(evt.data || '{}');
            const trafficLight = data.trafficLight;
            const list = Array.isArray(data.suggestions) ? data.suggestions : [];
            const [s1, s2, s3] = list;
            onSuggestions?.({s1, s2, s3, trafficLight});
            onDots?.(trafficLight);
        } catch {
        }
    };
    ws.onclose = () => {
    };
    ws.onerror = () => {
    };

    return ws;
}

export function connectSuggestionsWithRetry(wsBase, ext, onSuggestions, {
    maxRetries = 10,
    baseDelay = 500,
    maxDelay = 8000,
    onDots
} = {}) {
    if (!wsBase) return () => {
    };
    let attempt = 0;
    let ws = null;
    let disposed = false;

    function delayFor(n) {
        const d = Math.min(baseDelay * Math.pow(2, Math.max(0, n - 1)), maxDelay);
        const j = Math.floor(Math.random() * 250);
        return d + j;
    }

    function open() {
        if (disposed) return;
        attempt++;
        ws = connectSuggestions(wsBase, ext, onSuggestions, onDots);
        if (!ws) return;

        let opened = false;

        const onopen = ws.onopen;
        ws.onopen = (evt) => {
            opened = true;
            attempt = 0;
            onopen?.(evt);
        };

        const onclose = ws.onclose;
        ws.onclose = (evt) => {
            onclose?.(evt);
            if (disposed) return;
            const code = evt?.code;
            const clean = code === 1000;
            if (attempt >= maxRetries) return;
            if (!clean || !opened) {
                setTimeout(open, delayFor(attempt));
            } else {
                setTimeout(open, delayFor(1));
            }
        };

        const onerror = ws.onerror;
        ws.onerror = (e) => {
            onerror?.(e);
        };
    }

    function handleOnline() {
        if (!ws || ws.readyState === WebSocket.CLOSED) {
            if (attempt < maxRetries && !disposed) setTimeout(open, delayFor(attempt || 1));
        }
    }

    open();

    if (typeof window !== 'undefined') {
        window.addEventListener('online', handleOnline);
        document.addEventListener('visibilitychange', () => {
            if (!disposed && document.visibilityState === 'visible') handleOnline();
        });
    }

    return () => {
        disposed = true;
        try {
            window.removeEventListener('online', handleOnline);
        } catch {
        }
        try {
            if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
        } catch {
        }
    };
}
