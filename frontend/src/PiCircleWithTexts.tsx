import React, {useEffect, useMemo, useRef, useState} from "react";
import {Inviter, Registerer, Session, SessionState, URI, UserAgent} from "sip.js";

const SIP_DOMAIN = "mike-wegele.sip-eu.vonage.com";
const SIP_USER = "mike-wegele";
const SIP_PASS = "4hA=39ptg!u6F1WnevVu";

export default function SipPoc() {
    const [wsServer, setWsServer] = useState("wss://YOUR-SIP-WEBSOCKET-URL");
    const [domain, setDomain] = useState(SIP_DOMAIN);
    const [username, setUsername] = useState(SIP_USER);
    const [password, setPassword] = useState(SIP_PASS);
    const [target, setTarget] = useState("");
    const [status, setStatus] = useState("idle");
    const [registered, setRegistered] = useState(false);
    const userAgentRef = useRef<UserAgent | null>(null);
    const registererRef = useRef<Registerer | null>(null);
    const sessionRef = useRef<Session | null>(null);

    const aor = useMemo(() => `sip:${username}@${domain}`, [username, domain]);

    useEffect(() => {
        return () => {
            if (sessionRef.current) sessionRef.current.dispose();
            if (registererRef.current) registererRef.current.unregister();
            if (userAgentRef.current) userAgentRef.current.stop();
        };
    }, []);

    const connect = async () => {
        if (!wsServer.startsWith("ws")) return setStatus("WS URL needed");
        const ua = new UserAgent({
            uri: URI.parse(aor)!,
            transportOptions: {server: wsServer},
            authorizationUsername: username,
            authorizationPassword: password,
            delegate: {
                onInvite: incoming => {
                    sessionRef.current = incoming;
                    wireSession(incoming);
                    setStatus("incoming call");
                }
            }
        });
        userAgentRef.current = ua;
        await ua.start();
        const reg = new Registerer(ua);
        registererRef.current = reg;
        await reg.register();
        setRegistered(true);
        setStatus("registered");
    };

    const disconnect = async () => {
        try {
            await registererRef.current?.unregister();
        } catch {
        }
        try {
            await userAgentRef.current?.stop();
        } catch {
        }
        setRegistered(false);
        setStatus("idle");
    };

    const call = async () => {
        if (!registered) return;
        const targetUri = target.includes("@") ? target : `sip:${target}@${domain}`;
        const inviter = new Inviter(userAgentRef.current!, URI.parse(targetUri)!);
        sessionRef.current = inviter;
        wireSession(inviter);
        await inviter.invite();
    };

    const hangup = async () => {
        const s = sessionRef.current;
        if (!s) return;
        if (s.state === SessionState.Established) await s.bye();
        else await s.cancel();
        setStatus("ready");
    };

    const wireSession = (s: Session) => {
        s.stateChange.addListener(state => {
            if (state === SessionState.Establishing) setStatus("ringing");
            if (state === SessionState.Established) setStatus("in call");
            if (state === SessionState.Terminated) setStatus("ready");
        });
    };

    return (
        <div className="min-h-screen bg-gray-50 p-6">
            <div className="max-w-xl mx-auto grid gap-4">
                <h1 className="text-2xl font-semibold">SIP POC</h1>
                <div className="grid gap-2">
                    <label className="text-sm">WebSocket Server (WSS)</label>
                    <input className="border rounded-xl px-3 py-2" value={wsServer}
                           onChange={e => setWsServer(e.target.value)} placeholder="wss://example.com:7443"/>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div className="grid gap-2">
                        <label className="text-sm">Domain</label>
                        <input className="border rounded-xl px-3 py-2" value={domain}
                               onChange={e => setDomain(e.target.value)}/>
                    </div>
                    <div className="grid gap-2">
                        <label className="text-sm">User</label>
                        <input className="border rounded-xl px-3 py-2" value={username}
                               onChange={e => setUsername(e.target.value)}/>
                    </div>
                </div>
                <div className="grid gap-2">
                    <label className="text-sm">Password</label>
                    <input className="border rounded-xl px-3 py-2" type="password" value={password}
                           onChange={e => setPassword(e.target.value)}/>
                </div>
                <div className="flex gap-3">
                    {!registered ? (
                        <button onClick={connect} className="px-4 py-2 rounded-2xl shadow bg-black text-white">Connect &
                            Register</button>
                    ) : (
                        <button onClick={disconnect}
                                className="px-4 py-2 rounded-2xl shadow bg-gray-800 text-white">Disconnect</button>
                    )}
                    <div className="px-3 py-2 text-sm bg-white rounded-2xl border">{status}</div>
                </div>
                <div className="h-px bg-gray-200"/>
                <div className="grid gap-2">
                    <label className="text-sm">Target SIP URI or extension</label>
                    <input className="border rounded-xl px-3 py-2" value={target}
                           onChange={e => setTarget(e.target.value)}
                           placeholder="1001 or sip:1001@mike-wegele.sip-eu.vonage.com"/>
                </div>
                <div className="flex gap-3">
                    <button onClick={call} disabled={!registered}
                            className="px-4 py-2 rounded-2xl shadow bg-green-600 text-white disabled:opacity-50">Call
                    </button>
                    <button onClick={hangup} className="px-4 py-2 rounded-2xl shadow bg-red-600 text-white">Hang up
                    </button>
                </div>
                <p className="text-xs text-gray-500">Hinweis: Für Browser-Anrufe brauchst du einen SIP-Server mit
                    WebSocket (WSS) Gateway. Trage die korrekte WSS-URL deines Providers ein.</p>
            </div>
        </div>
    );
}
