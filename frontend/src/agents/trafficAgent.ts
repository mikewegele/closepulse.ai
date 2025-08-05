import {Agent, run} from '@openai/agents';
import {AMP_CHECKER_PROMPT} from "./prompts/trafficAgentPrompt.ts";

const ampelAgent = new Agent({
    name: 'AmpelChecker',
    instructions: AMP_CHECKER_PROMPT,
});

export const checkAmpelStatus = async (text: string) => {
    const result = await run(ampelAgent, text);
    try {
        return JSON.parse(result.finalOutput);
    } catch (e) {
        console.error("Fehler beim Parsen:", result.finalOutput);
        return {status: "yellow", reason: "Konnte nicht ausgewertet werden"};
    }
};
