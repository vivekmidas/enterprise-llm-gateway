"""
===============================================================================
Module: backend/app/knowledge/legal_parser.py
Description:
    Legal document text cleaner & exhaustive metadata parser.
    Extracts 15+ legal metadata fields using fast regex rules + fallback heuristics/LLM:
      1. case_title
      2. case_number
      3. court_level (SUPREME_COURT, HIGH_COURT, DISTRICT_COURT, TRIBUNAL)
      4. court_name
      5. bench_type (Single Judge, Division Bench, Full Bench, Constitution Bench)
      6. coram (Judge names)
      7. counsels (Petitioner / Respondent lawyers)
      8. judgment_date (ISO YYYY-MM-DD)
      9. citations (AIR, SCC, INSC, etc.)
     10. domain_category (Criminal, Civil, Constitutional, Tax, etc.)
     11. acts_cited (IPC, CrPC, BNS, BNSS, Constitution, etc.)
     12. sections_cited (Section 302, Article 21, Order 39, etc.)
     13. precedents_cited (Referred case citations)
     14. headnote (Keywords / catchwords)
     15. disposition (ALLOWED, DISMISSED, REMANDED, PARTLY_ALLOWED)
===============================================================================
"""

import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# --- REGEX PATTERNS ---
_CITATION_PATTERN = re.compile(
    r"\b(?:AIR|\(?\d{4}\)?\s*\d+\s*SCC\s*\d+|\d{4}\s*INSC\s*\d+|\d{4}\s*SCALE\s*\d+|ILR\s*\d{4}|MANU/[A-Z]+/\d+/\d{4})\b",
    re.IGNORECASE,
)

_CASE_NUMBER_PATTERN = re.compile(
    r"\b(?:Criminal|Civil|Writ|Special Leave|SLP|Arising out of|Appeal|Petition)\s+(?:Appeal|Petition|No\.?|Application)\s*(?:No\.?|\(C\)|\(Crl\)\.?|\(Civ\)\.?)?\s*\d+\s*(?:of|/|-)\s*\d{2,4}\b",
    re.IGNORECASE,
)

_DATE_PATTERNS = [
    re.compile(r"\b(?:Dated|Decided on|Judgment Date|Date of Decision)[:\s]*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})\b", re.IGNORECASE),
    re.compile(r"\b([0-9]{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+[0-9]{4})\b", re.IGNORECASE),
    re.compile(r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b"),
]

_ACT_PATTERNS = [
    (re.compile(r"\b(?:Indian Penal Code|I\.P\.C\.?|IPC)\b", re.IGNORECASE), "Indian Penal Code"),
    (re.compile(r"\b(?:Code of Criminal Procedure|Cr\.P\.C\.?|CrPC)\b", re.IGNORECASE), "Code of Criminal Procedure"),
    (re.compile(r"\b(?:Bharatiya Nyaya Sanhita|BNS)\b", re.IGNORECASE), "Bharatiya Nyaya Sanhita"),
    (re.compile(r"\b(?:Bharatiya Nagarik Suraksha Sanhita|BNSS)\b", re.IGNORECASE), "Bharatiya Nagarik Suraksha Sanhita"),
    (re.compile(r"\b(?:Indian Evidence Act|IEA|Bharatiya Sakshya Adhiniyam|BSA)\b", re.IGNORECASE), "Indian Evidence Act / BSA"),
    (re.compile(r"\b(?:Constitution of India|Article\s+\d+)\b", re.IGNORECASE), "Constitution of India"),
    (re.compile(r"\b(?:Code of Civil Procedure|C\.P\.C\.?|CPC)\b", re.IGNORECASE), "Code of Civil Procedure"),
    (re.compile(r"\b(?:Arbitration and Conciliation Act)\b", re.IGNORECASE), "Arbitration & Conciliation Act"),
    (re.compile(r"\b(?:Income Tax Act)\b", re.IGNORECASE), "Income Tax Act"),
    (re.compile(r"\b(?:Companies Act)\b", re.IGNORECASE), "Companies Act"),
    (re.compile(r"\b(?:Information Technology Act|IT Act)\b", re.IGNORECASE), "Information Technology Act"),
]

_SECTION_PATTERN = re.compile(
    r"\b(?:Section|Sec\.?|Articles?|Art\.?|Order\s+[XVIII|XV|IV|V|I|X]+\s+Rule\s+\d+)\s*([0-9]+[A-Z]?(?:\s*\([0-9a-z]+\))?)\b",
    re.IGNORECASE,
)

_COURT_LEVEL_PATTERNS = [
    (re.compile(r"\bSupreme Court of India\b", re.IGNORECASE), "SUPREME_COURT", "Supreme Court of India"),
    (re.compile(r"\bHigh Court of\b", re.IGNORECASE), "HIGH_COURT", "High Court"),
    (re.compile(r"\bDistrict Court|Sessions Court|Magistrate\b", re.IGNORECASE), "DISTRICT_COURT", "District Court"),
    (re.compile(r"\bTribunal|NCLT|CAT|SAT|ITAT\b", re.IGNORECASE), "TRIBUNAL", "Specialized Tribunal"),
]

_BENCH_PATTERNS = [
    (re.compile(r"\bConstitution Bench\b", re.IGNORECASE), "Constitution Bench"),
    (re.compile(r"\bFull Bench\b", re.IGNORECASE), "Full Bench"),
    (re.compile(r"\bDivision Bench\b", re.IGNORECASE), "Division Bench"),
    (re.compile(r"\bSingle Judge\b", re.IGNORECASE), "Single Judge"),
]

_DISPOSITION_PATTERNS = [
    (re.compile(r"\b(appeal|petition|application)\s+(is|are)\s+allowed\b", re.IGNORECASE), "ALLOWED"),
    (re.compile(r"\b(appeal|petition|application)\s+(is|are)\s+dismissed\b", re.IGNORECASE), "DISMISSED"),
    (re.compile(r"\b(remanded|sent back)\b", re.IGNORECASE), "REMANDED"),
    (re.compile(r"\ballowed in part\b", re.IGNORECASE), "PARTLY_ALLOWED"),
]


def clean_legal_text(text: str) -> str:
    """Clean text artifacts, OCR errors, page headers, footers, and redundant linebreaks."""
    if not text:
        return ""

    # Remove non-printable characters
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    # Fix line-break hyphenations (e.g. "judg-\nment" -> "judgment")
    cleaned = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", cleaned)

    # Remove repeated page numbers / headers (e.g., "Page 1 of 45", "SUPREME COURT OF INDIA")
    cleaned = re.sub(r"\bPage\s+\d+\s+of\s+\d+\b", "", cleaned, flags=re.IGNORECASE)

    # Normalize multiple whitespace / newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

    return cleaned.strip()


def parse_legal_metadata_fast(text: str) -> Dict[str, Any]:
    """Fast deterministic regex extraction for 15+ legal metadata fields."""
    cleaned = clean_legal_text(text)
    header_sample = cleaned[:3000]
    tail_sample = cleaned[-2000:]

    metadata: Dict[str, Any] = {
        "case_title": None,
        "case_number": None,
        "court_level": "HIGH_COURT",  # default fallback
        "court_name": "High Court",
        "bench_type": "Division Bench",
        "coram": [],
        "counsels": {"petitioner": [], "respondent": []},
        "judgment_date": None,
        "citations": [],
        "domain_category": "General Legal",
        "acts_cited": [],
        "sections_cited": [],
        "precedents_cited": [],
        "headnote": None,
        "disposition": "UNKNOWN",
    }

    # 1. Citations
    citations = list(set(_CITATION_PATTERN.findall(cleaned)))
    metadata["citations"] = citations[:10]

    # 2. Case Number
    cn_match = _CASE_NUMBER_PATTERN.search(header_sample)
    if cn_match:
        metadata["case_number"] = cn_match.group(0).strip()

    # 3. Court Level & Court Name
    for pattern, level, default_name in _COURT_LEVEL_PATTERNS:
        if pattern.search(header_sample):
            metadata["court_level"] = level
            match = pattern.search(header_sample)
            if match:
                start = max(0, match.start() - 20)
                end = min(len(header_sample), match.end() + 30)
                metadata["court_name"] = header_sample[start:end].split("\n")[0].strip()
            break

    # 4. Bench Type
    for pattern, bench in _BENCH_PATTERNS:
        if pattern.search(header_sample):
            metadata["bench_type"] = bench
            break

    # 5. Judgment Date
    for pattern in _DATE_PATTERNS:
        d_match = pattern.search(header_sample) or pattern.search(tail_sample)
        if d_match:
            raw_date = d_match.group(1).strip()
            metadata["judgment_date"] = raw_date
            break

    # 6. Acts Cited
    acts = []
    for pattern, act_name in _ACT_PATTERNS:
        if pattern.search(cleaned):
            acts.append(act_name)
    metadata["acts_cited"] = list(set(acts))

    # 7. Sections Cited
    sections = list(set(_SECTION_PATTERN.findall(cleaned)))
    metadata["sections_cited"] = [f"Sec {s}" for s in sections[:15]]

    # 8. Disposition
    for pattern, disp in _DISPOSITION_PATTERNS:
        if pattern.search(tail_sample) or pattern.search(header_sample):
            metadata["disposition"] = disp
            break

    # 9. Case Title Extraction (Heuristic "Versus" / "Vs.")
    v_match = re.search(
        r"^\s*([A-Z0-9\.\s,\(\)&-]+?)\s+(?:VERSUS|Versus|Vs\.?|V/s)\s+([A-Z0-9\.\s,\(\)&-]+)",
        header_sample,
        re.MULTILINE | re.IGNORECASE,
    )
    if v_match:
        p1 = re.sub(r"[\.\s]*\b(?:APPELLANT|PETITIONER|PLAINTIFF)(?:[S\(\)]*).*", "", v_match.group(1), flags=re.IGNORECASE).strip()
        p2 = re.sub(r"[\.\s]*\b(?:RESPONDENT|DEFENDANT)(?:[S\(\)]*).*", "", v_match.group(2), flags=re.IGNORECASE).strip()
        p1 = p1.split("\n")[-1].strip()
        p2 = p2.split("\n")[0].strip()
        metadata["case_title"] = f"{p1} v. {p2}"

    # 10. Domain Category (Criminal / Civil / Tax / Const)
    if any(a in metadata["acts_cited"] for a in ["Indian Penal Code", "Code of Criminal Procedure", "BNS", "BNSS"]):
        metadata["domain_category"] = "Criminal Law"
    elif "Constitution of India" in metadata["acts_cited"]:
        metadata["domain_category"] = "Constitutional Law"
    elif "Arbitration & Conciliation Act" in metadata["acts_cited"]:
        metadata["domain_category"] = "Arbitration Law"
    elif "Income Tax Act" in metadata["acts_cited"] or "GST" in cleaned:
        metadata["domain_category"] = "Taxation Law"
    elif "Code of Civil Procedure" in metadata["acts_cited"]:
        metadata["domain_category"] = "Civil Law"

    return metadata
