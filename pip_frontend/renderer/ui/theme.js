import {state} from "../state.js";

export function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("cp_theme", theme);
}

export function initTheme() {
    applyTheme(state.theme);
}