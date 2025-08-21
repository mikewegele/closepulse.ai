export function safeJson(res) {
    return res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`));
}

export function fmtMs(x) {
    if (x == null || Number.isNaN(x)) return "–";
    const ms = x * 1000;
    if (ms < 1) return `${ms.toFixed(2)} ms`;
    if (ms < 1000) return `${ms.toFixed(0)} ms`;
    return `${(ms / 1000).toFixed(2)} s`;
}

export function convoToString(turns) {
    return turns.map(t => `${t.role === 'user' ? 'User' : 'Assistant'}: ${t.content}`).join('\n');
}

export function pushTurn(state, max, role, content) {
    state.turns.push({role, content});
    if (state.turns.length > max) state.turns = state.turns.slice(-max);
}