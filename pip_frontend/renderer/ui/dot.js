import {el} from "../state.js";

export function setDotColor(tlObj) {
    console.log(tlObj)
    let color = null;
    if (typeof tlObj === "string") color = JSON.parse(tlObj).response;
    else if (tlObj && typeof tlObj === "object") color = tlObj.response || tlObj?.data?.response;
    if (!color) {
        el.dot.style.color = '#d9d9d9';
        el.dot.style.background = 'rgba(217,217,217,0.6)';
        return;
    }
    if (color === 'red') {
        el.dot.style.color = '#e53935';
        el.dot.style.background = '#e53935';
    } else if (color === 'yellow') {
        el.dot.style.color = '#fdd835';
        el.dot.style.background = '#fdd835';
    } else if (color === 'green') {
        el.dot.style.color = '#43a047';
        el.dot.style.background = '#43a047';
    } else {
        el.dot.style.color = '#d9d9d9';
        el.dot.style.background = 'rgba(217,217,217,0.6)';
    }
}