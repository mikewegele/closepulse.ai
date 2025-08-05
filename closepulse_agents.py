from agents import Agent
from prompts import SALES_ASSISTANT_PROMPT

main_agent = Agent(
    name="SalesAssistant",
    instructions=SALES_ASSISTANT_PROMPT,
)