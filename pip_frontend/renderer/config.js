export const ASK_URL = "http://localhost:8000/ask";
export const TL_URL = "http://localhost:8000/trafficLight";
export const TR_URL = "http://localhost:8000/transcribe";
export const ANALYZE_URL = "http://localhost:8000/analyze";

export const MAX_TURNS = 4; // keep context small
export const TIMESLICE_MS = 500; // MediaRecorder slice
export const MAX_AUDIO_SECONDS = 10; // only send last ~10s on stop