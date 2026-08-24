
import json
import re
from typing import Any, Dict, List, Optional
from app.knowledge.transformers.base import BaseResponseTransformer


class LegalResponseTransformer(BaseResponseTransformer):
    """
    Dedicated transformer for Legal domain responses.
    Guarantees strict legal JSON contract:
    {
      "cases": [
        {
          "case_title": "...",
          "court_type": "...",
          "judge": "...",
          "decision_date": "...",
          "outcome": "...",
          "parties": "...",
          "respondents": [...],
          "plaintiffs": [...],
          "sections_or_articles_involved": [...],
          "case_summary": "..."
        }
      ]
    }
    """

    LEGAL_CANONICAL_KEYS = [
        "case_title",
        "title",
        "court_type",
        "court",
        "judge",
        "decision_date",
        "outcome",
        "parties",
        "respondents",
        "plaintiffs",
        "sections_or_articles_involved",
        "current_status",
        "case_summary",
        "summary", 
        "linked_cases"
    ]

    def transform(self, raw_output: str, system_prompt: str = "") -> str:
        if not raw_output or not raw_output.strip():
            return "no answer"

        clean_text = raw_output.strip()
        lower_ans = clean_text.lower()

        if lower_ans in {"no answer", "information is not available in the provided document.", "i do not know", "dont know", "don t know"}:
            return "no answer"

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
        ]
        has_refusal = any(p in lower_ans for p in refusal_indicators)
        if has_refusal:
            is_populated_json = (
                (clean_text.startswith("{") or clean_text.startswith("[{"))
                and ('"title"' in clean_text or '"case_title"' in clean_text or '"name"' in clean_text)
                and len(clean_text) > 40
            )
            if not is_populated_json:
                is_json_requested = "json" in system_prompt.lower() or '{"' in system_prompt or "{'" in system_prompt
                if is_json_requested:
                    return json.dumps({"cases": []})
                return "no answer"

        # 1. Strip markdown fences if present
        if "```" in clean_text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
            if match:
                candidate = match.group(1).strip()
                if candidate.startswith("{") or candidate.startswith("["):
                    clean_text = candidate

        # 2. Extract embedded JSON
        if not clean_text.startswith("{") and not clean_text.startswith("["):
            match = re.search(r"(\{[\s\S]*\}|\[\s*\{[\s\S]*\}\s*\])", clean_text)
            if match:
                clean_text = match.group(1).strip()

        # 3. Direct JSON parsing
        try:
            parsed = json.loads(clean_text)
            if isinstance(parsed, list):
                parsed = {"cases": parsed}
            return json.dumps(parsed, indent=2)
        except Exception:
            parsed_cases = self._parse_legal_markdown(clean_text)
            if parsed_cases:
                return json.dumps({"cases": parsed_cases}, indent=2)
            return json.dumps({"cases": []})

    def _sanitize_legal_record(self, rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(rec, dict):
            return None

        # Filter out pure conversational records (e.g. {"title": "There is one case with conviction"})
        title_val = str(rec.get("case_title") or rec.get("title") or rec.get("name") or "").strip()
        lower_title = title_val.lower()
        if (
            lower_title.startswith(("there is", "there are", "here is", "here are", "based on", "the context", "the following", "note that", "unfortunately", "additionally", "these are"))
            or len(title_val) < 3
        ):
            # Check if this record has actual legal details, else drop it
            has_substance = any(
                k in rec for k in ("court", "court_type", "judge", "parties", "outcome", "conviction", "respondents", "plaintiffs", "sections")
            )
            if not has_substance:
                return None

        case: Dict[str, Any] = {
            "case_title": title_val,
            "title": title_val,
            "court_type": "N/A",
            "court": "N/A",
            "judge": "N/A",
            "decision_date": "N/A",
            "outcome": "N/A",
            "current_status": "N/A",
            "status": "N/A",
            "parties": "N/A",
            "respondents": [],
            "plaintiffs": [],
            "sections_or_articles_involved": [],
            "case_summary": "",
            "summary": "",
        }

        for k, v in rec.items():
            k_clean = str(k).lower().strip()
            if not v and (k_clean.startswith(("here_is", "1_", "2_", "note", "as_per")) or len(k_clean) > 25):
                continue

            # Canonical alias normalization
            if k_clean in ("case_title", "title", "name"):
                case["case_title"] = v
                case["title"] = v
            elif k_clean in ("parties", "party"):
                case["parties"] = v
                if not case["case_title"] or case["case_title"] == "N/A":
                    case["case_title"] = v
                    case["title"] = v
            elif k_clean in ("court", "court_type", "court_source", "forum", "tribunal"):
                case["court_type"] = v
                case["court"] = v
            elif k_clean in ("judge", "judges", "judge_coram", "coram", "bench", "presided_by"):
                case["judge"] = v
                case["judges"] = v
            elif k_clean in ("decision_date", "date", "judgment_date", "order_date"):
                case["decision_date"] = str(v)
            elif k_clean in ("outcome", "disposition", "status", "current_status", "decision", "conviction_status", "appeal_status"):
                case["outcome"] = v
                case["current_status"] = v
                case["status"] = v
            elif k_clean in ("plaintiff", "plaintiffs", "petitioner", "petitioners", "appellant", "appellants"):
                case["plaintiffs"] = v if isinstance(v, list) else [str(v)]
                case["plaintiff"] = v
            elif k_clean in ("respondent", "respondents", "accused", "defendant", "defendants"):
                case["respondents"] = v if isinstance(v, list) else [str(v)]
                case["respondent"] = v
            elif k_clean in ("sections", "sections_involved", "sections_or_articles_involved", "offences", "offence", "statute", "conviction"):
                case["offences"] = v
                case["conviction"] = v
                if isinstance(v, list):
                    case["sections_or_articles_involved"] = v
                else:
                    found = re.findall(r"(?:Sections?|Articles?|Acts?|IPC|Arms Act)\s*[^,;.]+", str(v), flags=re.IGNORECASE)
                    if found:
                        case["sections_or_articles_involved"] = [s.strip() for s in found]
                    else:
                        case["sections_or_articles_involved"] = [s.strip() for s in re.split(r"[,;]", str(v)) if s.strip()]
            elif k_clean in ("case_summary", "summary", "synopsis"):
                case["case_summary"] = v
                case["summary"] = v
            else:
                case[k] = v

        # Fallback summary if missing
        if not case["case_summary"]:
            case["case_summary"] = f"Case record for {case['case_title']}."
            case["summary"] = case["case_summary"]

        return case

    def _sanitize_legal_structure(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, list):
            sanitized = [self._sanitize_legal_record(item) for item in data]
            return {"cases": [c for c in sanitized if c is not None]}
        elif isinstance(data, dict):
            # Extract case list from common root keys
            cases_list = data.get("cases") or data.get("records") or data.get("results")
            if isinstance(cases_list, list):
                sanitized = [self._sanitize_legal_record(item) for item in cases_list]
                return {"cases": [c for c in sanitized if c is not None]}
            elif "cases" in data:
                return data
            else:
                # If single case dict
                single_case = self._sanitize_legal_record(data)
                return {"cases": [single_case] if single_case else []}
        return {"cases": []}

    def _parse_legal_markdown(self, text: str) -> List[Dict[str, Any]]:
        cases = []
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
            if lower_title.startswith(("based on", "the context", "here is", "here are", "note that", "the following", "unfortunately")) or len(title_line) < 3:
                continue

            case: Dict[str, Any] = {
                "case_title": title_line,
                "title": title_line,
            }
            if inline_summary:
                case["case_summary"] = inline_summary
                case["summary"] = inline_summary

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

                    val: Any = v_clean
                    if v_clean.startswith("[") and v_clean.endswith("]"):
                        val = [item.strip(" '\"[]") for item in re.split(r"[,;]", v_clean) if item.strip(" '\"[]")]

                    field_key = re.sub(r"[^a-zA-Z0-9]+", "_", k_raw).strip("_").lower()
                    case[field_key] = val
                elif not clean_l.lower().startswith(("note", "here is", "the following")):
                    summary_parts.append(clean_l)

            if summary_parts:
                combined = ". ".join(summary_parts)
                case["case_summary"] = f"{case.get('case_summary', '')}. {combined}".strip(". ")
                case["summary"] = case["case_summary"]

            cases.append(self._sanitize_legal_record(case))

        return cases
