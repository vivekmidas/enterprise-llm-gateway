import json
import re
import structlog
from typing import Any

from app.knowledge.domain_rag_v1.domains.legal.llm import DomainLLM

logger = structlog.get_logger(__name__)


def _clean_json_string(raw: str) -> str:
    """Strip markdown codeblock wrappers if present."""
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


MINIMAL_STOP_WORDS = {
    "the", "of", "and", "in", "to", "a", "an", "for", "with", "on", "at", "by", "from",
    "or", "as", "is", "it", "that", "this", "be", "are", "was", "were", "v", "vs", "re",
    "court", "high", "state", "case", "suit", "appeal", "order", "judge", "justice",
    "no", "number", "dated", "learned", "honble", "mr", "mrs", "ms", "pvt", "ltd",
}


def _is_grounded_in_text(val: Any, raw_text_lower: str) -> bool:
    """
    Check if the extracted value is grounded in the raw document text.
    Rejects hallucinations if zero key non-stopword tokens match or match ratio < 40%.
    """
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, (int, float)):
        return str(val) in raw_text_lower

    if isinstance(val, str):
        val_str = val.strip().lower()
        if not val_str or val_str in {"null", "n/a", "none", "unknown", "undefined", "plaintiffs", "defendants", "first defendant", "second defendant"}:
            return False
        # Reject bracketed template placeholders (e.g. [Name], Advocate [Name], <Date>)
        if re.search(r"\[.*?\]|<.*?>", val_str):
            return False

        # Exact substring check
        if val_str in raw_text_lower:
            return True

        # Extract non-stopword tokens (length >= 3)
        tokens = [t for t in re.split(r"\W+", val_str) if len(t) >= 3]
        key_tokens = [t for t in tokens if t not in MINIMAL_STOP_WORDS]

        # Fallback to general tokens if all words are stop-words
        check_tokens = key_tokens if key_tokens else tokens
        if not check_tokens:
            return True

        # Count matched key tokens in source text
        matched = sum(1 for t in check_tokens if t in raw_text_lower)
        if matched == 0:
            return False

        # Require at least 40% token overlap for multi-word strings
        match_ratio = matched / len(check_tokens)
        return match_ratio >= 0.4


    if isinstance(val, list):
        grounded_list = [item for item in val if _is_grounded_in_text(item, raw_text_lower)]
        return len(grounded_list) > 0

    if isinstance(val, dict):
        grounded_dict = {k: v for k, v in val.items() if _is_grounded_in_text(v, raw_text_lower)}
        return len(grounded_dict) > 0

    return True


def _filter_value(v: Any, raw_text_lower: str) -> Any:
    """
    Recursively filter a value at the leaf level.
    - Strings/numbers: checked for grounding, returned as-is or dropped (None)
    - Dicts: recursively filtered, kept if any leaf survives
    - Lists: each item filtered, kept if any item survives
    Returns None if value should be dropped.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v if (str(v) in raw_text_lower) else None
    if isinstance(v, str):
        return v if _is_grounded_in_text(v, raw_text_lower) else None
    if isinstance(v, list):
        filtered = []
        for item in v:
            if isinstance(item, dict):
                sub = _filter_value(item, raw_text_lower)
                if sub:  # non-empty dict
                    filtered.append(sub)
            else:
                sub = _filter_value(item, raw_text_lower)
                if sub is not None:
                    filtered.append(sub)
        return filtered if filtered else None
    if isinstance(v, dict):
        result = {}
        for dk, dv in v.items():
            filtered_dv = _filter_value(dv, raw_text_lower)
            if filtered_dv is not None and filtered_dv != [] and filtered_dv != {}:
                result[dk] = filtered_dv
        return result if result else None
    return v


def filter_ungrounded_fields(fields_dict: dict[str, Any], raw_text: str) -> dict[str, Any]:
    """
    Filter out fields whose leaf values have zero grounding in raw_text.
    Nested dicts and lists are filtered at the leaf node level — a parent
    is only dropped if ALL its children are ungrounded.
    """
    if not isinstance(fields_dict, dict) or not raw_text:
        return {}

    raw_text_lower = raw_text.lower()
    filtered = {}

    for k, v in fields_dict.items():
        result = _filter_value(v, raw_text_lower)
        if result is not None and result != [] and result != {}:
            filtered[k] = result
        else:
            logger.info("rejecting_ungrounded_field", field_key=k, value=str(v)[:100])

    return filtered


class DomainExtractor:
    """Extracts domain knowledge from document text using an LLM.
    Supports schema-free comprehensive extraction with grounding verification.
    """

    def __init__(self, llm: DomainLLM | None = None):
        self.llm = llm or DomainLLM()

    @classmethod
    def from_llm_profile(cls, llm_profile) -> "DomainExtractor":
        """
        Build a DomainExtractor using the tenant's LLMProfileDB settings.

        LLMProfileDB.settings shape:
          {
            "generation": { "url": "...", "model": "...", "api_key": "...", "provider": "..." },
            "search": { ... },
            "embedding": { ... }
          }

        Reads from the 'generation' section. Converts Ollama native chat URLs
        to OpenAI-compatible /v1 endpoint. Falls back to Ollama defaults on any error.
        """
        try:
            if llm_profile is None:
                return cls()

            s = llm_profile.settings or {}
            gen = s.get("generation") or {}

            raw_url = gen.get("url") or gen.get("base_url") or gen.get("endpoint")
            api_key = gen.get("api_key") or "ollama"
            model = gen.get("model") or llm_profile.name

            # Convert Ollama native URL to OpenAI-compatible /v1 endpoint
            # e.g. http://localhost:11434/api/chat → http://localhost:11434/v1
            base_url = None
            if raw_url:
                for suffix in ("/api/chat", "/api/generate", "/v1/chat/completions"):
                    if raw_url.endswith(suffix):
                        raw_url = raw_url[: -len(suffix)].rstrip("/")
                        break
                base_url = raw_url.rstrip("/") + "/v1"

            logger.info(
                "domain_extractor_profile_resolved",
                profile_name=llm_profile.name,
                model=model,
                base_url=base_url,
            )
            return cls(llm=DomainLLM(model=model, base_url=base_url, api_key=api_key))
        except Exception as exc:
            logger.warning("domain_extractor_profile_parse_failed", error=str(exc))
            return cls()

    async def extract_domain_knowledge(
        self,
        *,
        text: str,
        filename: str,
        domain_name: str,
        domain_key: str,
        schema_json: dict[str, Any] | None,
        system_prompt_template: str | None,
        user_prompt_template: str | None,
    ) -> dict[str, Any]:
        # Guard: skip if document text is empty or too short to be meaningful
        if not text or len(text.strip()) < 50:
            logger.warning(
                "domain_extraction_skipped_empty_text",
                filename=filename,
                text_length=len(text) if text else 0,
            )
            return {
                "domain_name": domain_name,
                "domain_key": domain_key,
                "extracted_fields": {},
                "extra_fields": {},
                "field_weights": {},
                "status_note": "Extraction skipped: document text was empty or too short.",
            }

        fields = (schema_json or {}).get("fields", [])

        # Build field_weights map (used for fallback reference)
        field_weights = {}
        for f in fields:
            key = f.get("key")
            weight = f.get("weight", 1.0)
            field_weights[key] = float(weight)

        sys_prompt = (
            "You are a precise document entity extractor.\n"
            "RULE 1: Extract ONLY values explicitly present in the provided Document Content.\n"
            "RULE 2: If a field value is NOT found in the document text, OMIT that field entirely "
            "— do NOT write null, do NOT write empty string.\n"
            "RULE 3: DO NOT use training data, prior knowledge, or inferred values.\n"
            "RULE 4: Use exact wording from the document for all extracted values.\n"
            "Return valid JSON only containing ONLY the fields you actually found."
        )

        # Truncate content — 80K chars covers ~60-page judgments with 40+ connected cases
        max_chars = 80_000
        content_snippet = text[:max_chars]
        logger.info(
            "domain_extraction_text_snapshot",
            filename=filename,
            content_snippet_length=len(content_snippet),
            content_preview=content_snippet[:200].replace("\n", " "),
        )

        # Skip schema-driven pass — go directly to free-extract.
        # Schema field keys constrain and bias the LLM, causing null-filled responses
        # or hallucinated values to fit schema keys. Free-extract lets the LLM discover
        # what is actually in the document without field name anchoring.
        logger.info(
            "domain_extraction_skipping_schema_using_free_extract",
            filename=filename,
            domain_key=domain_key,
            schema_field_count=len(fields),
        )
        return await self._free_extract(
            text=text,
            content_snippet=content_snippet,
            filename=filename,
            domain_name=domain_name,
            domain_key=domain_key,
            field_weights=field_weights,
            sys_prompt=sys_prompt,
        )

    async def _free_extract(
        self,
        *,
        text: str,
        content_snippet: str,
        filename: str,
        domain_name: str,
        domain_key: str,
        field_weights: dict[str, Any],
        sys_prompt: str,
    ) -> dict[str, Any]:
        """
        Schema-free comprehensive extraction.
        Produces a richly nested JSON covering all key entities in the document.
        The prompt adapts based on domain_key (legal = comprehensive judgment extraction).
        """
        if domain_key and "legal" in domain_key.lower():
            free_sys_prompt = (
                "You are a specialized legal document analyst.\n"
                "RULE 1: Extract ONLY factual information explicitly present in the document.\n"
                "RULE 2: Omit any field not found — do NOT write null, empty strings, or 0.\n"
                "RULE 3: NEVER write bracketed placeholders like '[Name]', '[Judge]', '[Advocate]', or '[Title]'. Extract exact real proper names or omit.\n"
                "RULE 4: For party names, extract actual names of people or companies, NOT generic roles like 'Plaintiffs' or 'Defendants'.\n"
                "RULE 5: Use exact wording from the document for all values.\n"
                "Return a single valid JSON object only."
            )
            free_user_prompt = (
                f"Document Filename: {filename}\n\n"
                f"Document Content:\n{content_snippet}\n\n"
                "Extract a comprehensive structured JSON from the above legal document.\n"
                "CRITICAL INSTRUCTIONS:\n"
                "- Omit any field not found in the document.\n"
                "- NEVER output bracketed placeholders like '[Name]', '[Advocate]', '[Judge]', or '[Date]'.\n"
                "- For parties, extract the exact names of people/entities, NOT generic role labels.\n"
                "- 'arguments' must contain actual legal arguments made by each side, NOT party names or facts.\n"
                "- 'legal_principles' must be legal propositions EXPLICITLY STATED or CONFIRMED by the court in this document only — not inferred.\n"
                "- 'number_of_connected_cases' must be an integer (number), not a string.\n\n"
                "Structure (omit any section not present):\n"
                "{\n"
                '  "document_type": "...",\n'
                '  "case_category": "...",\n'
                '  "court": {"name": "...", "jurisdiction": "...", "bench": ["..."]},\n'
                '  "judgment": {"type": "...", "reserved_on": "...", "pronounced_on": "...", "author": "..."},\n'
                '  "case_numbers": ["..."],\n'
                '  "lead_case": "...",\n'
                '  "number_of_connected_cases": 0,\n'
                '  "parties": {"appellant": {"name": "...", "type": "..."}, "respondents": [{"name": "...", "role": "..."}]},\n'
                '  "advocates": {"appellant": ["..."], "respondent": ["..."]},\n'
                '  "statutes": [{"act": "...", "sections": ["..."]}],\n'
                '  "legal_questions": [{"id": 1, "question": "..."}],\n'
                '  "facts": {"industry": "...", "business": "...", "assessment_issue": "..."},\n'
                '  "arguments": {"appellant": ["actual argument 1"], "respondent": ["actual argument 1"]},\n'
                '  "precedents_relied": [{"case": "...", "citation": "...", "principle": "..."}],\n'
                '  "findings": [{"issue": "...", "finding": "...", "reasoning": "..."}],\n'
                '  "questions_answered": [{"question": 1, "answered_in_favour_of": "..."}],\n'
                '  "decision": {"result": "...", "holding": "...", "costs": "..."},\n'
                '  "legal_principles": ["principle explicitly stated by court in this document"],\n'
                '  "keywords": ["..."]\n'
                "}\n"
                "Output ONLY the JSON. Omit fields not present in the document."
            )
        else:
            free_sys_prompt = sys_prompt
            free_user_prompt = (
                f"Document Filename: {filename}\n\n"
                f"Document Content:\n{content_snippet}\n\n"
                "Extract a comprehensive structured JSON of ALL key information in this document.\n"
                "Include all entities, parties, dates, amounts, decisions, references, and any other significant data.\n"
                "Use only what is explicitly stated. Omit fields not present.\n"
                'Return JSON: {"extracted_fields": { ... }}'
            )

        try:
            raw_response = await self.llm.complete(free_sys_prompt, free_user_prompt, temperature=0.0)
            cleaned = _clean_json_string(raw_response)
            parsed = json.loads(cleaned)

            # For legal domain, the LLM returns the full object directly (not wrapped)
            if domain_key and "legal" in domain_key.lower():
                extracted_fields = parsed if isinstance(parsed, dict) else {}
            else:
                extracted_fields = parsed.get("extracted_fields", parsed if isinstance(parsed, dict) else {})

            if not isinstance(extracted_fields, dict):
                extracted_fields = {}

            # Grounding verifier — leaf-level
            extracted_fields = filter_ungrounded_fields(extracted_fields, text)

            logger.info(
                "domain_free_extraction_completed",
                domain_key=domain_key,
                filename=filename,
                extracted_top_level_keys=list(extracted_fields.keys()),
            )

            return {
                "domain_name": domain_name,
                "domain_key": domain_key,
                "extracted_fields": extracted_fields,
                "extra_fields": {},
                "field_weights": field_weights,
                "extraction_mode": "schema_free_fallback",
                "debug_info": {
                    "system_prompt": free_sys_prompt,
                    "user_prompt": free_user_prompt,
                    "raw_response": raw_response,
                },
            }
        except Exception as exc:
            logger.warning("domain_free_extraction_failed", filename=filename, error=str(exc))
            return {
                "domain_name": domain_name,
                "domain_key": domain_key,
                "extracted_fields": {},
                "extra_fields": {},
                "field_weights": field_weights,
                "error": str(exc),
                "extraction_mode": "schema_free_fallback_failed",
            }
