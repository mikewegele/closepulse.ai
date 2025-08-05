import React, { useState, useRef } from "react";
import axios from "axios";

const VoiceAssistant: React.FC = () => {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: "system", content: "Starte Konversation" }
  ]);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunks: Blob[] = [];

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorderRef.current = mediaRecorder;
    audioChunks.length = 0;

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
      const formData = new FormData();
      formData.append("file", audioBlob, "audio.wav");

      const transcribeRes = await axios.post("http://localhost:8000/transcribe", formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });

      const userMessage = transcribeRes.data.text;
      const updatedMessages = [...messages, { role: "user", content: userMessage }];
      setMessages(updatedMessages);

      const askRes = await axios.post("http://localhost:8000/ask", updatedMessages);
      const assistantMessage = askRes.data.response;
      setMessages([...updatedMessages, { role: "assistant", content: assistantMessage }]);
    };

    mediaRecorder.start();
    setRecording(true);
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  return (
    <div>
      <h2>🧠 Voice Assistant</h2>
      <button onClick={recording ? stopRecording : startRecording}>
        {recording ? "Stop" : "Start"}
      </button>

      <ul>
        {messages.map((m, i) => (
          <li key={i}><strong>{m.role}:</strong> {m.content}</li>
        ))}
      </ul>
    </div>
  );
};

export default VoiceAssistant;
