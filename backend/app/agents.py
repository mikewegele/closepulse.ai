import openai
from closepulse_agents import main_agent, traffic_light_agent, database_agent, combo_agent

from agents import Runner
from .config import settings

openai.api_key = settings.OPENAI_API_KEY
runner = Runner()

__all__ = ["runner", "main_agent", "traffic_light_agent", "database_agent", "combo_agent"]
