import {el} from "../state.js";

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