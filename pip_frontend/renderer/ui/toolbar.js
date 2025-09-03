import {el} from "../state.js";

export function initToolbar() {
    let bar = document.getElementById("cp-toolbar");
    if (!bar) {
        bar = document.createElement("div");
        bar.id = "cp-toolbar";
        bar.className = "row";
        el.wrap.appendChild(bar); // statt prepend → jetzt unten
    }
}
