import {OpenAI} from "openai";
import {Agent, run} from "@openai/agents";
import {AMP_CHECKER_PROMPT} from "./prompts/trafficAgentPrompt";

const apiKey = import.meta.env.VITE_OPENAI_API_KEY;

if (!apiKey) {
    throw new Error("VITE_OPENAI_API_KEY is not defined!");
}

const openai = new OpenAI({
    apiKey: apiKey,
    dangerouslyAllowBrowser: true,
});

const ampelAgent = new Agent({
    name: "AmpelChecker",
    instructions: AMP_CHECKER_PROMPT,
    llm: openai,
});

export const checkAmpelStatus = async (text: string) => {
    try {
        const result = await run(ampelAgent, text);
        return JSON.parse(result.finalOutput);
    } catch (e) {
        console.error("Fehler beim Parsen:", e);
        return {status: "yellow"};
    }
};
