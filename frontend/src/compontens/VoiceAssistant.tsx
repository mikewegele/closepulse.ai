import React, {useCallback, useEffect, useRef, useState} from "react";
import {Box, Button, Typography} from "@mui/material";
import {makeStyles} from "tss-react/mui";
import axios from "axios";
import {useLocalMic, useWebRTCAudio} from "../util/audioAdapters.ts";

const useStyles = makeStyles()(() => ({
    root: {
        height: "100vh",
        width: "100vw",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#fafafa",
        fontFamily: "'Helvetica Neue', Helvetica, Arial, sans-serif"
    },
    container: {
        background: "#fff",
        borderRadius: 12,
        padding: "2rem",
        boxShadow: "0 8px 24px rgba(0,0,0,0.1)",
        maxWidth: 600,
        width: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "1.5rem",
        textAlign: "center",
        position: "relative"
    },
    messageBox: {
        width: "100%",
        padding: "1rem",
        borderRadius: 8,
        background: "#f9f9f9",
        whiteSpace: "pre-wrap",
        fontSize: "1.1rem",
        color: "#333"
    },
    button: {
        padding: "1rem 2rem",
        fontSize: "1rem",
        borderRadius: 50,
        backgroundColor: "#FF6F61",
        color: "#fff",
        "&:hover": {backgroundColor: "#e05a4f"}
    }
}));

const ClosePulseAI: React.FC = () => {
    const {classes} = useStyles();
    const [userText, setUserText] = useState("");
    const [assistantText, setAssistantText] = useState("");
    const [fullTranscript, setFullTranscript] = useState("");
    const [inputType, setInputType] = useState<"localMic" | "webRTC">("localMic");
    const [ampelStatus, setAmpelStatus] = useState<"green" | "yellow" | "red" | null>(null);
    const [suggestions, setSuggestions] = useState<string[]>([]);
    const pipRef = useRef<Window | null>(null);

    useEffect(() => {
        const saved = localStorage.getItem("voiceAssistantConfig");
        if (saved) {
            try {
                const cfg = JSON.parse(saved);
                setInputType(cfg.mode === "webrtc" ? "webRTC" : "localMic");
            } catch {
                setInputType("localMic");
            }
        }
    }, []);

    const fetchTextFromAPI = useCallback(async (url: string, data: any) => {
        const res = await axios.post(url, data);
        return res.data;
    }, []);

    const makeSuggestions = (text: string) => {
        const s = text.split(/(?<=[.!?])\s+/).filter(Boolean).map(x => x.trim()).filter(Boolean).slice(0, 3);
        if (s.length < 3) {
            const fill = ["Bitte wiederholen.", "Mehr Details bitte.", "Wie geht es weiter?"];
            while (s.length < 3) s.push(fill[s.length]);
        }
        return s.map(t => t.length > 120 ? t.slice(0, 117) + "…" : t);
    };

    const processResponse = useCallback(async (conversation: string) => {
        const ask = await fetchTextFromAPI("http://localhost:8000/ask", [{role: "user", content: conversation}]);
        setAssistantText(ask.response);
        setSuggestions(makeSuggestions(ask.response));
        const tl = await fetchTextFromAPI("http://localhost:8000/trafficLight", [{
            role: "user",
            content: conversation
        }]);
        setAmpelStatus(tl.response);
        return ask.response;
    }, [fetchTextFromAPI]);

    const onAudioStop = useCallback(async (blob: Blob) => {
        const formData = new FormData();
        formData.append("file", blob, "recording.webm");
        try {
            const transcribe = await fetchTextFromAPI("http://localhost:8000/transcribe", formData);
            const newUserText = transcribe.text;
            if (!newUserText) return;
            const updated = fullTranscript + `User: ${newUserText}\n`;
            const assistantResponse = await processResponse(updated);
            setFullTranscript(updated + `Assistant: ${assistantResponse}\n`);
            setUserText(newUserText);
        } catch (e) {
            console.error("API-Fehler:", e);
        }
    }, [fetchTextFromAPI, fullTranscript, processResponse]);

    const localMicAdapter = useLocalMic(onAudioStop);
    const webRTCAdapter = useWebRTCAudio(onAudioStop);
    const {recording, start, stop} = inputType === "localMic" ? localMicAdapter : webRTCAdapter;

    const renderPiP = useCallback(() => {
        const win = pipRef.current;
        if (!win) return;
        const doc = win.document;
        doc.body.style.margin = "0";
        doc.body.style.background = "#fff";
        doc.body.style.font = "14px system-ui, -apple-system, Segoe UI, Roboto";
        doc.body.innerHTML = `
      <div id="root" style="display:flex;flex-direction:column;gap:12px;align-items:center;padding:12px">
        <div id="dot" style="width:24px;height:24px;border-radius:50%"></div>
        <button class="s"></button>
        <button class="s"></button>
        <button class="s"></button>
      </div>
    `;
        const dot = doc.getElementById("dot") as HTMLDivElement;
        dot.style.background = ampelStatus === "red" ? "#e53935" : ampelStatus === "yellow" ? "#fdd835" : ampelStatus === "green" ? "#43a047" : "#d9d9d9";
        const btns = Array.from(doc.querySelectorAll(".s")) as HTMLButtonElement[];
        const localSuggestions = suggestions.slice(0, 3);
        btns.forEach((b, i) => {
            b.textContent = localSuggestions[i] ?? "";
            b.style.cssText = "width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:10px;background:#fff;text-align:center;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
            b.onclick = () => {
                win.close();
            };
        });
    }, [ampelStatus, suggestions]);

    const startPiP = useCallback(async () => {
        // @ts-ignore
        const api = (window as any).documentPictureInPicture;
        if (!api) {
            alert("Document Picture-in-Picture wird von diesem Browser nicht unterstützt.");
            return;
        }
        if (pipRef.current && !pipRef.current.closed) {
            pipRef.current.focus();
            return;
        }
        // @ts-ignore
        const pipWin: Window = await api.requestWindow({width: 280, height: 260, disallowReturnToOpener: true});
        pipRef.current = pipWin;
        pipWin.addEventListener("pagehide", () => {
            pipRef.current = null;
        });
        renderPiP();
    }, [renderPiP]);

    useEffect(() => {
        renderPiP();
    }, [renderPiP]);

    return (
        <>
            <Box sx={{position: "fixed", top: 16, right: 16, zIndex: 10}}>
                <Button variant="contained" onClick={startPiP}>PiP starten</Button>
            </Box>

            <Box className={classes.root}>
                <Box className={classes.container}>
                    <Typography variant="h4">closepulse.ai</Typography>
                    <Typography variant="body2"
                                sx={{mb: 2}}>Eingabemodus: <strong>{inputType === "localMic" ? "Lokales Mikrofon" : "WebRTC"}</strong></Typography>

                    {userText && (<Box className={classes.messageBox}><strong>User:</strong> {userText}</Box>)}
                    {assistantText && (
                        <Box className={classes.messageBox}><strong>Assistant:</strong> {assistantText}</Box>)}

                    {!recording ? (
                        <Button className={classes.button} onClick={start}>Aufnahme starten</Button>
                    ) : (
                        <Button className={classes.button} onClick={stop}>Aufnahme stoppen</Button>
                    )}
                </Box>
            </Box>
        </>
    );
};

export default ClosePulseAI;
