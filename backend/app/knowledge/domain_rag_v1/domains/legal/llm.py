from __future__ import annotations
import asyncio
import json
import os
import re
from typing import Any
import structlog
from openai import AsyncOpenAI

logger = structlog.get_logger(__name__)


def _setting(name, default):
    try:
        from app.core.config import get_settings
        settings = get_settings()
        aliases = {
            "OLLAMA_BASE_URL": ("OLLAMA_BASE_URL", "ollama_base_url"),
            "LLM_MODEL": ("LLM_MODEL", "llm_model", "MODEL_NAME", "model_name"),
        }.get(name, (name, name.lower()))
        for attr in aliases:
            value = getattr(settings, attr, None)
            if value:
                return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


def _base_url():
    raw = _setting("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1"):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)].rstrip("/")
    return raw + "/v1"


def chunk_text(text: str, chunk_size: int = 8000, overlap: int = 1000) -> list[dict[str, Any]]:
    """Split text into overlapping windows with positional metadata."""
    chunks = []
    step = chunk_size - overlap
    total_len = len(text)

    for i in range(0, total_len, step):
        chunk_str = text[i : i + chunk_size]
        is_first = (i == 0)
        is_last = (i + chunk_size >= total_len)
        chunks.append({
            "text": chunk_str,
            "index": len(chunks),
            "is_first": is_first,
            "is_last": is_last,
        })
        if is_last:
            break
    return chunks


def _safe_json_loads(raw_text: str) -> dict[str, Any]:
    if not raw_text:
        return {}
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        cleaned = cleaned[start_idx : end_idx + 1]

    try:
        return json.loads(cleaned)
    except Exception:
        return {}


def generic_deep_merge(target: Any, source: Any) -> Any:
    """
    Schema-agnostic recursive merger.
    - Dicts: recursively merged by key.
    - Lists: deduplicated and concatenated.
    - Scalars: prefers non-empty/truthy values.
    """
    if target is None or target == "" or target == [] or target == {}:
        return source
    if source is None or source == "" or source == [] or source == {}:
        return target

    if isinstance(target, dict) and isinstance(source, dict):
        merged = dict(target)
        for k, v in source.items():
            if k in merged:
                merged[k] = generic_deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged

    if isinstance(target, list) and isinstance(source, list):
        merged_list = list(target)
        for item in source:
            if item not in merged_list:
                merged_list.append(item)
        return merged_list

    # Scalars: non-empty replacement
    return source if source is not None and source != "" else target


def merge_chunk_extractions(chunk_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregates multiple chunk extraction results into a unified JSON structure."""
    aggregated: dict[str, Any] = {
        "extracted_fields": {},
        "extra_fields": {},
    }

    for res in chunk_results:
        if not isinstance(res, dict):
            continue

        extracted = res.get("extracted_fields") if "extracted_fields" in res and isinstance(res.get("extracted_fields"), dict) else res
        extra = res.get("extra_fields") if "extra_fields" in res and isinstance(res.get("extra_fields"), dict) else {}

        if isinstance(extracted, dict):
            aggregated["extracted_fields"] = generic_deep_merge(aggregated["extracted_fields"], extracted)

        if isinstance(extra, dict):
            aggregated["extra_fields"] = generic_deep_merge(aggregated["extra_fields"], extra)

    aggregated["extra_fields"]["_chunks_processed"] = len(chunk_results)
    return aggregated


class DomainLLM:
    def __init__(self, model=None, base_url=None, api_key=None):
        """
        LLM client for domain extraction.
        If base_url/api_key are provided, they override defaults
        so the tenant's configured LLM profile (Claude, GPT-4o, etc.) is used.
        """
        self.model = model or _setting("LLM_MODEL", "llama3.2:latest")
        resolved_base_url = base_url or _base_url()
        resolved_api_key = api_key or os.getenv("OLLAMA_API_KEY", "ollama")
        self.client = AsyncOpenAI(
            base_url=resolved_base_url,
            api_key=resolved_api_key,
        )

    async def x_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = 4096,
    ) -> str:
        kwargs = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }

        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = await self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content

        if not content:
            raise RuntimeError("LLM returned an empty response")

        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    @staticmethod
    def _render_user_prompt(
        template: str,
        text_segment: str,
        is_chunk: bool = False,
        chunk_meta: dict[str, Any] | None = None,
    ) -> str:
        """Injects document text/chunk into user prompt template."""
        if not template:
            return f"Document Content:\n{text_segment}"
        if "{content}" in template:
            return template.replace("{content}", text_segment)
        if is_chunk and chunk_meta:
            header_str = f" (Segment {chunk_meta['index'] + 1}, IsHeader={chunk_meta['is_first']}, IsConclusion={chunk_meta['is_last']})"
            return f"Document Content{header_str}:\n{text_segment}\n\n{template}"
        return f"Document Content:\n{text_segment}\n\n{template}"

    async def _extract_single_chunk(
        self,
        chunk: dict[str, Any],
        model: str,
        system_prompt: str | None = None,
        user_prompt_template: str | None = None,
    ) -> dict[str, Any]:
        if system_prompt and user_prompt_template:
            sys_prompt = system_prompt
            user_prompt = self._render_user_prompt(
                user_prompt_template,
                chunk["text"],
                is_chunk=True,
                chunk_meta=chunk,
            )
        else:
            sys_prompt = (
                "You are a strict legal entity extractor. Extract ONLY facts explicitly written in this text segment. "
                "Primary case metadata (parties, appeal number) exists in the header. "
                "Precedents cited in judgment must go under citations.precedents, NOT parties. "
                "Omit fields not found in this segment. Return valid JSON only."
            )

        try:
            raw = await self.x_complete(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=0.0,
            )
            return _safe_json_loads(raw)
        except Exception as exc:
            logger.warning("chunk_extraction_failed", chunk_index=chunk["index"], error=str(exc))
            return {}

    async def complete(
        self,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        document_text: str | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """
        Chunk-based extraction for 7B models. Breaks text into 8k chunks, runs in parallel, merges results.
        """
        text = document_text if document_text is not None else (user_prompt or "")
        effective_model = model or self.model

        # Small documents / single pass
        if len(text) <= 9000:
            if document_text is not None and user_prompt:
                final_user_prompt = self._render_user_prompt(user_prompt, text)
            else:
                final_user_prompt = user_prompt or text

            raw= await self.x_complete(
                system_prompt=system_prompt or "You are a precise document entity extractor.",
                user_prompt=final_user_prompt,
                model=effective_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.debug("extracted json", extra={"info": raw,})
            return _safe_json_loads(raw)
        # Large documents: 8k sliding chunk loop in parallel
        chunks = chunk_text(text, chunk_size=8000, overlap=1000)
        logger.info("chunked_extraction_start", model=effective_model, chunk_count=len(chunks), doc_len=len(text))

        tasks = [
            self._extract_single_chunk(
                chunk,
                effective_model,
                system_prompt=system_prompt,
                user_prompt_template=user_prompt,
            )
            for chunk in chunks
        ]
        chunk_results = await asyncio.gather(*tasks)

        merged_payload = merge_chunk_extractions(chunk_results)
        logger.info(f"final result \n{merged_payload}")
        return json.dumps(merged_payload, ensure_ascii=False)