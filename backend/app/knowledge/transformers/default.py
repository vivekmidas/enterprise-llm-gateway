import json
import re
from typing import Any, Dict, List, Optional
from app.knowledge.transformers.base import BaseResponseTransformer


class DefaultResponseTransformer(BaseResponseTransformer):
    """
    100% domain-agnostic response transformer.
    - Directly passes valid JSON structures.
    - Strips markdown codeblocks.
    - Sanitizes keys against system prompt schema if requested.
    - Normalizes markdown bullet points to snake_case attributes.
    """

    def transform(self, raw_output: str, system_prompt: str = "") -> str:
        if not raw_output or not raw_output.strip():
            return "no answer"

        clean_text = raw_output.strip()
        lower_ans = clean_text.lower()

        # Dynamic root key detection from system prompt (e.g. {"books": [...]}, {"cases": [...]})
        root_key = "records"
        target_keys: List[str] = []
        if system_prompt:
            key_match = re.search(r'\{"([a-zA-Z0-9_]+)":\s*\[', system_prompt)
            if key_match:
                root_key = key_match.group(1)
            target_keys = self._extract_schema_keys_from_prompt(system_prompt)

        is_json_requested = "json" in system_prompt.lower() or '{"' in system_prompt or "{'" in system_prompt or root_key != "records"

        # Refusal normalization
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
            is_populated_json = (
                (clean_text.startswith("{") or clean_text.startswith("[{"))
                and ('"title"' in clean_text or '"case_title"' in clean_text or '"name"' in clean_text)
                and len(clean_text) > 40
            )
            if not is_populated_json:
                if is_json_requested:
                    res = {root_key: []}
                    if root_key != "cases" and ("case" in system_prompt.lower() or "cases" in system_prompt.lower()):
                        res["cases"] = []
                    return json.dumps(res)
                return "no answer"

        # 1. Strip markdown fences if present: ```json ... ```
        if "```" in clean_text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
            if match:
                candidate = match.group(1).strip()
                if candidate.startswith("{") or candidate.startswith("["):
                    clean_text = candidate

        # 2. Extract embedded JSON object/array
        if is_json_requested and not clean_text.startswith("{") and not clean_text.startswith("["):
            match = re.search(r"(\{[\s\S]*\}|\[\s*\{[\s\S]*\}\s*\])", clean_text)
            if match:
                clean_text = match.group(1).strip()

        # 3. Parse JSON directly if valid
        try:
            parsed = json.loads(clean_text)
            root_key = "records"
            if system_prompt:
                key_match = re.search(r'\{"([a-zA-Z0-9_]+)":\s*\[', system_prompt)
                if key_match:
                    root_key = key_match.group(1)
            target_keys = self._extract_schema_keys_from_prompt(system_prompt)
            sanitized = self._sanitize_structure(parsed, root_key, target_keys)
            return json.dumps(sanitized, indent=2)
        except Exception:
            pass

        # 4. Parse markdown bullet points into key-value records if JSON requested or bullet keys present
        has_bullets = bool(re.search(r"(?:^|\n)\s*[-*•]\s+\*?\*?[A-Za-z0-9_\s]+\*?\*?:", clean_text))
        has_numbered = bool(re.search(r"(?:^|\n)\s*\d+[\.\)]\s+\*?\*?", clean_text))
        if has_bullets or has_numbered:
            target_keys = self._extract_schema_keys_from_prompt(system_prompt)
            parsed_records = self._parse_markdown(clean_text, target_keys)
            if parsed_records:
                root_key = "records"
                if system_prompt:
                    key_match = re.search(r'\{"([a-zA-Z0-9_]+)":\s*\[', system_prompt)
                    if key_match:
                        root_key = key_match.group(1)
                return json.dumps({root_key: parsed_records}, indent=2)

        # 5. Plain text response if JSON was not requested
        if not is_json_requested:
            return clean_text

        root_key = "records"
        if system_prompt:
            key_match = re.search(r'\{"([a-zA-Z0-9_]+)":\s*\[', system_prompt)
            if key_match:
                root_key = key_match.group(1)
        return json.dumps({root_key: [], "raw_response": clean_text})

    def _extract_schema_keys_from_prompt(self, prompt: str) -> List[str]:
        if not prompt:
            return []
        found_keys = re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s*:', prompt)
        container_keys = {"cases", "records", "items", "books", "data", "results", "documents", "response", "schema"}
        return [k for k in dict.fromkeys(found_keys) if k.lower() not in container_keys]

    def _align_key(self, key: str, target_keys: List[str]) -> str:
        if not target_keys:
            return key
        k_clean = key.lower().replace("_", "")
        for tk in target_keys:
            tk_clean = tk.lower().replace("_", "")
            if tk_clean == k_clean or tk_clean == k_clean + "s" or k_clean == tk_clean + "s" or k_clean in tk_clean or tk_clean in k_clean:
                return tk
        return key

    def _sanitize_record(self, rec: Dict[str, Any], target_keys: List[str]) -> Optional[Dict[str, Any]]:
        if not isinstance(rec, dict):
            return None

        # Filter out conversational noise records
        title_val = str(rec.get("title") or rec.get("name") or rec.get("case_title") or "").strip()
        lower_title = title_val.lower()
        if lower_title.startswith(("there is", "there are", "here is", "here are", "based on", "the context", "the following", "note that", "unfortunately", "additionally")):
            if len(rec) <= 2:
                return None

        cleaned = {}
        for k, v in rec.items():
            k_str = str(k).strip()
            if not k_str or (v == "" and len(k_str) > 25):
                continue
            k_lower = k_str.lower()
            if k_lower.startswith(("here_is", "here_are", "note", "as_per", "the_following")):
                continue
            if re.match(r"^\d+_", k_lower) and not v:
                continue
            aligned_k = self._align_key(k_str, target_keys)
            cleaned[aligned_k] = v
        return cleaned if cleaned else None

    def _sanitize_structure(self, data: Any, root_key: str, target_keys: List[str]) -> Any:
        if isinstance(data, list):
            sanitized_list = [self._sanitize_record(item, target_keys) for item in data]
            return {root_key: [item for item in sanitized_list if item is not None]}
        elif isinstance(data, dict):
            return {
                rk: [self._sanitize_record(item, target_keys) for item in rval if self._sanitize_record(item, target_keys) is not None] if isinstance(rval, list)
                else (self._sanitize_record(rval, target_keys) if isinstance(rval, dict) else rval)
                for rk, rval in data.items()
            }
        return data

    def _parse_markdown(self, text: str, target_keys: List[str]) -> List[Dict[str, Any]]:
        records = []
        chunks = re.split(r"(?:^|\n)\s*(?:\d+[\.\)]|\#\#+)\s+", text)
        if len(chunks) <= 1:
            chunks = re.split(r"\n\s*\n\s*(?=\*\*)", text)

        for chunk in chunks:
            lines = [line.strip() for line in chunk.strip().splitlines() if line.strip()]
            if not lines:
                continue

            inline_match = re.match(r"^\*\*([^*]+)\*\*:\s*(.*)", lines[0])
            if inline_match:
                title_line = inline_match.group(1).strip()
                inline_summary = inline_match.group(2).strip()
            else:
                title_line = lines[0].replace("**", "").rstrip(":").strip()
                inline_summary = ""

            lower_title = title_line.lower()
            if lower_title.startswith(("based on", "the context", "here is", "here are", "note that", "the following", "unfortunately", "there is", "there are", "additionally")) or len(title_line) < 3:
                continue

            title_key = self._align_key("title", target_keys)
            record: Dict[str, Any] = {title_key: title_line}
            if title_key != "title":
                record["title"] = title_line
            if inline_summary:
                sum_key = self._align_key("summary", target_keys)
                record[sum_key] = inline_summary

            summary_parts = []
            for line in lines[1:]:
                is_bullet = bool(re.match(r"^[-*•]\s+", line)) or bool(re.match(r"^\*\*[A-Za-z0-9_\s]+\*\*:", line))
                clean_l = re.sub(r"^[-*•\d\.]+\s*", "", line).strip()
                if ":" in clean_l and is_bullet:
                    k, v = clean_l.split(":", 1)
                    k_raw = k.replace("**", "").replace("*", "").strip()
                    v_clean = v.replace("**", "").replace("*", "").strip()
                    if not v_clean or k_raw.lower().startswith(("here is", "note", "the following")):
                        continue
                    field_key = re.sub(r"[^a-zA-Z0-9]+", "_", k_raw).strip("_").lower()
                    if not field_key:
                        continue
                    aligned_key = self._align_key(field_key, target_keys)
                    if v_clean.startswith("[") and v_clean.endswith("]"):
                        record[aligned_key] = [item.strip(" '\"[]") for item in re.split(r"[,;]", v_clean) if item.strip(" '\"[]")]
                    else:
                        record[aligned_key] = v_clean
                elif not clean_l.lower().startswith(("note", "here is", "the following")):
                    summary_parts.append(clean_l)

            if summary_parts:
                sum_key = self._align_key("summary", target_keys)
                combined = ". ".join(summary_parts)
                record[sum_key] = f"{record.get(sum_key, '')}. {combined}".strip(". ")

            records.append(record)
        return records
