import React, {useRef, useState} from "react";
import {Box, Button, Typography} from "@mui/material";
import {makeStyles} from "tss-react/mui";
import axios from "axios";

const useStyles = makeStyles()(() => ({
    root: {
        height: "100vh",
        width: "100vw",
        background:
            "linear-gradient(135deg, #FDEFF9 0%, #E2F0CB 50%, #FFC3A0 100%)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
        fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
        color: "#3A3A3A",
    },
    glassContainer: {
        backdropFilter: "blur(12px)",
        background: "rgba(255, 255, 255, 0.7)",
        borderRadius: 20,
        width: "90vw",
        maxWidth: 700,
        maxHeight: "80vh",
        overflowY: "auto",
        padding: "2rem",
        boxShadow: "0 10px 30px rgba(255, 183, 130, 0.3)",
        display: "flex",
        flexDirection: "column",
    },
    header: {
        fontSize: "3rem",
        fontWeight: 700,
        marginBottom: "1.5rem",
        textAlign: "center",
        userSelect: "none",
        color: "#FF6F61",
    },
    chat: {
        flexGrow: 1,
        display: "flex",
        flexDirection: "column",
        gap: "1.2rem",
        overflowY: "auto",
        paddingRight: "0.5rem",
    },
    messageUser: {
        alignSelf: "flex-end",
        background: "#FFD9C0",
        color: "#5A3E36",
        padding: "0.8rem 1.2rem",
        borderRadius: "20px 20px 0 20px",
        maxWidth: "75%",
        fontSize: "1.3rem",
        lineHeight: 1.4,
        userSelect: "text",
        wordBreak: "break-word",
        boxShadow: "0 3px 10px rgba(0,0,0,0.1)",
    },
    messageAssistant: {
        alignSelf: "flex-start",
        background: "#D2F8D2",
        color: "#2B4F2B",
        padding: "0.8rem 1.2rem",
        borderRadius: "20px 20px 20px 0",
        maxWidth: "75%",
        fontSize: "1.3rem",
        lineHeight: 1.4,
        userSelect: "text",
        wordBreak: "break-word",
        boxShadow: "0 3px 10px rgba(0,0,0,0.1)",
    },
    systemMessage: {
        alignSelf: "center",
        color: "#7D7D7D",
        fontStyle: "italic",
        fontSize: "1rem",
        marginBottom: "1rem",
    },
    button: {
        marginTop: "1.8rem",
        alignSelf: "center",
        padding: "1rem 3rem",
        fontSize: "1.5rem",
        fontWeight: 600,
        borderRadius: 50,
        textTransform: "none",
        boxShadow: "0 8px 24px rgba(255, 111, 97, 0.5)",
        cursor: "pointer",
        userSelect: "none",
        backgroundColor: "#FF6F61",
        color: "white",
        "&:hover": {
            backgroundColor: "#E55A4F",
        },
    },
    pulse: {
        display: "inline-block",
        width: 14,
        height: 14,
        borderRadius: "50%",
        marginLeft: 10,
        backgroundColor: "#FF6F61",
        animation: "pulse 2s infinite",
        "@keyframes pulse": {
            "0%": {transform: "scale(1)", opacity: 1},
            "50%": {transform: "scale(1.5)", opacity: 0.6},
            "100%": {transform: "scale(1)", opacity: 1},
        },
    },
}));

type Message = {
    role: "user" | "assistant" | "system";
    content: string;
};

export const ClosePulseAI = () => {
    const {classes} = useStyles();
    const [messages, setMessages] = useState<Message[]>([
        {role: "system", content: "Sag mir etwas oder drücke Start."},
    ]);
    const [recording, setRecording] = useState(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const silenceTimer = useRef<NodeJS.Timeout | null>(null);
    const chunks = useRef<Blob[]>([]);
    const audioContextRef = useRef<AudioContext | null>(null);
    const analyserRef = useRef<AnalyserNode | null>(null);

    const SILENCE_THRESHOLD = 60;
    const SILENCE_DURATION = 10000;

    const startRecording = async () => {
        if (recording) return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            console.log("Stream erhalten", stream);
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            chunks.current = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunks.current.push(e.data);
            };

            mediaRecorder.onstart = () => {
                console.log("Recorder started");
                setRecording(true);
            };

            mediaRecorder.onstop = async () => {
                console.log("Recorder stopped");
                setRecording(false);
                if (silenceTimer.current) {
                    clearTimeout(silenceTimer.current);
                    silenceTimer.current = null;
                }
                if (audioContextRef.current) {
                    await audioContextRef.current.close();
                    audioContextRef.current = null;
                    analyserRef.current = null;
                }

                const blob = new Blob(chunks.current, {type: "audio/webm"});
                const formData = new FormData();
                formData.append("file", blob, "recording.webm");

                try {
                    const transcribeRes = await axios.post(
                        "http://localhost:8000/transcribe",
                        formData,
                        {headers: {"Content-Type": "multipart/form-data"}}
                    );

                    const userText = transcribeRes.data.text;
                    if (!userText) return;

                    const newUserMessage = {role: "user", content: userText};

                    const askRes = await axios.post(
                        "http://localhost:8000/ask",
                        [...messages.filter((m) => m.role !== "system"), newUserMessage]
                    );

                    const assistantText = askRes.data.response;

                    setMessages((prev) => [...prev, newUserMessage, {role: "assistant", content: assistantText}]);
                } catch (error) {
                    console.error("Fehler bei API", error);
                    setMessages((prev) => [...prev, {role: "assistant", content: "Fehler bei der Verbindung."}]);
                }
            };

            mediaRecorder.start(250);

            audioContextRef.current = new AudioContext();
            const audioCtx = audioContextRef.current;
            const micSource = audioCtx.createMediaStreamSource(stream);
            analyserRef.current = audioCtx.createAnalyser();
            analyserRef.current.fftSize = 512;
            micSource.connect(analyserRef.current);

            const checkSilence = () => {
                if (!analyserRef.current) return;
                console.log("HERE 234234")
                const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
                analyserRef.current.getByteTimeDomainData(dataArray);

                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) {
                    const val = Math.abs(dataArray[i] - 128);
                    sum += val;
                }

                console.log(sum, dataArray)
                const avgVolume = sum / dataArray.length;
                console.log("avgVolume:", avgVolume);

                if (avgVolume < SILENCE_THRESHOLD) {
                    if (!silenceTimer.current) {
                        console.log("Stille erkannt, Timer startet");
                        silenceTimer.current = setTimeout(() => {
                            console.log("Stille-Timeout, Aufnahme stoppen");
                            if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
                                mediaRecorderRef.current.stop();
                                mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
                            }
                        }, SILENCE_DURATION);
                    }
                } else {
                    if (silenceTimer.current) {
                        clearTimeout(silenceTimer.current);
                        silenceTimer.current = null;
                        console.log("Laut genug, Timer abgebrochen");
                    }
                }

                if (recording) {
                    requestAnimationFrame(checkSilence);
                }
            };

            requestAnimationFrame(checkSilence);
        } catch (error) {
            console.error("Fehler beim Starten der Aufnahme:", error);
            setMessages((prev) => [...prev, {role: "assistant", content: "Fehler beim Zugriff auf Mikrofon."}]);
        }
    };


    const stopRecording = () => {
        if (!recording) return;
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
            mediaRecorderRef.current.stop();
            mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
        }
    };

    const latestUserMessage = [...messages].reverse().find((m) => m.role === "user");
    const latestAssistantMessage = [...messages].reverse().find((m) => m.role === "assistant");
    const systemMessages = messages.filter((m) => m.role === "system");

    return (
        <Box className={classes.root}>
            <Box className={classes.glassContainer}>
                <Typography className={classes.header} component="h1">
                    closepulse.ai
                    {recording && <span className={classes.pulse}/>}
                </Typography>

                <Box className={classes.chat}>
                    {systemMessages.map((msg, i) => (
                        <Typography key={"sys" + i} className={classes.systemMessage}>
                            {msg.content}
                        </Typography>
                    ))}

                    {latestUserMessage && (
                        <Typography className={classes.messageUser} style={{whiteSpace: "pre-line"}}>
                            <strong>User: </strong>
                            {latestUserMessage.content}
                        </Typography>
                    )}

                    {latestAssistantMessage && (
                        <Typography className={classes.messageAssistant} style={{whiteSpace: "pre-line"}}>
                            <strong>Assistant: </strong>
                            {latestAssistantMessage.content}
                        </Typography>
                    )}
                </Box>

                {!recording ? (
                    <Button className={classes.button} onClick={startRecording}>
                        Start Aufnahme
                    </Button>
                ) : (
                    <Button
                        className={classes.button}
                        onClick={stopRecording}
                        style={{backgroundColor: "#E55A4F"}}
                    >
                        Aufnahme stoppen
                    </Button>
                )}
            </Box>
        </Box>
    );
};

export default ClosePulseAI;
