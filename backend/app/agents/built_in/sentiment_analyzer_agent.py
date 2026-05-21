# backend/app/agents/built_in/sentiment_analyzer_agent.py
from app.agents.base import BaseAgent, AgentInput, AgentOutput
import time

class SentimentAnalyzerAgent(BaseAgent):
    name = "sentiment_analyzer"
    description = "Analyzes sentiment of user message"
    version = "1.0.0"

    async def run(self, inp: AgentInput) -> AgentOutput:
        start = time.time()
        
        # Simple rule-based + can be replaced with small LLM
        text = inp.content.lower()
        score = 0.5
        sentiment = "neutral"
        
        if any(word in text for word in ["bad", "terrible", "angry", "issue", "problem"]):
            sentiment = "negative"
            score = 0.2
        elif any(word in text for word in ["great", "excellent", "thanks", "good"]):
            sentiment = "positive"
            score = 0.85

        return AgentOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            metadata={"sentiment": sentiment, "score": score},
            latency_ms=round((time.time() - start) * 1000, 2)
        )