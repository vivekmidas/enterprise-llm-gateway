import json
import re
import structlog
from typing import Any

from app.knowledge.domain_rag_v1.domains.legal.llm import DomainLLM
# ==============================================================================
# LEGAL DOMAIN SOT INTEGRATION
# Prompts for free extraction are built using the Legal Domain SOT.
# ==============================================================================
from app.knowledge.legal_sot import build_free_extract_prompts


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


# =====================================================================
# BLOCK COMMENT: DYNAMIC PROMPT BUILDERS (SINGLE SOURCE OF TRUTH)
# Purpose:
# 1. format_fields_summary: Generates human-readable field definitions.
# 2. format_fields_json_schema: Generates dynamic target JSON structure from fields.
# 3. Ensures schema_json['fields'] is the sole source of truth for prompts and extraction.
# =====================================================================
def format_fields_summary(fields: list[dict[str, Any]] | None) -> str:
    """Format human-readable bullet list of schema fields."""
    if not fields:
        return "Extract all key entities, facts, and metadata."
    lines = []
    for f in fields:
        k = f.get("key", "")
        lbl = f.get("label", k)
        t = f.get("type", "string")
        d = f.get("description", "")
        lines.append(f"- {k} ({lbl}, {t}): {d}" if d else f"- {k} ({lbl}, {t})")
    return "\n".join(lines)


def format_fields_json_schema(fields: list[dict[str, Any]] | None) -> str:
    """Format target JSON schema structure dynamically from schema fields as single source of truth."""
    if not fields:
        return '{\n  "extracted_fields": { ... },\n  "extra_fields": { ... }\n}'

    extracted_spec: dict[str, Any] = {}
    for f in fields:
        k = f.get("key")
        if not k:
            continue
        ft = (f.get("type") or "string").lower()
        desc = f.get("description") or f.get("label") or k
        if k == "connected_cases":
            extracted_spec[k] = [
                {
                    "case": "<case number e.g. 2981 OF 1989>",
                    "plaintiff": "<petitioner/plaintiff name>",
                    "respondent": "<respondent/defendant name>",
                    "advocate": "<representing lawyer/advocate name if present>",
                    "date": "<decision/order date if present>",
                }
            ]
        elif ft in ("array", "list"):
            extracted_spec[k] = [f"<{desc}>"]
        elif ft in ("object", "dict"):
            extracted_spec[k] = {"...": f"<{desc}>"}
        elif ft in ("number", "integer", "float"):
            extracted_spec[k] = f"0.0 (<{desc}>)"
        elif ft in ("bool", "boolean"):
            extracted_spec[k] = f"true/false (<{desc}>)"
        else:
            extracted_spec[k] = f"<{desc}>"

    return json.dumps({
        "extracted_fields": extracted_spec,
        "extra_fields": {"<unmapped_extra_field>": "<value>"}
    }, indent=2)


class DomainExtractor:
    """Extracts domain knowledge from document text using an LLM.
    Supports schema-free comprehensive extraction with grounding verification.
    """

    def __init__(self, llm: DomainLLM | None = None):
        self.llm = llm or DomainLLM()

    @classmethod
    def from_llm_profile(cls, llm_profile: Any = None) -> "DomainExtractor":
        """
        Factory method to instantiate DomainExtractor bound to a customer's LLMProfileDB.
        """
        try:
            if llm_profile is None:
                return cls()

            s = llm_profile.settings or {}
            gen = s.get("generation") if isinstance(s.get("generation"), dict) else {}

            raw_url = gen.get("url") or gen.get("base_url") or gen.get("endpoint") or s.get("base_url") or s.get("url")
            api_key = gen.get("api_key") or s.get("api_key") or "ollama"
            model = gen.get("model") or gen.get("model_name") or s.get("model") or llm_profile.name

            base_url = None
            if raw_url:
                clean = str(raw_url).rstrip("/")
                if "generativelanguage.googleapis.com" in clean:
                    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
                else:
                    for suffix in ("/api/chat", "/api/generate", "/v1/chat/completions", "/chat/completions"):
                        if clean.endswith(suffix):
                            clean = clean[:-len(suffix)].rstrip("/")
                            break
                    base_url = clean if (clean.endswith("/v1") or clean.endswith("/openai")) else f"{clean}/v1"

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

        # Truncate content — 80K chars covers large multi-page documents
        max_chars = 80_000
        content_snippet = text[:max_chars]

        # =====================================================================
        # BLOCK COMMENT: PROMPT RESOLUTION (SINGLE SOURCE OF TRUTH)
        # Purpose:
        # 1. Resolves system prompt (custom template or default precise extractor).
        # 2. Dynamically derives fields_summary and fields_json_schema from fields.
        # 3. Renders user prompt template with dynamic schema structure.
        # =====================================================================
        fields_summary = format_fields_summary(fields)
        fields_json_schema = format_fields_json_schema(fields)

        if system_prompt_template and system_prompt_template.strip():
            logger.debug("domain_extractor_decision_sys_prompt", branch="custom_template", template_len=len(system_prompt_template))
            sys_prompt = (
                system_prompt_template
                .replace("{domain_name}", domain_name or "")
                .replace("{filename}", filename or "")
            )
        else:
            logger.debug("domain_extractor_decision_sys_prompt", branch="default_extractor")
            sys_prompt = (
                "You are a precise document entity extractor.\n"
                "RULE 1: Extract ONLY values explicitly present in the provided Document Content.\n"
                "RULE 2: If a field value is NOT found in the document text, OMIT that field entirely "
                "— do NOT write null, do NOT write empty string.\n"
                "RULE 3: DO NOT use training data, prior knowledge, or inferred values.\n"
                "RULE 4: Use exact wording from the document for all extracted values.\n"
                "Return valid JSON only containing ONLY the fields you actually found."
            )

        if user_prompt_template and user_prompt_template.strip():
            logger.debug("domain_extractor_decision_user_prompt", branch="custom_template", template_len=len(user_prompt_template))
            user_prompt = (
                user_prompt_template
                .replace("{filename}", filename or "")
                .replace("{fields_summary}", fields_summary)
                .replace("{fields_json_schema}", fields_json_schema)
                .replace("{content}", content_snippet)
                .replace("{content_snippet}", content_snippet)
                .replace("{domain_name}", domain_name or "")
            )
        else:
            if fields:
                logger.debug("domain_extractor_decision_user_prompt", branch="dynamic_schema_fields", field_count=len(fields))
                user_prompt = (
                    f"Document Filename: {filename}\n\n"
                    f"Target Schema Fields:\n{fields_summary}\n\n"
                    f"Target JSON Structure:\n{fields_json_schema}\n\n"
                    f"Document Content:\n{content_snippet}\n\n"
                    "Extract all matching schema fields and any unmapped extra domain knowledge in valid JSON format matching:\n"
                    '{\n  "extracted_fields": { ... },\n  "extra_fields": { ... }\n}'
                )
            else:
                logger.debug("domain_extractor_decision_user_prompt", branch="schemaless_comprehensive")
                user_prompt = (
                    f"Document Filename: {filename}\n\n"
                    f"Document Content:\n{content_snippet}\n\n"
                    "Extract a comprehensive structured JSON of ALL key information in this document.\n"
                    "Include all entities, parties, dates, amounts, decisions, references, and any other significant data.\n"
                    "Use only what is explicitly stated. Omit fields not present.\n"
                    'Return valid JSON only matching:\n{\n  "extracted_fields": { ... },\n  "extra_fields": { ... }\n}'
                )

        logger.info(
            "domain_extraction_executing",
            filename=filename,
            domain_key=domain_key,
            has_custom_sys_prompt=bool(system_prompt_template),
            has_custom_user_prompt=bool(user_prompt_template),
        )

        try:
            raw_response = await self.llm.complete(sys_prompt, user_prompt, temperature=0.0)
            cleaned = _clean_json_string(raw_response)
            parsed = json.loads(cleaned)

            if isinstance(parsed, dict) and ("extracted_fields" in parsed or "extra_fields" in parsed):
                logger.debug("domain_extractor_decision_payload_parse", branch="canonical_wrapper")
                extracted_fields = parsed.get("extracted_fields") or {}
                extra_fields = parsed.get("extra_fields") or {}
            elif isinstance(parsed, dict):
                if fields:
                    logger.debug("domain_extractor_decision_payload_parse", branch="root_dict_split_by_schema_keys")
                    schema_field_keys = {f.get("key") for f in fields if f.get("key")}
                    extracted_fields = {k: v for k, v in parsed.items() if k in schema_field_keys}
                    extra_fields = {k: v for k, v in parsed.items() if k not in schema_field_keys}
                else:
                    logger.debug("domain_extractor_decision_payload_parse", branch="root_dict_all_extracted")
                    extracted_fields = parsed
                    extra_fields = {}
            else:
                logger.debug("domain_extractor_decision_payload_parse", branch="unrecognized_structure")
                extracted_fields = {}
                extra_fields = {}

            if not isinstance(extracted_fields, dict):
                extracted_fields = {}
            if not isinstance(extra_fields, dict):
                extra_fields = {}

            # Grounding verifier — leaf-level
            extracted_fields = filter_ungrounded_fields(extracted_fields, text)
            if extra_fields:
                extra_fields = filter_ungrounded_fields(extra_fields, text)

            logger.info(
                "domain_extraction_completed",
                domain_key=domain_key,
                filename=filename,
                extracted_keys_count=len(extracted_fields),
                extra_keys_count=len(extra_fields),
            )

            return {
                "domain_name": domain_name,
                "domain_key": domain_key,
                "extracted_fields": extracted_fields,
                "extra_fields": extra_fields,
                "field_weights": field_weights,
                "extraction_mode": "prompt_driven" if system_prompt_template else "domain_default",
                "debug_info": {
                    "system_prompt": sys_prompt,
                    "user_prompt": user_prompt,
                    "raw_response": raw_response,
                },
            }
        except Exception as exc:
            logger.warning("domain_extraction_failed", filename=filename, error=str(exc))
            return {
                "domain_name": domain_name,
                "domain_key": domain_key,
                "extracted_fields": {},
                "extra_fields": {},
                "field_weights": field_weights,
                "error": str(exc),
                "extraction_mode": "failed",
                "debug_info": {
                    "system_prompt": sys_prompt,
                    "user_prompt": user_prompt,
                },
            }

