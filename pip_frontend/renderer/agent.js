import {spawn} from 'child_process';
import path from 'path';
import {fileURLToPath} from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let agentProc = null;
let agentStarting = false;

function resolveAgentCommand() {
    if (process.env.ELECTRON_START_URL || process.env.NODE_ENV !== 'production') {
        return {
            cmd: process.env.PYTHON || 'python3',
            args: [path.join(path.dirname(__dirname), 'closepulse_agent.py')]
        };
    }
    const bin = process.platform === 'win32'
        ? path.join(process.resourcesPath, 'closepulse_agent_win.exe')
        : path.join(process.resourcesPath, 'closepulse_agent_mac');
    return {cmd: bin, args: []};
}

function killProcessTree(p) {
    if (!p || !p.pid) return;
    if (process.platform === 'win32') {
        try {
            spawn('taskkill', ['/PID', String(p.pid), '/T', '/F'], {stdio: 'ignore'});
        } catch {
        }
    } else {
        try {
            process.kill(-p.pid, 'SIGTERM');
        } catch {
        }
        setTimeout(() => {
            try {
                process.kill(-p.pid, 'SIGKILL');
            } catch {
            }
        }, 1000);
    }
}

export async function startAgent({ws, ext, mic, loopback, lang}) {
    if (agentProc || agentStarting) return true;
    agentStarting = true;
    try {
        if (loopback) mic = undefined;
        const {cmd, args} = resolveAgentCommand();
        const full = [...args, '--ws', ws, '--ext', ext];
        if (mic) full.push('--mic', mic);
        if (loopback) full.push('--loopback', loopback);
        if (lang) full.push('--lang', lang);
        const env = {...process.env, PYTHONUNBUFFERED: '1'};
        agentProc = spawn(cmd, full, {
            stdio: ['ignore', 'pipe', 'pipe'],
            env,
            detached: process.platform !== 'win32',
            windowsHide: true
        });
        agentProc.stdout.on('data', d => console.log('[agent]', String(d).trim()));
        agentProc.stderr.on('data', d => console.error('[agent-err]', String(d).trim()));
        agentProc.once('error', e => console.error('[agent] spawn error', e));
        agentProc.once('exit', () => {
            agentProc = null;
        });
        return true;
    } finally {
        agentStarting = false;
    }
}

export function stopAgent() {
    if (!agentProc) return Promise.resolve(true);
    const p = agentProc;
    agentProc = null;
    return new Promise((resolve) => {
        let done = false;
        const finish = () => {
            if (!done) {
                done = true;
                resolve(true);
            }
        };
        p.once('exit', finish);
        p.once('close', finish);
        try {
            p.stdout?.removeAllListeners();
            p.stderr?.removeAllListeners();
        } catch {
        }
        try {
            p.unref?.();
        } catch {
        }
        killProcessTree(p);
        setTimeout(finish, 3000);
    });
}

export function listDevices() {
    return new Promise((resolve, reject) => {
        const {cmd, args} = resolveAgentCommand();
        const child = spawn(cmd, [...args, '--list-devices'], {env: {...process.env}});
        let out = '', err = '';
        child.stdout.on('data', d => out += d.toString());
        child.stderr.on('data', d => err += d.toString());
        child.on('exit', () => {
            if (err) console.error('[agent-list-err]', err.trim());
            try {
                resolve(JSON.parse(out || '{}'));
            } catch (e) {
                reject(e);
            }
        });
    });
}

export function agentRunning() {
    return !!agentProc;
}
