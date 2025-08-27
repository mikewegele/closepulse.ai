const API_BASE = "https://hidden-nonprofit-fe-ghost.trycloudflare.com"
export const ASK_URL = `${API_BASE}/ask`;
export const TL_URL = `${API_BASE}/trafficLight`;
export const TR_URL = `${API_BASE}/transcribe`;
export const ANALYZE_URL = `${API_BASE}/analyze`;
export const ANALYZE_FAST_URL = `${API_BASE}/analyze_fast`;


export const MAX_TURNS = 4; // keep context small
export const TIMESLICE_MS = 500; // MediaRecorder slice
export const MAX_AUDIO_SECONDS = 10; // only send last ~10s on stop