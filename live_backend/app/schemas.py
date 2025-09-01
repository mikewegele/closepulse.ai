from typing import Optional, Any, Dict

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class AskResponse(BaseModel):
    response: str
    duration: float
    conversation_id: Optional[str] = None


class TLResponse(BaseModel):
    response: Any
    duration: float
    conversation_id: Optional[str] = None


class AnalyzeResponse(BaseModel):
    suggestions: Any = Field(..., description="JSON-Array oder Modell-Output für Vorschläge")
    trafficLight: Dict[str, str]
    durations: Dict[str, float]
    conversation_id: Optional[str] = None
