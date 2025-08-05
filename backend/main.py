# backend/main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from agents import Runner
from closepulse_agents import main_agent
import openai
import os
from dotenv import load_dotenv
from datetime import date
import scipy.io.wavfile
from io import BytesIO

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

runner = Runner()
app = FastAPI()

# CORS für Zugriff vom React-Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    audio_data = await file.read()
    wav_io = BytesIO(audio_data)

    transcription = openai.audio.transcriptions.create(
        file=("audio.wav", wav_io, "audio/wav"),
        model="whisper-1",
        language="de"
    )

    return {"text": transcription.text}


@app.post("/ask")
async def ask_agent(messages: list[dict]):
    messages.append({"role": "system", "content": f"Heute ist der {date.today().isoformat()}"})
    result = await runner.run(main_agent, messages)
    return {"response": result.final_output}

