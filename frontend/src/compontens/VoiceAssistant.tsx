import React, { useRef, useState } from "react";
import { Button, Typography, Box } from "@mui/material";
import { makeStyles } from "tss-react/mui";
import axios from "axios";

const useStyles = makeStyles()(() => ({
  root: {
    height: "100vh",
    width: "100vw",
    background:
      "rgba(255, 255, 255, 0.15)", // viel transparenter
    backdropFilter: "blur(40px)", // mehr Blur
    WebkitBackdropFilter: "blur(40px)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "3rem",
    fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
    color: "#111",
  },
  glassBox: {
    background: "rgba(255, 255, 255, 0.12)", // sehr durchsichtig
    boxShadow:
      "0 8px 32px 0 rgba(31, 38, 135, 0.12)", // zarter Schatten
    backdropFilter: "blur(30px)", // sehr starkes Blur
    WebkitBackdropFilter: "blur(30px)",
    borderRadius: "32px",
    border: "1px solid rgba(255, 255, 255, 0.25)", // dünner, heller Rand
    padding: "3rem 4rem",
    maxWidth: 700,
    width: "90vw",
    minHeight: 200,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  },
  header: {
    fontSize: "3.5rem",
    fontWeight: "800",
    marginBottom: "2.5rem",
    userSelect: "none",
    color: "#111",
    textShadow: "0 0 8px rgba(255 255 255 / 0.6)", // leicht leuchtend
  },
  resultText: {
    fontSize: "1.9rem",
    fontWeight: "700",
    textAlign: "center",
    lineHeight: 1.6,
    whiteSpace: "pre-line",
    color: "#222",
    textShadow: "0 0 4px rgba(255 255 255 / 0.7)", // leichter Glow
  },
  coloredWord: {
    fontWeight: "900",
    padding: "0 8px",
    borderRadius: "8px",
    color: "white",
    display: "inline-block",
    userSelect: "text",
    textShadow: "0 0 3px rgba(0,0,0,0.3)",
  },
  button: {
    marginTop: "3rem",
    padding: "1.2rem 4rem",
    fontSize: "1.5rem",
    fontWeight: "700",
    borderRadius: "60px",
    backgroundColor: "rgba(34, 34, 34, 0.7)",
    color: "white",
    border: "none",
    cursor: "pointer",
    userSelect: "none",
    transition: "background-color 0.3s ease",
    "&:hover": {
      backgroundColor: "rgba(34, 34, 34, 0.9)",
    },
    "&:disabled": {
      backgroundColor: "rgba(200, 200, 200, 0.4)",
      cursor: "not-allowed",
      color: "#888",
    },
  },
}));


// Funktion, die Ampelfarben in Text erkennt und spannt
const highlightTrafficColors = (text: string, classes: ReturnType<typeof useStyles>["classes"]) => {
  // Wörter und Farben definieren
  const colorsMap: { [key: string]: string } = {
    rot: "#d32f2f",
    rotlich: "#d32f2f",
    rotlicht: "#d32f2f",
    gelb: "#fbc02d",
    gelblicht: "#fbc02d",
    gelblicht: "#fbc02d",
    grün: "#388e3c",
    gruen: "#388e3c",
    grünlicht: "#388e3c",
    gruenlicht: "#388e3c",
  };

  // Text splitten in Wörter (inklusive Satzzeichen)
  const words = text.split(/(\s+|\b)/);

  return words.map((word, i) => {
    const key = word.toLowerCase().replace(/[^a-zäöüß]/g, "");
    if (colorsMap[key]) {
      return (
        <span
          key={i}
          className={classes.coloredWord}
          style={{ backgroundColor: colorsMap[key] }}
        >
          {word}
        </span>
      );
    }
    return word;
  });
};

export const VoiceAssistant = () => {
  const { classes } = useStyles();
  const [result, setResult] = useState<string | null>(null);
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
      setResult(null); // beim Start löschen
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
        if (!userText) {
          setResult("Keine Sprache erkannt.");
          return;
        }

        // Anfrage an KI mit nur dem Usertext
        const askRes = await axios.post("http://localhost:8000/ask", [{ role: "user", content: userText }]);
        setResult(askRes.data.response);
      } catch {
        setResult("Fehler bei der Verbindung.");
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
      <Box className={classes.glassBox}>
        <Typography className={classes.header}>🧠 Voice Assistant</Typography>

        <Typography className={classes.resultText}>
          {result ? highlightTrafficColors(result, classes) : "Bitte sprechen und warten..."}
        </Typography>

        <button
          className={classes.button}
          onClick={startRecording}
          disabled={recording}
          aria-label="Start Aufnahme"
        >
          {recording ? "Sprich..." : "Start"}
        </button>
      </Box>
    </Box>
  );
};

export default VoiceAssistant;
