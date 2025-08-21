# backend/main.py
import os
import time
from datetime import date
from io import BytesIO

import openai
from agents import Runner
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from closepulse_agents import main_agent, traffic_light_agent

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

runner = Runner()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    t0 = time.perf_counter()
    audio_data = await file.read()
    wav_io = BytesIO(audio_data)
    transcription = openai.audio.transcriptions.create(
        file=("audio.wav", wav_io, "audio/wav"),
        model="whisper-1",
        language="de"
    )
    dt = time.perf_counter() - t0
    print(f"/transcribe {dt:.3f}s")
    return {"text": transcription.text, "duration": dt}


@app.post("/ask")
async def ask_agent(messages: list[dict]):
    t0 = time.perf_counter()
    messages.append({"role": "system", "content": f"Heute ist der {date.today().isoformat()}"})
    result = await runner.run(main_agent, messages)
    dt = time.perf_counter() - t0
    print(f"/ask {dt:.3f}s")
    return {"response": result.final_output, "duration": dt}


@app.post("/trafficLight")
async def traffic_light(messages: list[dict]):
    t0 = time.perf_counter()
    messages.append({"role": "system", "content": f"Heute ist der {date.today().isoformat()}"})
    result = await runner.run(traffic_light_agent, messages)
    dt = time.perf_counter() - t0
    print(f"/trafficLight {dt:.3f}s")
    return {"response": result.final_output, "duration": dt}
