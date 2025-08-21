import React, {useEffect, useMemo, useRef, useState} from "react";
import {Invitation, Registerer, Session, SessionState, UserAgent} from "sip.js";

type Props = {};

const InboundCallTest: React.FC<Props> = () => {
    const [wsServer, setWsServer] = useState("wss://sip.telnyx.com:7443");
    const [domain, setDomain] = useState("sip.telnyx.com");
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [status, setStatus] = useState("idle");
    const [caller, setCaller] = useState("");
    const [registered, setRegistered] = useState(false);
    const [ringing, setRinging] = useState(false);
    const userAgentRef = useRef<UserAgent | null>(null);
    const registererRef = useRef<Registerer | null>(null);
    const sessionRef = useRef<Session | null>(null);
    const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
    const localStreamRef = useRef<MediaStream | null>(null);

    const aor = useMemo(() => UserAgent.makeURI(`sip:${username}@${domain}`), [username, domain]);

    useEffect(() => {
        return () => {
            try {
                registererRef.current?.unregister();
            } catch {
            }
            try {
                userAgentRef.current?.stop();
            } catch {
            }
            try {
                sessionRef.current?.dispose();
            } catch {
            }
            if (localStreamRef.current) {
                localStreamRef.current.getTracks().forEach(t => t.stop());
                localStreamRef.current = null;
            }
        };
    }, []);

    const ensureLocalStream = async () => {
        if (!localStreamRef.current) localStreamRef.current = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: false
        });
        return localStreamRef.current;
    };

    const attachRemote = (s: Session) => {
        const pc: RTCPeerConnection | undefined = (s as any).sessionDescriptionHandler?.peerConnection;
        if (!pc || !remoteAudioRef.current) return;
        pc.ontrack = (e: RTCTrackEvent) => {
            if (e.streams && e.streams[0]) {
                remoteAudioRef.current!.srcObject = e.streams[0];
                remoteAudioRef.current!.play().catch(() => {
                });
            }
        };
    };

    const wireSession = (s: Session) => {
        s.stateChange.addListener(state => {
            if (state === SessionState.Establishing) setStatus("establishing");
            if (state === SessionState.Established) {
                setStatus("in call");
                setRinging(false);
                attachRemote(s);
            }
            if (state === SessionState.Terminated) {
                setStatus("ready");
                setRinging(false);
                setCaller("");
                sessionRef.current = null;
            }
        });
    };

    const connect = async () => {
        if (!aor) {
            setStatus("invalid uri");
            return;
        }
        const ua = new UserAgent({
            uri: aor,
            transportOptions: {server: wsServer},
            authorizationUsername: username,
            authorizationPassword: password,
            sessionDescriptionHandlerFactoryOptions: {peerConnectionConfiguration: {sdpSemantics: "unified-plan" as any}},
            delegate: {
                onInvite: (inv: Invitation) => {
                    sessionRef.current = inv;
                    setCaller(inv.incomingInviteRequest.message.from?.uri?.user || "unknown");
                    wireSession(inv);
                    setRinging(true);
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
        if (localStreamRef.current) {
            localStreamRef.current.getTracks().forEach(t => t.stop());
            localStreamRef.current = null;
        }
        setRegistered(false);
        setStatus("idle");
        setCaller("");
        setRinging(false);
    };

    const answer = async () => {
        const s = sessionRef.current as Invitation | null;
        if (!s) return;
        const stream = await ensureLocalStream();
        await s.accept({sessionDescriptionHandlerOptions: {streams: [stream]}});
    };

    const reject = async () => {
        const s = sessionRef.current as Invitation | null;
        if (!s) return;
        await s.reject();
    };

    const hangup = async () => {
        const s = sessionRef.current;
        if (!s) return;
        await s.bye();
    };

    return (
        <div className="min-h-screen bg-gray-50 p-6">
            <div className="max-w-xl mx-auto grid gap-4">
                <h1 className="text-2xl font-semibold">Inbound Call Test</h1>
                <div className="grid gap-2">
                    <label className="text-sm">WSS</label>
                    <input className="border rounded-xl px-3 py-2" value={wsServer}
                           onChange={e => setWsServer(e.target.value)}/>
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
                               onChange={e => setUsername(e.target.value)} placeholder="SIP Username"/>
                    </div>
                </div>
                <div className="grid gap-2">
                    <label className="text-sm">Password</label>
                    <input className="border rounded-xl px-3 py-2" type="password" value={password}
                           onChange={e => setPassword(e.target.value)} placeholder="SIP Password"/>
                </div>
                <div className="flex gap-3 items-center">
                    {!registered ? (
                        <button onClick={connect} className="px-4 py-2 rounded-2xl shadow bg-black text-white">Connect &
                            Register</button>
                    ) : (
                        <button onClick={disconnect}
                                className="px-4 py-2 rounded-2xl shadow bg-gray-800 text-white">Disconnect</button>
                    )}
                    <div className="px-3 py-2 text-sm bg-white rounded-2xl border">{status}</div>
                </div>
                {ringing && (
                    <div
                        className="flex items-center justify-between bg-yellow-50 border border-yellow-200 rounded-xl p-3">
                        <div className="text-sm">Incoming from: <span className="font-mono">{caller}</span></div>
                        <div className="flex gap-2">
                            <button onClick={answer}
                                    className="px-4 py-2 rounded-2xl shadow bg-green-600 text-white">Answer
                            </button>
                            <button onClick={reject}
                                    className="px-4 py-2 rounded-2xl shadow bg-red-600 text-white">Reject
                            </button>
                        </div>
                    </div>
                )}
                <div className="flex gap-3">
                    <button onClick={hangup} className="px-4 py-2 rounded-2xl shadow bg-red-600 text-white">Hang up
                    </button>
                </div>
                <audio ref={remoteAudioRef} autoPlay playsInline/>
            </div>
        </div>
    );
};

export default InboundCallTest;
