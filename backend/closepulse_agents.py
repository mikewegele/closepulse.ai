from agents import Agent

from prompts import SALES_ASSISTANT_PROMPT, UNDERSTANDING_AGENT_PROMPT

sales_assistant_agent = Agent(
    name="SalesAssistant",
    instructions=SALES_ASSISTANT_PROMPT,
)

main_agent = Agent(
    name="MainAgent",
    instructions=UNDERSTANDING_AGENT_PROMPT,
    handoffs=[sales_assistant_agent],
)
