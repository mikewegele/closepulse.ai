import os
from dotenv import load_dotenv
import openai
import sounddevice as sd
import numpy as np
import scipy.io.wavfile
from io import BytesIO
import collections
import webrtcvad
from agents import Runner
from datetime import date

from closepulse_agents import main_agent

# ========================== Init ==========================
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ======================= Runner =======================
runner = Runner()

def run_agent_with_context(context):
    context_with_today = context.copy()
    context_with_today.append({"role": "system", "content": f"Heute ist der {date.today().isoformat()}"})
    result = runner.run_sync(main_agent, context_with_today)
    return result.final_output

# ======================= Aufnahme mit VAD =======================
def record_until_silence(silence_limit_sec=2, fs=16000):
    vad = webrtcvad.Vad(2)  # Aggressivität 0-3
    frame_duration_ms = 30
    frame_size = int(fs * frame_duration_ms / 1000)
    silence_frames_limit = int(silence_limit_sec * 1000 / frame_duration_ms)

    recording = []
    silent_frames = 0

    with sd.InputStream(samplerate=fs, channels=1, dtype='int16') as stream:
        print("🎤 Sprich jetzt...")
        while True:
            data, _ = stream.read(frame_size)
            pcm_data = data.tobytes()
            is_speech = vad.is_speech(pcm_data, fs)

            if is_speech:
                silent_frames = 0
                recording.append(data)
            else:
                silent_frames += 1
                if silent_frames > silence_frames_limit:
                    break

    print("🎤 Aufnahme beendet.")
    audio = np.concatenate(recording)
    return audio, fs

# =================== Transkription =====================
def transcribe_with_openai_whisper():
    audio, fs = record_until_silence()

    if len(audio) < fs * 0.1:
        print("⚠️ Aufnahme zu kurz, bitte nochmal sprechen.")
        return ""

    wav_io = BytesIO()
    scipy.io.wavfile.write(wav_io, fs, audio)
    wav_io.seek(0)

    print("🌀 Sende Audio an OpenAI Whisper...")

    transcription = openai.audio.transcriptions.create(
        file=("audio.wav", wav_io, "audio/wav"),
        model="whisper-1",
        language="de"
    )

    text = transcription.text
    print(f"🗣️ Erkannt: {text}")
    return text

# ========================== Main ==========================
def main():
    print("📞 Assistent gestartet")

    conversation_context = [
        {"role": "system", "content": main_agent.instructions},
        {"role": "user", "content": "Hallo"}
    ]

    while True:
        user_input = transcribe_with_openai_whisper()
        if not user_input.strip():
            continue

        conversation_context.append({"role": "user", "content": user_input})

        response = run_agent_with_context(conversation_context)
        print(f"Assistent: {response}")

        conversation_context.append({"role": "assistant", "content": response})

        if "beenden" in user_input.lower():
            print("👋 Assistent beendet.")
            break

if __name__ == "__main__":
    main()
