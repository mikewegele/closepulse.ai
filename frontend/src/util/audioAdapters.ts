import {useCallback, useEffect, useRef, useState} from "react";

export function useLocalMic(onStopCallback: (audioBlob: Blob) => void) {
    const [recording, setRecording] = useState(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    const start = useCallback(async () => {
        const stream = await navigator.mediaDevices.getUserMedia({audio: true});
        const recorder = new MediaRecorder(stream);
        mediaRecorderRef.current = recorder;
        chunksRef.current = [];

        recorder.ondataavailable = (e) => {
            if (e.data.size > 0) chunksRef.current.push(e.data);
        };

        recorder.onstop = () => {
            const blob = new Blob(chunksRef.current, {type: "audio/webm"});
            onStopCallback(blob);
        };

        recorder.start();
        setRecording(true);
    }, [onStopCallback]);

    const stop = useCallback(() => {
        if (mediaRecorderRef.current) {
            mediaRecorderRef.current.stop();
            mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
            setRecording(false);
        }
    }, []);

    return {recording, start, stop};
}

export function useWebRTCAudio(onStopCallback: (audioBlob: Blob) => void) {
    const [recording, setRecording] = useState(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);
    const pcRef = useRef<RTCPeerConnection | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const localStreamRef = useRef<MediaStream | null>(null);

    useEffect(() => {
        wsRef.current = new WebSocket("wss://your-signaling-server.example.com");
        wsRef.current.onmessage = async (msg) => {
            const data = JSON.parse(msg.data);
            if (!pcRef.current) return;

            if (data.sdp) {
                await pcRef.current.setRemoteDescription(new RTCSessionDescription(data.sdp));
                if (data.sdp.type === "offer") {
                    const answer = await pcRef.current.createAnswer();
                    await pcRef.current.setLocalDescription(answer);
                    wsRef.current?.send(JSON.stringify({sdp: pcRef.current.localDescription}));
                }
            } else if (data.ice) {
                await pcRef.current.addIceCandidate(new RTCIceCandidate(data.ice));
            }
        };

        return () => {
            wsRef.current?.close();
        };
    }, []);

    const start = useCallback(async () => {
        const pc = new RTCPeerConnection({
            iceServers: [{urls: "stun:stun.l.google.com:19302"}],
        });
        pcRef.current = pc;

        const stream = await navigator.mediaDevices.getUserMedia({audio: true});
        localStreamRef.current = stream;
        stream.getTracks().forEach((track) => pc.addTrack(track, stream));

        pc.onicecandidate = (event) => {
            if (event.candidate) {
                wsRef.current?.send(JSON.stringify({ice: event.candidate}));
            }
        };

        const recorder = new MediaRecorder(stream);
        mediaRecorderRef.current = recorder;
        chunksRef.current = [];

        recorder.ondataavailable = (e) => {
            if (e.data.size > 0) chunksRef.current.push(e.data);
        };

        recorder.onstop = () => {
            const blob = new Blob(chunksRef.current, {type: "audio/webm"});
            onStopCallback(blob);
            pc.close();
            pcRef.current = null;
        };

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        wsRef.current?.send(JSON.stringify({sdp: offer}));

        recorder.start();
        setRecording(true);
    }, [onStopCallback]);

    const stop = useCallback(() => {
        if (mediaRecorderRef.current) {
            mediaRecorderRef.current.stop();
        }
        if (localStreamRef.current) {
            localStreamRef.current.getTracks().forEach((t) => t.stop());
        }
        setRecording(false);
    }, []);

    return {recording, start, stop};
}