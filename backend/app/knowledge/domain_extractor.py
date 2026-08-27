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
    Rejects placeholders and hallucinations while preserving citations,
    summaries, categorizations, and normalized numbers.
    """
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, (int, float)):
        # Normalize numeric representations
        val_int = int(val) if float(val).is_integer() else None
        val_str = str(val_int) if val_int is not None else str(val)
        if val_str in raw_text_lower:
            return True
        # Check formatted numbers with commas (e.g. 50,000 or 1,00,000)
        if val_int is not None:
            formatted_en = f"{val_int:,}"
            if formatted_en in raw_text_lower:
                return True
        # For floating point confidence/scores (0.0 to 1.0) or small integers, retain valid metadata
        if isinstance(val, float) and 0.0 <= val <= 1.0:
            return True
        return False

    if isinstance(val, str):
        val_str = val.strip().lower()
        if not val_str or val_str in {"null", "n/a", "none", "unknown", "undefined"}:
            return False

        # Reject literal template placeholder tokens (e.g. [Name], [Judge], <value>, <description>)
        if re.search(r"\[(name|judge|advocate|title|date|court|lawyer|plaintiff|respondent|case|placeholder|unmapped)\]|<(value|description|unmapped.*?|details|date|name|field)>", val_str, re.IGNORECASE):
            return False
        if re.fullmatch(r"\[[a-zA-Z_\s]+\]|<[a-zA-Z_\s]+>", val_str):
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
            # Check if any digits/years in check_tokens exist in raw text (e.g. 2018, 482)
            digit_tokens = [t for t in check_tokens if t.isdigit()]
            if digit_tokens and any(dt in raw_text_lower for dt in digit_tokens):
                return True
            return False

        # Multi-word string match ratio: accept >= 30% overlap or >= 2 key token matches
        match_ratio = matched / len(check_tokens)
        return match_ratio >= 0.3 or matched >= 2


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
        return v if _is_grounded_in_text(v, raw_text_lower) else None
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
# BLOCK COMMENT: CANONICAL FIELD ALIAS DICTIONARY & RECONCILIATION
# Purpose:
# 1. Maps drifted LLM keys (coram -> judge, case_numbers -> case_number) to single SOT keys.
# 2. Ensures extracted_fields strictly adheres to target schema definitions.
# 3. Routes any unmapped / out-of-schema attributes into extra_fields.
# =====================================================================
FIELD_CANONICAL_ALIASES: dict[str, str] = {
    # Judicial / Coram / Judge
    "coram": "judge",
    "judges": "judge",
    "bench": "judge",
    "honble_judge": "judge",
    "honble_justice": "judge",
    "justice": "judge",
    "presiding_judge": "judge",
    "court_name": "court",
    "forum": "court",
    "tribunal": "court",
    "tribunal_name": "court",
    "bench_location": "location",
    "court_location": "location",
    "jurisdiction": "location",

    # Case Identification & Timeline
    "case_numbers": "case_number",
    "case_no": "case_number",
    "caseno": "case_number",
    "appeal_number": "case_number",
    "appeal_no": "case_number",
    "petition_number": "case_number",
    "petition_no": "case_number",
    "citation_number": "citation",
    "citations": "citation",
    "judgment_date": "decision_date",
    "order_date": "decision_date",
    "date_of_judgment": "decision_date",
    "date_of_decision": "decision_date",
    "date_of_order": "decision_date",
    "case_date": "decision_date",
    "related_cases": "connected_cases",
    "connected_case": "connected_cases",
    "other_cases": "connected_cases",

    # Parties & Advocates
    "petitioner": "petitioners",
    "appellant": "appellants",
    "claimant": "petitioners",
    "claimants": "petitioners",
    "applicant": "petitioners",
    "applicants": "petitioners",
    "respondent": "respondents",
    "opponent": "respondents",
    "opponents": "respondents",
    "defendant": "defendants",
    "accused": "defendants",
    "prosecutor": "prosecutors",
    "prosecution": "prosecutors",
    "advocate": "advocates",
    "lawyer": "advocates",
    "lawyers": "advocates",
    "counsel": "advocates",
    "counsels": "advocates",
    "legal_counsel": "advocates",

    # Statutes & Sections
    "act": "statutes",
    "acts": "statutes",
    "statute": "statutes",
    "statutes_cited": "statutes",
    "section": "sections",
    "section_involved": "sections",
    "key_sections": "sections",
    "sections_involved": "sections",
    "provisions": "sections",
    "provision": "sections",
    "article": "sections",
    "articles": "sections",
    "articles_involved": "sections",

    # Outcomes & Findings
    "disposition": "final_decision",
    "outcome": "final_decision",
    "verdict": "final_decision",
    "order_type": "judgment_type",
}


def _reconcile_dict_keys(d: dict[str, Any], allowed_props: set[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconciles keys in a dictionary using canonical aliases and separates unmapped properties."""
    from app.knowledge.document_tag_service import normalize_standard_date
    clean_dict: dict[str, Any] = {}
    extra_dict: dict[str, Any] = {}

    for raw_k, raw_v in d.items():
        k_str = str(raw_k).strip()
        k_lower = k_str.lower()
        k_norm = k_lower.replace(" ", "_")

        # Canonical target name
        canon_k = FIELD_CANONICAL_ALIASES.get(k_norm) or FIELD_CANONICAL_ALIASES.get(k_lower) or k_norm

        if isinstance(raw_v, dict):
            sub_clean, sub_extra = _reconcile_dict_keys(raw_v)
            raw_v = {**sub_clean, **sub_extra}
        elif isinstance(raw_v, list):
            # If list of dicts (like connected_cases), reconcile each item
            norm_list = []
            for item in raw_v:
                if isinstance(item, dict):
                    i_clean, i_extra = _reconcile_dict_keys(item)
                    norm_list.append({**i_clean, **i_extra})
                else:
                    norm_list.append(item)
            raw_v = norm_list
        elif isinstance(raw_v, str) and ("date" in canon_k or "date" in k_norm):
            norm_date = normalize_standard_date(raw_v)
            if norm_date:
                raw_v = norm_date

        if allowed_props is not None:
            # Check if canon_k or k_norm belongs to allowed property set
            if canon_k in allowed_props:
                clean_dict[canon_k] = raw_v
            elif k_norm in allowed_props:
                clean_dict[k_norm] = raw_v
            else:
                extra_dict[k_str] = raw_v
        else:
            clean_dict[canon_k] = raw_v

    return clean_dict, extra_dict


def reconcile_extracted_payload(
    extracted_fields: dict[str, Any],
    extra_fields: dict[str, Any],
    fields: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Deterministically reconciles extracted fields against schema keys and known canonical aliases.
    - Resolves drifted names (e.g. coram -> judge, case_numbers -> case_number, acts -> statutes).
    - Ensures extracted_fields contains ONLY valid schema fields.
    - Automatically routes any unmapped or extra keys to extra_fields.
    """
    clean_extracted: dict[str, Any] = {}
    clean_extra: dict[str, Any] = dict(extra_fields or {})

    if not fields:
        # Schema-free: apply canonical key normalization across all fields
        norm_extracted, unmapped = _reconcile_dict_keys(extracted_fields or {})
        clean_extracted.update(norm_extracted)
        clean_extra.update(unmapped)
        return clean_extracted, clean_extra

    # Build schema lookup maps
    schema_key_map: dict[str, str] = {}
    schema_prop_map: dict[str, set[str]] = {}

    for f in fields:
        orig_k = f.get("key")
        if not orig_k:
            continue
        k_lower = orig_k.lower().strip()
        schema_key_map[k_lower] = orig_k
        schema_key_map[k_lower.replace("_", "")] = orig_k
        lbl = f.get("label")
        if lbl:
            schema_key_map[lbl.lower().replace(" ", "_").strip()] = orig_k
            schema_key_map[lbl.lower().replace(" ", "").strip()] = orig_k

        # Extract nested properties if defined in schema
        props = f.get("properties")
        if isinstance(props, dict):
            prop_keys = set()
            for pk in props.keys():
                prop_keys.add(pk.lower())
                # Add aliases pointing to this subprop
                for alias_k, canon_target in FIELD_CANONICAL_ALIASES.items():
                    if canon_target == pk.lower():
                        prop_keys.add(alias_k)
            schema_prop_map[orig_k] = prop_keys

    for raw_k, raw_v in (extracted_fields or {}).items():
        k_str = str(raw_k).strip()
        k_lower = k_str.lower()
        k_no_us = k_lower.replace("_", "").replace(" ", "")

        # 1. Direct schema match or alias match
        target_schema_key = schema_key_map.get(k_lower) or schema_key_map.get(k_no_us)
        if not target_schema_key:
            canon_alias = FIELD_CANONICAL_ALIASES.get(k_lower)
            if canon_alias:
                target_schema_key = schema_key_map.get(canon_alias) or schema_key_map.get(canon_alias.replace("_", ""))

        if target_schema_key:
            allowed_subprops = schema_prop_map.get(target_schema_key)
            if isinstance(raw_v, dict):
                sub_clean, sub_extra = _reconcile_dict_keys(raw_v, allowed_subprops)
                clean_extracted[target_schema_key] = sub_clean
                for sub_k, sub_val in sub_extra.items():
                    clean_extra[f"{target_schema_key}_{sub_k}"] = sub_val
            elif isinstance(raw_v, list):
                norm_list = []
                for item in raw_v:
                    if isinstance(item, dict):
                        i_clean, i_extra = _reconcile_dict_keys(item)
                        norm_list.append({**i_clean, **i_extra})
                    else:
                        norm_list.append(item)
                clean_extracted[target_schema_key] = norm_list
            else:
                clean_extracted[target_schema_key] = raw_v
        else:
            # Unmapped top-level key: route to extra_fields
            clean_extra[k_str] = raw_v

    return clean_extracted, clean_extra


# =====================================================================
# BLOCK COMMENT: DYNAMIC PROMPT BUILDERS (SINGLE SOURCE OF TRUTH)
# Purpose:
# 1. format_fields_summary: Generates human-readable field definitions.
# 2. format_fields_json_schema: Generates dynamic target JSON structure from domain_schema fields.
# 3. Ensures domain_schema (schema_json['fields']) is the sole source of truth for prompts and extraction.
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
    """Format target JSON schema structure dynamically from domain_schema fields as single source of truth."""
    if not fields:
        return '{\n  "extracted_fields": { ... },\n  "extra_fields": { ... }\n}'

    extracted_spec: dict[str, Any] = {}
    for f in fields:
        k = f.get("key")
        if not k:
            continue
        ft = (f.get("type") or "string").lower()
        desc = f.get("description") or f.get("label") or k
        if f.get("properties") and isinstance(f.get("properties"), dict):
            extracted_spec[k] = f.get("properties")
        elif f.get("items") and isinstance(f.get("items"), (dict, list, str)):
            extracted_spec[k] = [f.get("items")] if not isinstance(f.get("items"), list) else f.get("items")
        elif ft in ("array", "list"):
            extracted_spec[k] = [f"<{desc}>"]
        elif ft in ("object", "dict"):
            extracted_spec[k] = {"details": f"<{desc}>"}
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
        schema_json: dict[str, Any] | None = None,
        schema_extraction_system_prompt: str | None = None,
        schema_extraction_user_prompt: str | None = None,
        kb_extraction_system_prompt: str | None = None,
        kb_extraction_user_prompt: str | None = None,
        strategy: str = "inherit",
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

        # =====================================================================
        # BLOCK COMMENT: PROMPT RESOLUTION (SINGLE SOURCE OF TRUTH)
        # Purpose:
        # 1. Resolves system prompt according to strategy (inherit, override, combine).
        # 2. Dynamically derives fields_summary and fields_json_schema from fields.
        # 3. Renders user prompt template with dynamic schema structure (content injected by LLM layer).
        # =====================================================================
        fields_summary = format_fields_summary(fields)
        fields_json_schema = format_fields_json_schema(fields)

        # default_sys_prompt = (
        #     "You are a precise document entity extractor.\n"
        #     "RULE 1: Extract ONLY values explicitly present in the provided Document Content.\n"
        #     "RULE 2: STRICT FIELD CANONICALIZATION: Follow the exact schema field names provided. Do NOT drift or rename fields "
        #     "(e.g. use `judge` (singular), NOT `coram`/`judges`/`bench`; use `case_number` (singular), NOT `case_numbers`/`case_no`; "
        #     "use `decision_date`, NOT `order_date`/`judgment_date`; use `court`, NOT `court_name`/`forum`; use `statutes`, NOT `acts`; "
        #     "use `sections`, NOT `provisions`/`articles`; use `petitioners`, NOT `petitioner`; use `respondents`, NOT `respondent`; "
        #     "use `advocates`, NOT `counsel`/`lawyers`).\n"
        #     "RULE 3: STRICT SCHEMA BOUNDARY: Extract ONLY the defined schema fields under 'extracted_fields'. "
        #     "Any other unmapped facts, observed attributes, or additional domain details MUST go under 'extra_fields'. "
        #     "NEVER place unmapped keys into 'extracted_fields'.\n"
        #     "RULE 4: If a field value is NOT found in the document text, OMIT that field entirely — do NOT write null, do NOT write empty string.\n"
        #     "RULE 5: DO NOT use training data, prior knowledge, or inferred values.\n"
        #     "RULE 6: Use exact wording from the document for all extracted values.\n"
        #     'Return valid JSON only matching: {"extracted_fields": { ... }, "extra_fields": { ... }}'
        # )

        # --- Prompt Merging Strategy (Commented Out) ---
        # base_schema_sys = schema_extraction_system_prompt
        # base_schema_user = schema_extraction_user_prompt
        # effective_kb_sys = kb_extraction_system_prompt
        # effective_kb_user = kb_extraction_user_prompt
        #
        # resolved_strategy = (strategy or "inherit").lower()
        # prompt_source = "domain_schema"
        #
        # if resolved_strategy == "combine":
        #     base_prompt = base_schema_sys or default_sys_prompt
        #     if effective_kb_sys and effective_kb_sys.strip():
        #         sys_template = f"{base_prompt}\n\n### Knowledge Base Extraction Directives:\n{effective_kb_sys.strip()}"
        #         prompt_source = "combined"
        #     else:
        #         sys_template = base_prompt
        #         prompt_source = "domain_schema" if base_schema_sys else "system_default"
        #     user_template = effective_kb_user or base_schema_user
        # elif resolved_strategy == "override":
        #     if effective_kb_sys and effective_kb_sys.strip():
        #         sys_template = effective_kb_sys
        #         prompt_source = "kb_override"
        #     elif base_schema_sys and base_schema_sys.strip():
        #         sys_template = base_schema_sys
        #         prompt_source = "domain_schema"
        #     else:
        #         sys_template = default_sys_prompt
        #         prompt_source = "system_default"
        #     user_template = effective_kb_user or base_schema_user
        # else:  # inherit (default)
        #     if base_schema_sys and base_schema_sys.strip():
        #         sys_template = base_schema_sys
        #         prompt_source = "domain_schema"
        #     elif effective_kb_sys and effective_kb_sys.strip():
        #         sys_template = effective_kb_sys
        #         prompt_source = "kb_override"
        #     else:
        #         sys_template = default_sys_prompt
        #         prompt_source = "system_default"
        #     user_template = base_schema_user or effective_kb_user
        # ------------------------------------------------

        if not schema_extraction_system_prompt or not schema_extraction_system_prompt.strip():
            raise ValueError("schema_extraction_system_prompt is required for domain extraction.")
        if not schema_extraction_user_prompt or not schema_extraction_user_prompt.strip():
            raise ValueError("schema_extraction_user_prompt is required for domain extraction.")

        sys_prompt = (
            schema_extraction_system_prompt
            .replace("{domain_name}", domain_name or "")
            .replace("{filename}", filename or "")
        )

        user_prompt = (
            schema_extraction_user_prompt
            .replace("{filename}", filename or "")
            .replace("{fields_summary}", fields_summary)
            .replace("{fields_json_schema}", fields_json_schema)
            .replace("{domain_name}", domain_name or "")
        )

        logger.info(
            "domain_extraction_prompt_resolved",
            domain_key=domain_key,
            domain_name=domain_name,
            filename=filename,
            sys_prompt_len=len(sys_prompt),
            user_prompt_len=len(user_prompt),
        )

        try:
            raw_response = await self.llm.complete(sys_prompt, user_prompt, temperature=0.0, document_text=text)
            cleaned = _clean_json_string(raw_response)
            parsed = json.loads(cleaned)

            # Auto-unwrap wrapper containers if LLM wrapped the payload
            if isinstance(parsed, dict):
                for wrapper_key in ("data", "result", "response", "payload", "output", domain_key, "legal", "extracted_data"):
                    if wrapper_key in parsed and isinstance(parsed[wrapper_key], dict) and ("extracted_fields" in parsed[wrapper_key] or "extra_fields" in parsed[wrapper_key] or len(parsed[wrapper_key]) > len(parsed) - 1):
                        parsed = parsed[wrapper_key]
                        break

            if isinstance(parsed, dict) and ("extracted_fields" in parsed or "extra_fields" in parsed):
                logger.debug("domain_extractor_decision_payload_parse", branch="canonical_wrapper")
                extracted_fields = parsed.get("extracted_fields") or {}
                extra_fields = parsed.get("extra_fields") or {}
            elif isinstance(parsed, dict):
                if fields:
                    logger.debug("domain_extractor_decision_payload_parse", branch="root_dict_split_by_schema_keys")
                    # Build canonical lookup map for schema keys (lowercased, stripped, underscore normalized)
                    norm_key_map = {}
                    for f in fields:
                        orig_k = f.get("key")
                        if orig_k:
                            norm_key_map[orig_k.lower().strip()] = orig_k
                            norm_key_map[orig_k.lower().replace("_", "").strip()] = orig_k
                            lbl = f.get("label")
                            if lbl:
                                norm_key_map[lbl.lower().replace(" ", "_").strip()] = orig_k
                                norm_key_map[lbl.lower().replace(" ", "").strip()] = orig_k

                    extracted_fields = {}
                    extra_fields = {}
                    for k, v in parsed.items():
                        cleaned_k = str(k).lower().strip()
                        cleaned_k_no_us = cleaned_k.replace("_", "").replace(" ", "")
                        target_key = norm_key_map.get(cleaned_k) or norm_key_map.get(cleaned_k_no_us)
                        if target_key:
                            extracted_fields[target_key] = v
                        else:
                            extra_fields[k] = v
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

            # Deterministic Anti-Drift Canonical Reconciler
            extracted_fields, extra_fields = reconcile_extracted_payload(
                extracted_fields=extracted_fields,
                extra_fields=extra_fields,
                fields=fields,
            )

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
                "extraction_mode": "prompt_driven",
                "debug_info": {
                    "strategy": strategy or "inherit",
                    "prompt_source": "domain_schema",
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
#                    "strategy": resolved_strategy,
#                    "prompt_source": prompt_source,
                    "system_prompt": sys_prompt,
                    "user_prompt": user_prompt,
                },
            }

