import React, {useRef, useState} from "react";
import {Box, Button, Typography} from "@mui/material";
import {makeStyles} from "tss-react/mui";
import axios from "axios";
import {checkAmpelStatus} from "../agents/trafficAgent.ts";
import {AmpelSingleLight} from "./AmpelDisplay.tsx";

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

export const ClosePulseAI: React.FC = () => {
    const {classes} = useStyles();
    const [recording, setRecording] = useState(false);
    const [userText, setUserText] = useState("");
    const [assistantText, setAssistantText] = useState("");
    const [ampelStatus, setAmpelStatus] = useState<"green" | "yellow" | "red" | null>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    const startRecording = async () => {
        const stream = await navigator.mediaDevices.getUserMedia({audio: true});
        const recorder = new MediaRecorder(stream);
        mediaRecorderRef.current = recorder;
        chunksRef.current = [];

        recorder.ondataavailable = (e) => {
            if (e.data.size > 0) chunksRef.current.push(e.data);
        };

        recorder.onstop = handleUpload;
        recorder.start();
        setRecording(true);
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current) {
            mediaRecorderRef.current.stop();
            mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
            setRecording(false);
        }
    };

    const handleUpload = async () => {
        const blob = new Blob(chunksRef.current, {type: "audio/webm"});
        const formData = new FormData();
        formData.append("file", blob, "recording.webm");

        try {
            const transcribe = await axios.post("http://localhost:8000/transcribe", formData, {
                headers: {"Content-Type": "multipart/form-data"},
            });
            const text = transcribe.data.text;
            if (!text) return;

            setUserText(text);

            const ask = await axios.post("http://localhost:8000/ask", [{role: "user", content: text}]);
            const reply = ask.data.response;
            setAssistantText(reply);

            const {status} = await checkAmpelStatus(reply);
            setAmpelStatus(status);
        } catch (err) {
            console.error("API-Fehler:", err);
        }
    };

    return (
        <Box className={classes.root}>
            <Box className={classes.container}>
                <Typography variant="h4">closepulse.ai</Typography>

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
                    <Button className={classes.button} onClick={startRecording}>
                        Aufnahme starten
                    </Button>
                ) : (
                    <Button className={classes.button} onClick={stopRecording}>
                        Aufnahme stoppen
                    </Button>
                )}
            </Box>
        </Box>
    );
};

export default ClosePulseAI;
