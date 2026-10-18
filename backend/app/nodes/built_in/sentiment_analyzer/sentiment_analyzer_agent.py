# backend/app/agents/built_in/sentiment_analyzer_agent.py
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
import time

class SentimentAnalyzerAgent(BaseNode ):
    name: str = "sentiment_analyzer"
    description: str = "Analyzes sentiment of user message"
    version: str = "1.0.0"

    async def init(self) -> None:
        await super().init()
        
    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        await super().validate_input(inp)
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="success"
        )
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        
        data_val = self.get_input_data(inp)
        strings = self.collect_strings(data_val)
        text = " ".join(strings).lower()
        
        score = 0.5
        sentiment = "neutral"
        
        if any(word in text for word in ["bad", "terrible", "angry", "issue", "problem"]):
            sentiment = "negative"
            score = 0.2
        elif any(word in text for word in ["great", "excellent", "thanks", "good"]):
            sentiment = "positive"
            score = 0.85

        out_data = self.set_output_data(inp, data_val)

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            start_time=start,
            end_time=time.time(),
            metadata={"sentiment": sentiment, "score": score},
            latency_ms=round((time.time() - start) * 1000, 2)
        )