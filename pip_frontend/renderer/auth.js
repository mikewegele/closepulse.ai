import {API_BASE} from "../config.js";

const LS_TOKEN = "cp_token";
const LS_USER = "cp_user";

export function getToken() {
    return localStorage.getItem(LS_TOKEN) || "";
}

export function getUser() {
    try {
        return JSON.parse(localStorage.getItem(LS_USER) || "{}");
    } catch {
        return {};
    }
}

export function logout() {
    localStorage.removeItem(LS_TOKEN);
    localStorage.removeItem(LS_USER);
    location.reload();
}

function ensureLoginModal() {
    if (document.getElementById("login-overlay")) return;

    // <<< Wichtig: App komplett ausblenden
    document.documentElement.classList.add("login-open");

    const wrap = document.createElement("div");
    wrap.id = "login-overlay";
    wrap.className = "login-overlay"; // Styling in CSS
    wrap.innerHTML = `
    <div class="login-card">
      <h2 class="login-title">Anmelden</h2>
      <form id="login-form" class="login-form">
        <label class="login-label" for="login-email">E-Mail</label>
        <input id="login-email" class="login-input" type="email" placeholder="you@team.com" required />

        <label class="login-label" for="login-pass">Passwort</label>
        <input id="login-pass" class="login-input" type="password" placeholder="••••••••" required />

        <button type="submit" class="btn login-btn">Einloggen</button>
      </form>
      <p id="login-error" class="login-error"></p>
    </div>
  `;
    document.body.appendChild(wrap);
}

async function doLogin(email, password) {
    const res = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({email, password})
    });
    if (!res.ok) throw new Error(`Login fehlgeschlagen (${res.status})`);
    const json = await res.json();
    localStorage.setItem(LS_TOKEN, json.access_token || "");
    localStorage.setItem(LS_USER, JSON.stringify({
        email, role: json.role, team_id: json.team_id
    }));
}

export async function ensureLoggedIn() {
    const tok = getToken();
    if (tok) return;

    ensureLoginModal();

    return new Promise((resolve) => {
        const form = document.getElementById("login-form");
        const err = document.getElementById("login-error");
        form.onsubmit = async (e) => {
            e.preventDefault();
            err.textContent = "";
            const email = document.getElementById("login-email").value.trim();
            const pass = document.getElementById("login-pass").value;
            try {
                await doLogin(email, pass);
                document.getElementById("login-overlay")?.remove();
                document.documentElement.classList.remove("login-open"); // <<< App wieder einblenden
                resolve();
            } catch (ex) {
                err.textContent = ex?.message || "Login fehlgeschlagen";
            }
        };
    });
}
