import {el} from "../state.js";

export function makeSuggestionsFrom(text) {
    if (!text) return [];
    if (Array.isArray(text)) return text.slice(0, 3).map(s => String(s).trim()).filter(Boolean);
    try {
        const first = text.indexOf('['), last = text.lastIndexOf(']');
        if (first !== -1 && last !== -1 && last > first) {
            const arr = JSON.parse(text.slice(first, last + 1));
            if (Array.isArray(arr)) return arr.slice(0, 3).map(s => String(s).trim()).filter(Boolean);
        }
    } catch {
    }
    const out = [];
    const re = /^\s*-\s+(.+?)\s*$/gm;
    let m;
    while ((m = re.exec(text)) && out.length < 3) out.push(m[1]);
    if (out.length) return out;
    return (text || "").split(/(?<=[.!?])\s+/).map(t => t.trim()).filter(Boolean).slice(0, 3);
}

export function renderSuggestions(sugg) {
    const buttons = [el.s1, el.s2, el.s3];
    buttons.forEach((button, i) => {
        const full = sugg[i];
        if (full && full.length) {
            button.style.display = 'block';
            button.disabled = false;
            button.title = full;
            button.textContent = full;
        } else {
            button.textContent = '';
            button.title = '';
            button.style.display = 'none';
        }
    });
}