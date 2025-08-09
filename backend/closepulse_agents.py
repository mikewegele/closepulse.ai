from agents import Agent

from prompts import SALES_ASSISTANT_PROMPT, TRAFFIC_LIGHT_AGENT_PROMPT

sales_assistant_agent = Agent(
    name="SalesAssistantDep",
    instructions=SALES_ASSISTANT_PROMPT,
)

main_agent = Agent(
    name="SalesAssistant",
    instructions=SALES_ASSISTANT_PROMPT,
)

traffic_light_agent = Agent(
    name="TrafficLightAgent",
    instructions=TRAFFIC_LIGHT_AGENT_PROMPT,
)
