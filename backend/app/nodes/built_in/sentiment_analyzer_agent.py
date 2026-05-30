# backend/app/agents/built_in/sentiment_analyzer_agent.py
from app.nodes.base import BaseNode, NodeInput, NodeOutput
import time

class SentimentAnalyzerAgent(BaseNode ):
    name: str = "sentiment_analyzer"
    description: str = "Analyzes sentiment of user message"
    version: str = "1.0.0"

    async def run(self, inp: NodeInput) -> NodeOutput:
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

        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            start_time=start,
            end_time=time.time(),
            metadata={"sentiment": sentiment, "score": score},
            latency_ms=round((time.time() - start) * 1000, 2)
        )