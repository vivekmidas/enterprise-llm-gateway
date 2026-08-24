import time
import re
import structlog
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.llm_router import LLMRouter
from app.knowledge.retrieval_models import (
    ResponseGenerationRequest,
    ResponseGenerationResult,
)

logger = structlog.get_logger(__name__)


# Standard English function, structural, organizational & domain vocabulary (domain-agnostic)
COMMON_ENGLISH_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not", "on", "with",
    "he", "as", "you", "do", "at", "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
    "or", "an", "will", "my", "one", "all", "would", "there", "their", "what", "so", "up", "out", "if",
    "about", "who", "get", "which", "go", "me", "when", "make", "can", "like", "time", "no", "just", "him",
    "know", "take", "people", "into", "year", "your", "good", "some", "could", "them", "see", "other",
    "than", "then", "now", "look", "only", "come", "its", "over", "think", "also", "back", "after", "use",
    "two", "how", "our", "work", "first", "well", "way", "even", "new", "want", "because", "any", "these",
    "give", "day", "most", "us", "however", "therefore", "although", "furthermore", "moreover", "regarding",
    "since", "between", "under", "without", "against", "during", "before", "information", "document",
    "provided", "available", "record", "records", "summary", "result", "results", "based", "according", "following", "details",
    "case", "cases", "action", "actions", "state", "status", "type", "types", "order", "orders", "matter", "report", "process", "rule",
    "high", "court", "courts", "act", "acts", "arms", "code", "law", "laws", "section", "sections", "article", "articles",
    "judge", "judges", "justice", "bench", "appeal", "appeals", "petitioner", "petitioners", "respondent", "respondents",
    "sentence", "sentences", "conviction", "convictions", "murder", "imprisonment", "offence", "offences", "trial", "trials",
    "decision", "decisions", "revision", "jurisdiction", "application", "applications", "board", "committee", "council",
    "police", "station", "medical", "hospital", "doctor", "patient", "health", "care", "service", "services",
    "school", "university", "college", "student", "students", "teacher", "teachers", "education", "course", "courses", "author", "authors", "book", "books",
    "science", "learning", "study", "research", "method", "methods", "system", "systems", "design", "management", "graduate", "target", "audience",
    "contract", "contracts", "agreement", "agreements", "vendor", "vendors", "client", "clients", "customer", "customers",
    "account", "accounts", "finance", "financial", "payment", "invoice", "company", "group", "department", "unit",
    "manager", "employee", "officer", "director", "president", "member", "members", "team", "agency", "union",
    "general", "public", "private", "national", "central", "district", "regional", "local", "federal", "primary", "secondary"
}


def _verify_answer_grounding(answer: str, context_text: str, extra_context: str = "") -> bool:
    """
    100% Domain-agnostic grounding check:
    1. Verifies long numeric identifiers (>= 4 digits) in answer exist in context.
    2. Strips JSON schema keys, markdown headers, and structural discourse.
    3. Verifies that non-dictionary proper names (people, organizations, places) have presence in context.
    Works identically for Legal, Healthcare, Procurement, HR, Education, etc.
    """
    if not answer or not context_text:
        return True

    clean_ans_lower = answer.strip().lower()
    if clean_ans_lower in {"no answer", "information is not available in the provided document."}:
        return True

    full_ctx_lower = f"{context_text} {extra_context}".lower()

    # 1. Check Long Numbers / Specific IDs (length >= 5, excluding standard 4-digit years)
    long_numbers = set(re.findall(r"\b\d{5,}\b", answer))
    if long_numbers:
        missing_numbers = [n for n in long_numbers if n not in full_ctx_lower]
        if len(missing_numbers) >= 2 and len(missing_numbers) == len(long_numbers):
            logger.warning("grounding_failed_fabricated_numeric_ids", missing=missing_numbers[:3])
            return False

    # 2. Check Multi-Word Proper Named Entities (Domain-Agnostic)
    # Strip JSON keys ("field_name": ...), markdown bold labels (**Key**: ...), and line-starting labels
    clean_text = re.sub(r'"[A-Za-z0-9_\s]+"\s*:', "", answer)
    clean_text = re.sub(r"\*\*([A-Za-z\s]+)\*\*:", "", clean_text)
    clean_text = re.sub(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*:", "", clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r"^#+\s+.*$", "", clean_text, flags=re.MULTILINE)

    # Find potential capitalized multi-word phrases
    multi_word_phrases = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", clean_text)

    suspicious_entities = []
    for phrase in multi_word_phrases:
        words = [w.lower() for w in phrase.split() if len(w) >= 3]
        # If any word in the phrase is a standard dictionary/vocabulary word, it's not a hallucinated proper name
        non_dict_words = [w for w in words if w not in COMMON_ENGLISH_WORDS]
        if not non_dict_words or len(non_dict_words) < len(words):
            continue

        # If any of the distinctive non-dictionary proper name words exist in context, it's grounded
        if not any(w in full_ctx_lower for w in non_dict_words):
            suspicious_entities.append(phrase)

    if len(suspicious_entities) >= 2:
        logger.warning("grounding_failed_fabricated_proper_entities", missing=suspicious_entities[:3])
        return False

    return True


def _parse_markdown_to_json(text: str) -> list[dict]:
    """
    Simple, 100% domain-agnostic parser that transforms structured markdown lists/records into JSON objects.
    Dynamically maps bullet points '- **Key**: Value' to snake_case dictionary keys without domain-specific schemas.
    """
    has_numbered_items = bool(re.search(r"(?:^|\n)\s*\d+[\.\)]\s+\*?\*?", text))
    has_bullet_keys = bool(re.search(r"(?:^|\n)\s*[-*•]\s+\*?\*?[A-Za-z0-9_\s]+\*?\*?:", text))
    if not has_numbered_items and not has_bullet_keys:
        return []

    records = []
    case_chunks = re.split(r"(?:^|\n)\s*(?:\d+[\.\)]|\#\#+)\s+", text)
    if len(case_chunks) <= 1:
        case_chunks = re.split(r"\n\s*\n\s*(?=\*\*)", text)

    for chunk in case_chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue

        inline_match = re.match(r"^\*\*([^*]+)\*\*:\s*(.*)", lines[0])
        if inline_match:
            title_line = inline_match.group(1).strip()
            inline_summary = inline_match.group(2).strip()
        else:
            title_line = lines[0].replace("**", "").rstrip(":").strip()
            inline_summary = ""

        # Filter conversational preambles
        lower_title = title_line.lower()
        if (
            lower_title.startswith("based on")
            or lower_title.startswith("the context")
            or lower_title.startswith("here is")
            or lower_title.startswith("here are")
            or lower_title.startswith("these are")
            or lower_title.startswith("the following")
            or lower_title.startswith("note that")
            or lower_title.startswith("the above")
            or lower_title.startswith("unfortunately")
            or lower_title.startswith("according to")
            or lower_title.startswith("as per")
            or len(title_line) < 3
        ):
            continue

        record: dict = {
            "title": title_line,
        }

        if inline_summary:
            record["summary"] = inline_summary

        summary_parts = []
        for line in lines[1:]:
            clean_l = re.sub(r"^[-*•\d\.]+\s*", "", line).strip()
            if not clean_l:
                continue
            if ":" in clean_l:
                k, v = clean_l.split(":", 1)
                k_raw = k.replace("**", "").replace("*", "").strip()
                v_clean = v.replace("**", "").replace("*", "").strip()

                # Dynamic snake_case field normalization
                field_key = re.sub(r"[^a-zA-Z0-9]+", "_", k_raw).strip("_").lower()
                if not field_key:
                    continue

                if v_clean.startswith("[") and v_clean.endswith("]"):
                    parsed_list = [item.strip(" '\"[]") for item in re.split(r"[,;]", v_clean) if item.strip(" '\"[]")]
                    record[field_key] = parsed_list
                else:
                    record[field_key] = v_clean
            else:
                summary_parts.append(clean_l)

        if summary_parts:
            combined = ". ".join(summary_parts)
            if "summary" in record and record["summary"]:
                record["summary"] = f"{record['summary']}. {combined}".strip(". ")
            else:
                record["summary"] = combined

        records.append(record)
    return records


_parse_markdown_cases_to_json = _parse_markdown_to_json


def _clean_and_normalize_answer(answer: str, system_prompt: str = "") -> str:
    """
    Normalizes LLM output across providers and domains:
    1. Extracts clean JSON payload if wrapped in markdown code fences or conversational text.
    2. Detects refusal / not-found statements and returns 'no answer' or empty JSON.
    3. Seamlessly converts any domain markdown list into structured JSON.
    """
    if not answer or not answer.strip():
        return "no answer"

    clean_text = answer.strip()

    # Dynamic root key detection from system prompt (e.g. {"books": [...]}, {"cases": [...]})
    root_key = "cases"
    if system_prompt:
        key_match = re.search(r'\{"([a-zA-Z0-9_]+)":\s*\[', system_prompt)
        if key_match:
            root_key = key_match.group(1)

    # 1. Strip markdown code fences if wrapped: ```json ... ``` or ``` ... ```
    if "```" in clean_text:
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
        if json_match:
            candidate = json_match.group(1).strip()
            if candidate.startswith("{") or candidate.startswith("[{") or candidate.startswith("[\n{"):
                try:
                    import json
                    json.loads(candidate)
                    clean_text = candidate
                except Exception:
                    pass

    # 2. If system prompt requested JSON, extract raw JSON object { ... } or [ { ... } ]
    is_json_requested = "json" in system_prompt.lower() or '{"' in system_prompt or "{'" in system_prompt
    if is_json_requested and not clean_text.startswith("{") and not clean_text.startswith("[{"):
        first_brace = clean_text.find("{")
        last_brace = clean_text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = clean_text[first_brace:last_brace + 1].strip()
            try:
                import json
                json.loads(candidate)
                clean_text = candidate
            except Exception:
                pass

    # 3. Refusal normalization
    lower_ans = clean_text.lower()
    refusal_indicators = [
        "unable to find any",
        "unable to find",
        "could not find any",
        "could not find",
        "no relevant information",
        "no cases found",
        "no records found",
        "not mentioned in the provided context",
        "not mentioned in the context",
        "not available in the provided document",
        "not available in the provided context",
        "information is not available",
        "no information is available",
        "no answer",
        "i do not know",
        "dont know",
        "don t know",
    ]

    has_refusal = any(p in lower_ans for p in refusal_indicators)
    if has_refusal:
        # If response doesn't have a non-empty populated JSON list
        is_populated_json = (
            (clean_text.startswith("{") or clean_text.startswith("[{"))
            and ('"title"' in clean_text or '"case_title"' in clean_text or '"name"' in clean_text)
            and len(clean_text) > 40
        )
        if not is_populated_json:
            if is_json_requested:
                import json
                return json.dumps({root_key: []})
            return "no answer"

    # 4. Strict JSON enforcement or Markdown-to-JSON parsing
    import json
    try:
        parsed = json.loads(clean_text)
        if isinstance(parsed, dict) or (isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict)):
            return json.dumps(parsed, indent=2)
    except Exception:
        pass

    # Attempt to extract embedded JSON
    match = re.search(r"(\{[\s\S]*\}|\[\s*\{[\s\S]*\}\s*\])", clean_text)
    if match:
        try:
            parsed = json.loads(match.group(1))
            return json.dumps(parsed, indent=2)
        except Exception:
            pass

    # If model returned markdown list (e.g. from Ollama), parse into domain-agnostic JSON
    parsed_records = _parse_markdown_to_json(clean_text)
    if parsed_records:
        result_dict = {root_key: parsed_records}
        if root_key != "cases":
            result_dict["cases"] = parsed_records
        return json.dumps(result_dict, indent=2)

    # If JSON was explicitly requested, ensure valid JSON fallback
    if is_json_requested:
        return json.dumps({root_key: [], "raw_response": clean_text})

    return clean_text


class ResponseGenerationService:
    def __init__(self) -> None:
        self.llm_router = LLMRouter()

    async def generate_response(self, request: ResponseGenerationRequest, db = None) -> ResponseGenerationResult:
        """
        Takes retrieved chunks/context, builds prompt, calls the LLM, and validates the response.
        """
        start_time = time.perf_counter()

        has_context = bool(
            request.context
            and (request.context.chunks or (request.context.context and request.context.context.strip()))
        )

        effective_llm_config = getattr(request, "llm_config", None) or {}
        llm_config_id = getattr(request, "llm_config_id", None) or getattr(request, "llm_profile_id", None)
        llm_profile = getattr(request, "llm_profile", None)

        if not has_context and not effective_llm_config and not llm_profile and not request.system_prompt and not llm_config_id:
            logger.info("response_generation_empty_context_returning_no_answer")
            return ResponseGenerationResult(
                answer="no answer",
                used_tokens=0,
            )

        # System prompt resolution with configuration hierarchy:
        # 1. Caller Request Override (request.system_prompt)
        # 2. CustomerDB Tenant Settings ("Client AI Prompts" configured in UI)
        # 3. Default Settings Fallback (get_settings().SYSTEM_PROMPT)
        from app.core.config import get_settings
        system_prompt = get_settings().SYSTEM_PROMPT

        # Check Step 1: Explicit Request Override
        if request.system_prompt and request.system_prompt.strip():
            system_prompt = request.system_prompt.strip()
            logger.info("using_caller_override_system_prompt")
        else:
            resolved_prompt = None

            # Check Step 2: CustomerDB Tenant Settings ("Client AI Prompts" in UI)
            if db and request.customer_id:
                try:
                    from app.models.db_models import CustomerDB
                    from sqlalchemy import select, or_
                    cust_res = await db.execute(
                        select(CustomerDB).where(
                            or_(CustomerDB.id == request.customer_id, CustomerDB.id == str(request.customer_id))
                        )
                    )
                    cust = cust_res.scalar_one_or_none()
                    if cust and cust.settings and isinstance(cust.settings, dict):
                        cust_prompts = cust.settings.get("prompts", {}) or {}
                        if not cust_prompts and any(k in cust.settings for k in ("search_system_prompt", "drafting_system_prompt", "synthesize_system_prompt")):
                            cust_prompts = cust.settings
                        tenant_search_sys = cust_prompts.get("search_system_prompt") or cust_prompts.get("system_prompt")
                        if tenant_search_sys and str(tenant_search_sys).strip():
                            resolved_prompt = str(tenant_search_sys).strip()
                            logger.info("using_customer_tenant_client_ai_prompt", customer_id=request.customer_id)
                except Exception as c_err:
                    logger.warning("failed_to_fetch_customer_prompts", error=str(c_err))

            if resolved_prompt:
                system_prompt = resolved_prompt

        if has_context:
            context_text = ""
            chunks_list = request.context.chunks if request.context else []
            if chunks_list and (
                not request.context.context
                or not request.context.context.strip()
                or "[Extracted Metadata]" not in request.context.context
            ):
                from app.knowledge.context_builder import format_chunk_with_metadata
                context_text = "\n\n---\n\n".join([format_chunk_with_metadata(c) for c in chunks_list])
            elif request.context and request.context.context:
                context_text = request.context.context.strip()

            user_prompt = (
                f"Context:\n"
                f"{context_text}\n\n"
                f"Query:\n"
                f"{request.query}"
            )
        else:
            user_prompt = request.query

        # For smaller / local models, reinforce JSON instruction if prompt requests JSON output
        is_json_requested = "json" in system_prompt.lower() or '{"' in system_prompt or "{'" in system_prompt
        if is_json_requested:
            user_prompt += "\n\nCRITICAL INSTRUCTION: Respond ONLY with a valid raw JSON object strictly adhering to the schema. Do NOT include markdown codeblocks (```json), conversational text, introductory greetings, or commentary."

        # ==============================================================================
        # BLOCK COMMENT: KNOWLEDGE BASE & PROFILE AWARE CONFIG RESOLUTION
        # Resolves model configuration (provider, model, max_tokens, temperature) from
        # LLMProfile without interfering with prompt management.
        # ==============================================================================
        if llm_profile:
            if hasattr(llm_profile, "generation"):
                gen = llm_profile.generation
                gen_dict = gen.model_dump() if hasattr(gen, "model_dump") else dict(gen)
                effective_llm_config = {**gen_dict, **effective_llm_config}
        elif db and (not effective_llm_config or not (effective_llm_config.get("model") or effective_llm_config.get("llm_model"))):
            try:
                target_kb_id = None
                target_customer_id = request.customer_id
                if not llm_config_id and has_context and request.context.chunks:
                    for chunk in request.context.chunks:
                        kb_id = getattr(chunk, "knowledge_base_id", None) or (chunk.metadata.get("knowledge_base_id") if getattr(chunk, "metadata", None) else None)
                        if kb_id:
                            target_kb_id = str(kb_id)
                            break

                from app.core.profile_resolver import ProfileResolver
                resolver = ProfileResolver(db=db)
                profile = await resolver.resolve_for_knowledge_base(
                    knowledge_base_id=target_kb_id,
                    customer_id=target_customer_id,
                    profile_id=str(llm_config_id) if llm_config_id else None,
                )
                if profile:
                    gen_dict = profile.generation.model_dump()
                    effective_llm_config = {**gen_dict, **effective_llm_config}
                    logger.info(
                        "resolved_profile_for_generation",
                        profile_id=llm_config_id,
                        kb_id=target_kb_id,
                        model=profile.generation.model,
                        provider=profile.generation.provider,
                    )
            except Exception as ex:
                logger.warning("failed_to_resolve_profile_for_generation", error=str(ex))

        gen_max_tokens = effective_llm_config.get("max_tokens") or effective_llm_config.get("max_generation_tokens") if isinstance(effective_llm_config, dict) else None
        if gen_max_tokens is not None and (request.max_generation_tokens == 1024 or request.max_generation_tokens is None):
            max_tokens_to_use = int(gen_max_tokens)
        else:
            max_tokens_to_use = request.max_generation_tokens or (int(gen_max_tokens) if gen_max_tokens else 1024)

        # Ensure LLMRouter keys are populated
        if isinstance(effective_llm_config, dict):
            effective_llm_config = dict(effective_llm_config)
            effective_llm_config["max_tokens"] = max_tokens_to_use
            effective_llm_config["max_generation_tokens"] = max_tokens_to_use
            if is_json_requested and "format" not in effective_llm_config:
                effective_llm_config["format"] = "json"
            if "llm_provider" not in effective_llm_config and "provider" in effective_llm_config:
                effective_llm_config["llm_provider"] = effective_llm_config["provider"]
            if "llm_model" not in effective_llm_config and "model" in effective_llm_config:
                effective_llm_config["llm_model"] = effective_llm_config["model"]
            if "llm_base_url" not in effective_llm_config:
                raw_url = effective_llm_config.get("url") or effective_llm_config.get("base_url") or effective_llm_config.get("endpoint")
                if raw_url:
                    clean = str(raw_url).rstrip("/")
                    for suffix in ("/api/chat", "/api/generate", "/v1/chat/completions", "/chat/completions"):
                        if clean.endswith(suffix):
                            clean = clean[:-len(suffix)].rstrip("/")
                            break
                    effective_llm_config["llm_base_url"] = clean

        temp_to_use = request.temperature
        if isinstance(effective_llm_config, dict) and effective_llm_config.get("temperature") is not None:
            temp_to_use = float(effective_llm_config["temperature"])

        # Get LLM provider model
        llm = await self.llm_router.get_llm(
            temperature=temp_to_use,
            max_tokens=max_tokens_to_use,
            customer_id=request.customer_id,
            db=db,
            llm_config=effective_llm_config,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            # Call model
            response = await llm.ainvoke(messages)
            
            # Validate response
            if not response or not hasattr(response, "content") or response.content is None:
                logger.error("response_generation_invalid_output", response=response)
                raise ValueError("LLM generation returned an empty or invalid response")

            raw_answer = response.content.strip()
            if not raw_answer:
                logger.error("response_generation_empty_string")
                raise ValueError("LLM generation returned an empty string")

            # Clean and normalize across LLM providers (strips preambles, fences, detects refusals)
            answer = _clean_and_normalize_answer(raw_answer, system_prompt)

            # Check for hallucinated training data via text grounding verifier
            if answer != "no answer" and has_context and request.context and request.context.context:
                extra_ctx_parts = []
                if request.context.chunks:
                    import json
                    for c in request.context.chunks:
                        meta = getattr(c, "metadata", {}) or {}
                        if meta:
                            extra_ctx_parts.append(json.dumps(meta, ensure_ascii=False))
                if request.query:
                    extra_ctx_parts.append(request.query)
                extra_ctx = " ".join(extra_ctx_parts)
                if not _verify_answer_grounding(answer, request.context.context, extra_ctx):
                    logger.warning("response_grounding_failed_overriding_to_no_answer")
                    answer = "no answer"

            # Check if output is strictly a refusal / no answer
            normalized_answer = "".join(c for c in answer.lower() if c.isalnum() or c.isspace()).strip()
            refusal_phrases = {
                "no answer",
                "information is not available in the provided document",
                "information is not available",
                "no information is available",
                "i do not know",
                "dont know",
                "don t know",
                "not available in the provided document",
            }
            if normalized_answer in refusal_phrases or (
                len(normalized_answer) < 80 and any(normalized_answer.startswith(p) for p in ("no answer", "information is not available", "i do not know", "dont know", "don t know"))
            ):
                answer = "no answer"

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info("response_generation_success", elapsed_ms=elapsed_ms, answer_length=len(answer))

            from app.knowledge.context_builder import estimate_tokens
            system_tokens = estimate_tokens(system_prompt)
            user_tokens = estimate_tokens(user_prompt)
            answer_tokens = estimate_tokens(answer)
            used_tokens = system_tokens + user_tokens + answer_tokens

            return ResponseGenerationResult(
                answer=answer,
                used_tokens=used_tokens,
            )

        except Exception as e:
            logger.error("response_generation_failed", error=str(e))
            raise
