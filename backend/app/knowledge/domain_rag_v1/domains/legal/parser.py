from __future__ import annotations

import json
import re

from .prompts import LEGAL_SYSTEM_PROMPT, LEGAL_USER_TEMPLATE


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


class LegalDomainParser:
    def __init__(self, llm):
        self.llm = llm

    async def parse(self, document_text: str) -> dict:
        prompt = LEGAL_USER_TEMPLATE.replace("{{DOCUMENT}}", document_text)
        raw = await self.llm.complete(
            system_prompt=LEGAL_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.0,
        )
        return _extract_json(raw)
