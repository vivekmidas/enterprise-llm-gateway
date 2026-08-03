from __future__ import annotations
import json, re
from .prompts import build_prompt

def _extract_json(text: str) -> dict:
    
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise

class LegalDomainParser:
    def __init__(self, llm):
        self.llm = llm

    async def parse(self, document_text: str) -> dict:
        system_prompt, user_prompt = build_prompt(document_text)
        print("\n========== DOMAIN RAG V1.1 PROMPT ==========")
        print(system_prompt)
        print(user_prompt[:5000])
        print("========== END PROMPT ==========\n")
        raw = await self.llm.complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0)
        return _extract_json(raw)
