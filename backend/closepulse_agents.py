from agents import Agent

from prompts import SALES_ASSISTANT_PROMPT, CONTEXT_ASSISTANT_PROMPT, MAIN_AGENT_PROMPT, UNDERSTANDING_AGENT_PROMPT

context_agent = Agent(
    name="ContextAgent",
    instructions=CONTEXT_ASSISTANT_PROMPT,
)

sales_assistant_agent = Agent(
    name="SalesAssistant",
    instructions=SALES_ASSISTANT_PROMPT,
)

understanding_agent = Agent(
    name="UnderstandingAgent",
    instructions=UNDERSTANDING_AGENT_PROMPT,
)

main_agent = Agent(
    name="MainAgent",
    instructions=MAIN_AGENT_PROMPT,
    handoffs=[context_agent, understanding_agent, sales_assistant_agent],
)
