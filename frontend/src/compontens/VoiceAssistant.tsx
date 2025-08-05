import React, { useRef, useState } from "react";
import { Button, Typography, Box } from "@mui/material";
import { makeStyles } from "tss-react/mui";
import axios from "axios";

const useStyles = makeStyles()(() => ({
  root: {
    height: "100vh",
    width: "100vw",
    background: "linear-gradient(135deg, #4b6cb7 0%, #182848 100%)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "2rem",
    fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
    color: "white",
  },
  glassContainer: {
    backdropFilter: "blur(20px)",
    background: "rgba(255, 255, 255, 0.1)",
    borderRadius: "20px",
    border: "1px solid rgba(255, 255, 255, 0.3)",
    width: "90vw",
    maxWidth: 700,
    maxHeight: "80vh",
    overflowY: "auto",
    padding: "2rem",
    boxShadow: "0 8px 32px 0 rgba(31, 38, 135, 0.37)",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    fontSize: "3rem",
    fontWeight: "700",
    marginBottom: "1.5rem",
    textAlign: "center",
    userSelect: "none",
    textShadow: "0 2px 10px rgba(0,0,0,0.4)",
  },
  chat: {
    flexGrow: 1,
    display: "flex",
    flexDirection: "column",
    gap: "1.5rem",
    overflowY: "auto",
    paddingRight: "0.5rem",
  },
  messageUser: {
    alignSelf: "flex-end",
    background: "rgba(255, 255, 255, 0.2)",
    color: "#e0e0e0",
    padding: "0.8rem 1.2rem",
    borderRadius: "20px 20px 0 20px",
    maxWidth: "75%",
    fontSize: "1.3rem",
    lineHeight: 1.4,
    userSelect: "text",
    wordBreak: "break-word",
    boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
  },
  messageAssistant: {
    alignSelf: "flex-start",
    background: "rgba(255, 255, 255, 0.35)",
    color: "#222",
    padding: "0.8rem 1.2rem",
    borderRadius: "20px 20px 20px 0",
    maxWidth: "75%",
    fontSize: "1.3rem",
    lineHeight: 1.4,
    userSelect: "text",
    wordBreak: "break-word",
    boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
  },
  systemMessage: {
    alignSelf: "center",
    color: "rgba(255,255,255,0.7)",
    fontStyle: "italic",
    fontSize: "1rem",
    marginBottom: "1rem",
  },
  button: {
    marginTop: "1.8rem",
    alignSelf: "center",
    padding: "1rem 3rem",
    fontSize: "1.5rem",
    fontWeight: "600",
    borderRadius: "50px",
    textTransform: "none",
    boxShadow: "0 8px 24px rgba(0,0,0,0.2)",
    transition: "background-color 0.3s ease",
    cursor: "pointer",
    userSelect: "none",
  },
  buttonPrimary: {
    backgroundColor: "#4b6cb7",
    color: "white",
    "&:hover": {
      backgroundColor: "#3a54a1",
    },
  },
  buttonError: {
    backgroundColor: "#d32f2f",
    color: "white",
    "&:hover": {
      backgroundColor: "#9a2424",
    },
  },
}));

type Message = {
  role: "user" | "assistant" | "system";
  content: string;
};

export const VoiceAssistant = () => {
  const { classes, cx } = useStyles();
  const [messages, setMessages] = useState<Message[]>([
    { role: "system", content: "Starte Konversation" },
  ]);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const silenceTimer = useRef<NodeJS.Timeout | null>(null);
  const chunks = useRef<Blob[]>([]);

  const startRecording = async () => {
    if (recording) return;

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorderRef.current = mediaRecorder;
    chunks.current = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.current.push(e.data);
    };

    mediaRecorder.onstart = () => {
      setRecording(true);
    };

    mediaRecorder.onstop = async () => {
      setRecording(false);
      if (silenceTimer.current) {
        clearTimeout(silenceTimer.current);
        silenceTimer.current = null;
      }

      const blob = new Blob(chunks.current, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("file", blob, "recording.wav");

      try {
        const transcribeRes = await axios.post("http://localhost:8000/transcribe", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });

        const userText = transcribeRes.data.text;
        if (!userText) return;

        const updated = [...messages, { role: "user", content: userText }];
        setMessages(updated);

        const askRes = await axios.post("http://localhost:8000/ask", updated);
        const assistantText = askRes.data.response;

        setMessages([
          ...updated,
          {
            role: "assistant",
            content: assistantText,
          },
        ]);
      } catch {
        setMessages((m) => [...m, { role: "assistant", content: "Fehler bei der Verbindung." }]);
      }
    };

    mediaRecorder.start(250);

    const audioCtx = new AudioContext();
    const micSource = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    micSource.connect(analyser);
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const SILENCE_THRESHOLD = 10;
    const SILENCE_DELAY = 2000;

    const checkSilence = () => {
      analyser.getByteFrequencyData(dataArray);
      const volume = dataArray.reduce((a, b) => a + b) / dataArray.length;

      if (volume < SILENCE_THRESHOLD) {
        if (!silenceTimer.current) {
          silenceTimer.current = setTimeout(() => {
            mediaRecorder.stop();
            stream.getTracks().forEach((track) => track.stop());
            audioCtx.close();
          }, SILENCE_DELAY);
        }
      } else {
        if (silenceTimer.current) {
          clearTimeout(silenceTimer.current);
          silenceTimer.current = null;
        }
      }

      if (recording) {
        requestAnimationFrame(checkSilence);
      }
    };

    requestAnimationFrame(checkSilence);
  };

  return (
    <Box className={classes.root}>
      <Box className={classes.glassContainer}>
        <Typography className={classes.header} component="h1">
          🧠 Voice Assistant
        </Typography>

        <Box className={classes.chat}>
          {messages.map((msg, index) => (
            <Typography
              key={index}
              className={
                msg.role === "user"
                  ? classes.messageUser
                  : msg.role === "assistant"
                  ? classes.messageAssistant
                  : classes.systemMessage
              }
              style={{ whiteSpace: "pre-line" }}
            >
              {msg.role !== "system" && (
                <strong style={{ textTransform: "capitalize", marginRight: 8 }}>
                  {msg.role}:
                </strong>
              )}
              {msg.content}
            </Typography>
          ))}
        </Box>

        <Button
          className={cx(
            classes.button,
            recording ? classes.buttonError : classes.buttonPrimary
          )}
          onClick={startRecording}
          disabled={recording}
        >
          {recording ? "Sprich..." : "Start"}
        </Button>
      </Box>
    </Box>
  );
};

export default VoiceAssistant;
