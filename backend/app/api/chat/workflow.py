DEFAULT_CHAT_WORKFLOW = {
    "id": "customer-chat-agent",
    "nodes": [
        {"id": "start", "type": "trigger"},
        {"id": "input-guard", "type": "agent", "name": "presidio_ner_guard"},
        {"id": "profanity-check", "type": "agent", "name": "profanity_guard"},
        {"id": "context-enrich", "type": "agent", "name": "context_setter"},
        {"id": "sentiment-analysis", "type": "agent", "name": "sentiment_analyzer"},
        {"id": "main-llm", "type": "llm", "name": "main_llm"},
        {"id": "output-guard", "type": "agent", "name": "output_guard"},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"source": "start", "target": "input-guard"},
        {"source": "input-guard", "target": "profanity-check"},
        {"source": "profanity-check", "target": "context-enrich"},
        {"source": "context-enrich", "target": "sentiment-analysis"},
        {"source": "sentiment-analysis", "target": "main-llm"},
        {"source": "main-llm", "target": "output-guard"},
        {"source": "output-guard", "target": "end"},
    ],
}
