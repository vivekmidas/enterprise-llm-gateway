# ==============================================================================
# BLOCK COMMENT: Self-contained ProfanityGuardAgent System Plugin
# Epic: Independent Custom Node Publishing & Execution Robustness (Phase 2)
# Story: EPIC-GUARD-PROFANITY-001 / STORY-PROFANITY-FILTER-001
# Design Changes:
#   1. All profane word lists (`strong_words`, `mild_words`, `profanity_patterns`)
#      are defined solely in `manifest.json` (`system_properties`) so new words
#      or phonetic patterns can be added without touching Python code.
#   2. Tenants extend the list via `user_properties` (`user_profanity_words`,
#      `user_profanity_patterns`).
#   3. Single-pass combined regex with prioritized named groups
#      (`strong_word` -> `user_word` -> `mild_word` -> `phonetic_pattern`):
#      - Words matched as profane (`strong_word`, `user_word`, `mild_word`) are
#        consumed immediately and excluded from `phonetic_pattern` matches.
#      - Eliminates span sorting/merging and prevents duplicate matches across spans.
#   4. Simplified output metadata reporting:
#      - `identified_words`: deduplicated list of `{"word": ..., "criterion": ...}`
#      - `overall_rating`: "None" | "Mild" | "Moderate" | "Strong"
# ==============================================================================

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import BaseNode


class ProfanityGuardAgent(BaseNode):
    """
    Profanity Guard node driven entirely by manifest system_properties
    and tenant user_properties.
    """

    def __init__(self, **data):
        super().__init__(**data)
        self._analyzer = None

    def _ensure_analyzer(self):
        """Lazy initializer for Presidio AnalyzerEngine to avoid startup latency."""
        if self._analyzer is None:
            try:
                from presidio_analyzer import AnalyzerEngine
                self._analyzer = AnalyzerEngine()
            except Exception as exc:
                self.logger.warning("presidio_analyzer_init_skipped", error=str(exc))
                self._analyzer = False

    async def init(self) -> None:
        await super().init()

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        await super().validate_input(inp)
        return None

    @staticmethod
    def _parse_list(val: Any) -> List[str]:
        """Splits a comma/newline-separated string or list into trimmed entries."""
        if not val:
            return []
        if isinstance(val, (list, set, tuple)):
            out: List[str] = []
            for item in val:
                out.extend(ProfanityGuardAgent._parse_list(item))
            return out
        if isinstance(val, str):
            return [w.strip() for w in re.split(r"[,\n;]+", val) if w and w.strip()]
        return []

    @staticmethod
    def _build_word_branch(group_name: str, words: List[str]) -> Optional[str]:
        """Builds a named regex group matching whole words (and common inflections)."""
        cleaned = [re.escape(w.lower()) for w in words if w]
        if not cleaned:
            return None
        cleaned.sort(key=len, reverse=True)
        joined = "|".join(cleaned)
        return rf"(?P<{group_name}>\b(?:{joined})(?:er|ers|ing|ed|s|es|y)?\b)"

    @classmethod
    def _build_combined_regex(
        cls,
        strong_words: List[str],
        user_words: List[str],
        mild_words: List[str],
        raw_patterns: List[str],
    ) -> Optional[re.Pattern]:
        """
        Compiles a single prioritized regex (`strong_word` | `user_word` | `mild_word` | `phonetic_pattern`).
        Because regex alternation is left-biased and non-overlapping, any word matched by
        strong/user/mild word lists is never matched again by phonetic patterns.
        """
        branches: List[str] = []

        for group_name, word_list in (
            ("strong_word", strong_words),
            ("user_word", user_words),
            ("mild_word", mild_words),
        ):
            branch = cls._build_word_branch(group_name, word_list)
            if branch:
                branches.append(branch)

        valid_patterns: List[str] = []
        for pat_str in raw_patterns:
            try:
                re.compile(pat_str, re.IGNORECASE)
                valid_patterns.append(f"(?:{pat_str})")
            except re.error:
                continue

        if valid_patterns:
            branches.append(f"(?P<phonetic_pattern>{'|'.join(valid_patterns)})")

        if not branches:
            return None

        return re.compile("|".join(branches), re.IGNORECASE)

    @staticmethod
    def _compute_overall_rating(identified: List[Dict[str, str]]) -> str:
        """Determines overall profanity rating from matched criteria."""
        if not identified:
            return "None"
        criteria = {item["criterion"] for item in identified}
        if criteria.intersection({"strong_word", "user_word", "phonetic_pattern"}):
            return "Strong"
        if len(identified) >= 3:
            return "Moderate"
        return "Mild"

    async def execute(self, inp: NodeInput) -> NodeOutput:
        self._ensure_analyzer()

        # Resolve manifest system_properties + user_properties + runtime overrides
        config: Dict[str, Any] = self.get_resolved_properties(instance_overrides=inp.config or {})

        # 1. Read word lists & patterns from manifest / config (no hardcoded words in code)
        strong_words = self._parse_list(config.get("strong_words"))
        mild_words = self._parse_list(config.get("mild_words"))
        user_words = self._parse_list(
            config.get("user_profanity_words")
            or config.get("profanity_words_tenant")
            or config.get("additional_profanity_words")
        )
        raw_patterns = self._parse_list(config.get("profanity_patterns")) + self._parse_list(
            config.get("user_profanity_patterns")
        )

        combined_re = self._build_combined_regex(strong_words, user_words, mild_words, raw_patterns)

        # 2. Action & formatting settings
        action = str(config.get("action") or "highlight").strip().lower()
        highlight_marker = str(config.get("highlight_marker") or "**[{word}]**")
        redact_replacement = str(config.get("redact_replacement") or "[PROFANITY_REDACTED]")

        data_val = self.get_input_data(inp)
        identified_words: List[Dict[str, str]] = []
        seen_words: set = set()

        def process_profanity():
            def replace_match(match: re.Match) -> str:
                word = match.group(0)
                criterion = next(
                    (k for k, v in match.groupdict().items() if v is not None),
                    "strong_word",
                )
                word_key = word.lower()
                if word_key not in seen_words:
                    seen_words.add(word_key)
                    identified_words.append({"word": word, "criterion": criterion})

                if action == "flag_only":
                    return word
                if action == "redact":
                    return redact_replacement
                return (
                    highlight_marker.replace("{word}", word)
                    if "{word}" in highlight_marker
                    else f"{highlight_marker}{word}{highlight_marker}"
                )

            def filter_text(text: str) -> str:
                if not text or not combined_re:
                    return text
                return combined_re.sub(replace_match, text)

            def traverse(val: Any) -> Any:
                if isinstance(val, str):
                    stripped = val.strip()
                    if (stripped.startswith("{") and stripped.endswith("}")) or (
                        stripped.startswith("[") and stripped.endswith("]")
                    ):
                        try:
                            parsed = json.loads(val)
                            if isinstance(parsed, (dict, list)):
                                return json.dumps(traverse(parsed))
                        except Exception:
                            pass
                    return filter_text(val)
                if isinstance(val, dict):
                    return {
                        k: (v if k in {"context", "user_data"} else traverse(v))
                        for k, v in val.items()
                    }
                if isinstance(val, list):
                    return [traverse(item) for item in val]
                return val

            return traverse(data_val)

        new_data_val = await asyncio.to_thread(process_profanity)
        out_data = self.set_output_data(inp, new_data_val)

        # 3. Build rating and response
        overall_rating = self._compute_overall_rating(identified_words)
        offended_words = [item["word"] for item in identified_words]
        profanity_detected = bool(identified_words)

        violations: List[str] = offended_words
        status = "success"
        error_message: Optional[str] = None
        error_code = 200

        if profanity_detected and action == "reject":
            violations = ["profanity"]
            status = "failure"
            error_code = 400
            error_message = f"Profanity rejected (rating={overall_rating}): {', '.join(offended_words)}"

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            status=status,
            error_message=error_message,
            error_code=error_code,
            violations=violations,
            metadata={
                "profanity_detected": profanity_detected,
                "overall_rating": overall_rating,
                "identified_words": identified_words,
                "offended_words": offended_words,
                "action_taken": action if profanity_detected else "none",
            },
        )
