import React, {useCallback, useEffect, useState} from "react";
import {Box, Button, Typography} from "@mui/material";
import {makeStyles} from "tss-react/mui";
import axios from "axios";
import {AmpelSingleLight} from "./AmpelDisplay.tsx";
import {useLocalMic, useWebRTCAudio} from "../util/audioAdapters.ts";

const useStyles = makeStyles()(() => ({
    root: {
        height: "100vh",
        width: "100vw",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#fafafa",
        padding: "2rem",
        fontFamily: "'Helvetica Neue', Helvetica, Arial, sans-serif",
        // position: "relative", // NICHT nötig hier
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
        position: "relative",  // hier position relativ
    },
    ampelPosition: {
        position: "absolute",
        top: "1rem",
        right: "1rem",
        zIndex: 10,
    },
    messageBox: {
        width: "100%",
        padding: "1rem",
        borderRadius: 8,
        background: "#f9f9f9",
        whiteSpace: "pre-wrap",
        fontSize: "1.1rem",
        color: "#333",
    },
    button: {
        padding: "1rem 2rem",
        fontSize: "1rem",
        borderRadius: 50,
        backgroundColor: "#FF6F61",
        color: "#fff",
        "&:hover": {
            backgroundColor: "#e05a4f",
        },
    },
}));


const adapters = {
    localMic: useLocalMic,
    webRTC: useWebRTCAudio,
};

const ClosePulseAI: React.FC = () => {
    const {classes} = useStyles();
    const [userText, setUserText] = useState("");
    const [assistantText, setAssistantText] = useState("");
    const [ampelStatus, setAmpelStatus] = useState<"green" | "yellow" | "red" | null>(null);
    const [fullTranscript, setFullTranscript] = useState("");
    const [inputType, setInputType] = useState<keyof typeof adapters>("localMic");

    useEffect(() => {
        const savedConfig = localStorage.getItem("voiceAssistantConfig");
        if (savedConfig) {
            try {
                const config = JSON.parse(savedConfig);
                if (config.mode === "webrtc") {
                    setInputType("webRTC");
                } else {
                    setInputType("localMic");
                }
            } catch {
                setInputType("localMic");
            }
        }
    }, []);

    const fetchTextFromAPI = useCallback(async (url: string, data: any) => {
        const res = await axios.post(url, data);
        return res.data;
    }, []);

    const processResponse = useCallback(
        async (fullText: string) => {
            const askData = await fetchTextFromAPI("http://localhost:8000/ask", [{role: "user", content: fullText}]);
            setAssistantText(askData.response);

            const trafficLightData = await fetchTextFromAPI("http://localhost:8000/trafficLight", [{
                role: "user",
                content: fullText
            }]);
            setAmpelStatus(trafficLightData.response);

            return askData.response;
        },
        [fetchTextFromAPI]
    );

    const onAudioStop = useCallback(
        async (blob: Blob) => {
            const formData = new FormData();
            formData.append("file", blob, "recording.webm");

            try {
                const transcribeData = await fetchTextFromAPI("http://localhost:8000/transcribe", formData);
                const newUserText = transcribeData.text;
                if (!newUserText) return;

                const updatedTranscript = fullTranscript + `User: ${newUserText}\n`;
                const assistantResponse = await processResponse(updatedTranscript);

                setFullTranscript(updatedTranscript + `Assistant: ${assistantResponse}\n`);
                setUserText(newUserText);
                setAssistantText(assistantResponse);
            } catch (err) {
                console.error("API-Fehler:", err);
            }
        },
        [fetchTextFromAPI, fullTranscript, processResponse]
    );

    const {recording, start, stop} = adapters[inputType](onAudioStop);

    return (
        <Box className={classes.root}>
            <Box className={classes.container}>
                <Typography variant="h4">closepulse.ai</Typography>

                <Typography variant="body2" sx={{mb: 2}}>
                    Eingabemodus: <strong>{inputType === "localMic" ? "Lokales Mikrofon" : "WebRTC"}</strong>
                </Typography>

                {userText && (
                    <Box className={classes.messageBox}>
                        <strong>User:</strong> {userText}
                    </Box>
                )}

                {assistantText && (
                    <Box className={classes.messageBox}>
                        <strong>Assistant:</strong> {assistantText}
                    </Box>
                )}

                {ampelStatus && <AmpelSingleLight status={ampelStatus}/>}

                {!recording ? (
                    <Button className={classes.button} onClick={start}>
                        Aufnahme starten
                    </Button>
                ) : (
                    <Button className={classes.button} onClick={stop}>
                        Aufnahme stoppen
                    </Button>
                )}
            </Box>
        </Box>
    );
};

export default ClosePulseAI;