"""
Typed Metadata Lexical & Phonetic Matcher
A domain-agnostic, generic matching engine supporting:
- Soundex: Traditional phonetic encoding.
- Metaphone: Lawrence Philips' phonetic encoding for English and romanized names.
- NYSIIS: New York State Identification and Intelligence System for surname matching.
- Jaro-Winkler Similarity: Specialized metric for proper names, prefixes, and transpositions.
- Field Typing: ENTITY, TEXT, and VALUE specialized scoring strategies.
"""

import re
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class FieldType(str, Enum):
    ENTITY = "entity"
    TEXT = "text"
    VALUE = "value"


# Universal noise tokens to ignore during token extraction
DEFAULT_NOISE_TOKENS: Set[str] = {
    # Legal / Administrative Honorifics & Roles
    "smt", "shri", "sri", "hon", "honble", "justice", "judge", "mr", "mrs", "ms", "dr",
    "j", "cj", "jj", "bench", "coram",
    "petitioner", "petitioners", "respondent", "respondents", "appellant", "appellants",
    "accused", "plaintiff", "defendant", "applicant", "advocate", "counsel",
    # Connectors, Prepositions & Fillers
    "cases", "case", "presided", "by", "before", "for", "against", "under", "regarding",
    "involving", "matter", "matters", "vs", "v", "versus", "and", "or", "the", "in",
    "at", "of", "with", "from", "to", "on", "about",
}


# --- 1. Soundex Phonetic Algorithm ---

def soundex(name: str) -> str:
    """
    Standard Soundex phonetic algorithm.
    Maps similar-sounding names to identical 4-character codes (e.g. Mhatre, Mahtre, Mhtre -> M360).
    """
    if not name:
        return ""
    name = re.sub(r"[^A-Za-z]", "", name.upper())
    if not name:
        return ""
    mapping = {
        "BFPV": "1",
        "CGJKQSXZ": "2",
        "DT": "3",
        "L": "4",
        "MN": "5",
        "R": "6",
    }
    encoded = name[0]
    last_code = ""
    for char in name[1:]:
        for key, code in mapping.items():
            if char in key:
                if code != last_code:
                    encoded += code
                    last_code = code
                break
        else:
            last_code = ""
    encoded = re.sub(r"[AEIOUYHW]", "", encoded[0] + encoded[1:])
    return (encoded[:4] + "0000")[:4]


# --- 2. Metaphone Phonetic Algorithm ---

def metaphone(name: str) -> str:
    """
    Lawrence Philips' Metaphone phonetic encoding.
    Handles consonant combinations, silent letters, and romanized phonetic variations.
    """
    if not name:
        return ""
    name = re.sub(r"[^A-Za-z]", "", name.upper())
    if not name:
        return ""

    if name.startswith(("KN", "GN", "PN", "AE", "WR")):
        name = name[1:]
    elif name.startswith("X"):
        name = "S" + name[1:]
    elif name.startswith("WH"):
        name = "W" + name[2:]

    metaph: List[str] = []
    length = len(name)
    i = 0
    while i < length:
        ch = name[i]
        if ch in "AEIOU":
            if i == 0:
                metaph.append(ch)
        elif ch == "B":
            if not (i == length - 1 and i > 0 and name[i - 1] == "M"):
                metaph.append("B")
        elif ch == "C":
            if i + 1 < length and name[i + 1] == "H":
                metaph.append("X")
                i += 1
            elif i + 1 < length and name[i + 1] in "EIY":
                metaph.append("S")
            else:
                metaph.append("K")
        elif ch == "D":
            if i + 2 < length and name[i + 1] == "G" and name[i + 2] in "EIY":
                metaph.append("J")
                i += 2
            else:
                metaph.append("T")
        elif ch in "FPV":
            if ch == "P" and i + 1 < length and name[i + 1] == "H":
                metaph.append("F")
                i += 1
            else:
                metaph.append("F")
        elif ch == "G":
            if i + 1 < length and name[i + 1] == "H":
                i += 1
            elif i + 1 < length and name[i + 1] in "EIY":
                metaph.append("J")
            else:
                metaph.append("K")
        elif ch == "H":
            if i == 0 or name[i - 1] in "AEIOU":
                if i + 1 < length and name[i + 1] in "AEIOU":
                    metaph.append("H")
        elif ch in "JKQXZ":
            if ch == "Q":
                metaph.append("K")
            elif ch == "X":
                metaph.append("KS")
            elif ch == "Z":
                metaph.append("S")
            else:
                metaph.append(ch)
        elif ch in "LMNR":
            metaph.append(ch)
        elif ch == "S":
            if i + 1 < length and name[i + 1] == "H":
                metaph.append("X")
                i += 1
            else:
                metaph.append("S")
        elif ch == "T":
            if i + 1 < length and name[i + 1] == "H":
                metaph.append("0")
                i += 1
            elif i + 2 < length and name[i + 1] == "I" and name[i + 2] in "AO":
                metaph.append("X")
                i += 2
            else:
                metaph.append("T")
        elif ch in "WY":
            if i + 1 < length and name[i + 1] in "AEIOU":
                metaph.append(ch)
        i += 1

    return "".join(metaph)


# --- 3. NYSIIS Phonetic Algorithm ---

def nysiis(name: str) -> str:
    """
    New York State Identification and Intelligence System (NYSIIS) phonetic algorithm.
    Optimized for surname resolution and spelling mutations.
    """
    if not name:
        return ""
    name = re.sub(r"[^A-Za-z]", "", name.upper())
    if not name:
        return ""

    if name.startswith("MAC"):
        name = "MCC" + name[3:]
    elif name.startswith("KN"):
        name = "NN" + name[2:]
    elif name.startswith("K"):
        name = "C" + name[1:]
    elif name.startswith(("PH", "PF")):
        name = "FF" + name[2:]
    elif name.startswith("SCH"):
        name = "SSS" + name[3:]

    if name.endswith(("EE", "IE")):
        name = name[:-2] + "Y"
    elif name.endswith(("DT", "RT", "RD", "NT", "ND")):
        name = name[:-2] + "D"

    key = [name[0]]
    i = 1
    while i < len(name):
        c = name[i]
        curr = ""
        if c == "E" and i + 1 < len(name) and name[i + 1] == "V":
            curr = "AF"
            i += 1
        elif c in "AEIOU":
            curr = "A"
        elif c == "Q":
            curr = "G"
        elif c == "Z":
            curr = "S"
        elif c == "M":
            curr = "N"
        elif c == "K":
            curr = "C"
        elif c == "S" and i + 2 < len(name) and name[i + 1 : i + 3] == "CH":
            curr = "S"
            i += 2
        elif c == "P" and i + 1 < len(name) and name[i + 1] == "H":
            curr = "F"
            i += 1
        elif c == "H" and (name[i - 1] not in "AEIOU" or (i + 1 < len(name) and name[i + 1] not in "AEIOU")):
            curr = name[i - 1]
        elif c == "W" and name[i - 1] in "AEIOU":
            curr = name[i - 1]
        else:
            curr = c

        if curr and curr[-1] != key[-1]:
            key.append(curr)
        i += 1

    res = "".join(key)
    if res.endswith("S") and len(res) > 1:
        res = res[:-1]
    if res.endswith("AY"):
        res = res[:-2] + "Y"
    if res.endswith("A") and len(res) > 1:
        res = res[:-1]
    return res


# --- 4. Jaro-Winkler String Similarity Metric ---

def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1) -> float:
    """
    Jaro-Winkler string distance metric with prefix bonus.
    Ideal for short entity tokens, names, and transliteration differences.
    """
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_dist = max(len1, len2) // 2 - 1
    if match_dist < 0:
        match_dist = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] == s2[j]:
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    transpositions //= 2
    jaro = (matches / len1 + matches / len2 + (matches - transpositions) / matches) / 3.0

    prefix_len = 0
    for i in range(min(len1, len2, 4)):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break

    return jaro + prefix_len * p * (1.0 - jaro)


def extract_clean_tokens(raw_val: Any, noise_tokens: Optional[Set[str]] = None) -> List[str]:
    """Recursively extract clean lowercased tokens from any data structure, stripping noise words."""
    noise = noise_tokens if noise_tokens is not None else DEFAULT_NOISE_TOKENS
    if isinstance(raw_val, dict):
        text = " ".join(str(v) for v in raw_val.values())
    elif isinstance(raw_val, (list, tuple, set)):
        text = " ".join(str(v) for v in raw_val)
    else:
        text = str(raw_val or "")
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return [w for w in text.split() if w not in noise and len(w) >= 3]


def flatten_metadata_fields(meta: Any, prefix: str = "") -> Dict[str, Any]:
    """
    Recursively flattens any arbitrary JSON metadata structure into a flat dict of field_name -> value.
    """
    flat: Dict[str, Any] = {}
    if isinstance(meta, dict):
        for k, v in meta.items():
            field_name = f"{prefix}.{k}" if prefix else k
            flat[field_name] = v
            if isinstance(v, dict):
                flat.update(flatten_metadata_fields(v, field_name))
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        flat.update(flatten_metadata_fields(item, f"{field_name}[{i}]"))
    return flat


def identify_field_type(key: str, value: Any, custom_hints: Optional[Dict[str, FieldType]] = None) -> FieldType:
    """
    Classifies a metadata field key and value into ENTITY, TEXT, or VALUE.
    """
    key_lower = key.lower()
    if custom_hints and key_lower in custom_hints:
        return custom_hints[key_lower]

    value_keywords = {
        "year", "date", "decision_date", "section", "sec", "cnr", "case_no",
        "court_code", "disposition", "status", "id", "amount", "price", "code", "sku"
    }
    if any(k in key_lower for k in value_keywords):
        return FieldType.VALUE
    if isinstance(value, (int, float)):
        return FieldType.VALUE
    if isinstance(value, str) and re.match(r"^\d{4}(-\d{2}-\d{2})?$", value.strip()):
        return FieldType.VALUE

    entity_keywords = {
        "judge", "coram", "bench", "petitioner", "respondent", "appellant",
        "advocate", "counsel", "party", "parties", "court", "author", "doctor",
        "patient", "vendor", "claimant", "beneficiary", "client", "plaintiff", "defendant"
    }
    if any(k in key_lower for k in entity_keywords):
        return FieldType.ENTITY

    if isinstance(value, str) and len(value.split()) >= 4:
        return FieldType.TEXT
    text_keywords = {"title", "summary", "holding", "facts", "description", "content", "notes", "narrative"}
    if any(k in key_lower for k in text_keywords):
        return FieldType.TEXT

    return FieldType.ENTITY


import structlog

logger = structlog.get_logger(__name__)


class TypedMetadataMatcher:
    """
    Modular Lexical, Phonetic, and String Similarity Matcher.
    Combines Soundex, Metaphone, NYSIIS, Jaro-Winkler, and SequenceMatcher with structured debug logs.
    """

    def __init__(
        self,
        noise_tokens: Optional[Set[str]] = None,
        custom_type_hints: Optional[Dict[str, FieldType]] = None,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.noise_tokens = noise_tokens or DEFAULT_NOISE_TOKENS
        self.custom_type_hints = custom_type_hints or {}
        self.weights = weights or {"entity": 0.45, "text": 0.30, "value": 0.40}

    def match_entity(self, query_val: Any, target_val: Any, field_name: str = "entity") -> Tuple[bool, float, str]:
        """
        Tiered Cascade Entity Matcher:
        1. Tier 1 (PRIMARY): Exact Token Overlap (Score: 100%)
        2. Tier 2 (HIGH-PRECISION STRING): Jaro-Winkler >= 0.88 (Score: 85%)
        3. Tier 3 (FUZZY STRING): SequenceMatcher >= 0.80 (Score: 75%)
        4. Tier 4 (FALLBACK ONLY): Phonetic Match [Metaphone -> Soundex -> NYSIIS] (Score: 60%)
        """
        q_tokens = extract_clean_tokens(query_val, self.noise_tokens)
        t_tokens = extract_clean_tokens(target_val, self.noise_tokens)
        if not q_tokens or not t_tokens:
            return False, 0.0, "no_tokens"

        base_weight = self.weights["entity"]

        # --- Tier 1: PRIMARY - Exact Token Match ---
        common = set(q_tokens) & set(t_tokens)
        if common:
            logger.debug(
                "matcher_entity_tier1_exact_match",
                field=field_name,
                matched_tokens=list(common),
                score=base_weight,
            )
            return True, base_weight, f"exact_token:{','.join(common)}"

        # --- Tier 2: String Distance - Jaro-Winkler (Prefix & Character Position) ---
        for qt in q_tokens:
            for tt in t_tokens:
                jw_score = jaro_winkler_similarity(qt, tt)
                if jw_score >= 0.88:
                    s = base_weight * 0.85
                    logger.debug(
                        "matcher_entity_tier2_jaro_winkler_match",
                        field=field_name,
                        query_token=qt,
                        doc_token=tt,
                        similarity=round(jw_score, 3),
                        score=s,
                    )
                    return True, s, f"jaro_winkler:{qt}~{tt}:{round(jw_score, 2)}"

        # --- Tier 3: String Distance - SequenceMatcher Fuzzy Ratio ---
        for qt in q_tokens:
            for tt in t_tokens:
                ratio = SequenceMatcher(None, qt, tt).ratio()
                if ratio >= 0.80:
                    s = base_weight * 0.75
                    logger.debug(
                        "matcher_entity_tier3_fuzzy_ratio_match",
                        field=field_name,
                        query_token=qt,
                        doc_token=tt,
                        ratio=round(ratio, 3),
                        score=s,
                    )
                    return True, s, f"fuzzy_ratio:{qt}~{tt}:{round(ratio, 2)}"

        # --- Tier 4: FALLBACK ONLY - Phonetic Matching (Metaphone -> Soundex -> NYSIIS) ---
        for qt in q_tokens:
            # 4a. Metaphone (Primary phonetic)
            q_mp = metaphone(qt)
            if q_mp:
                for tt in t_tokens:
                    t_mp = metaphone(tt)
                    if q_mp == t_mp:
                        s = base_weight * 0.60
                        logger.debug(
                            "matcher_entity_tier4_phonetic_fallback",
                            algorithm="metaphone",
                            field=field_name,
                            query_token=qt,
                            doc_token=tt,
                            metaphone_code=q_mp,
                            score=s,
                        )
                        return True, s, f"phonetic_fallback:metaphone:{qt}~{tt}"

            # 4b. Soundex (Secondary phonetic fallback)
            q_sx = soundex(qt)
            if q_sx:
                for tt in t_tokens:
                    t_sx = soundex(tt)
                    if q_sx == t_sx:
                        s = base_weight * 0.55
                        logger.debug(
                            "matcher_entity_tier4_phonetic_fallback",
                            algorithm="soundex",
                            field=field_name,
                            query_token=qt,
                            doc_token=tt,
                            soundex_code=q_sx,
                            score=s,
                        )
                        return True, s, f"phonetic_fallback:soundex:{qt}~{tt}"

            # 4c. NYSIIS (Tertiary phonetic fallback)
            q_ny = nysiis(qt)
            if q_ny:
                for tt in t_tokens:
                    t_ny = nysiis(tt)
                    if q_ny == t_ny:
                        s = base_weight * 0.50
                        logger.debug(
                            "matcher_entity_tier4_phonetic_fallback",
                            algorithm="nysiis",
                            field=field_name,
                            query_token=qt,
                            doc_token=tt,
                            nysiis_code=q_ny,
                            score=s,
                        )
                        return True, s, f"phonetic_fallback:nysiis:{qt}~{tt}"

        return False, 0.0, "no_match"

    def match_text(self, query_val: Any, target_val: Any, field_name: str = "text") -> Tuple[bool, float, str]:
        """Lexical token frequency and concept matching for narrative fields."""
        q_tokens = extract_clean_tokens(query_val, self.noise_tokens)
        t_tokens = extract_clean_tokens(target_val, self.noise_tokens)
        if not q_tokens or not t_tokens:
            return False, 0.0, "no_tokens"

        common = set(q_tokens) & set(t_tokens)
        if common:
            overlap_ratio = len(common) / max(len(q_tokens), 1)
            score = self.weights["text"] * min(overlap_ratio, 1.0)
            logger.debug(
                "matcher_text_lexical_overlap",
                field=field_name,
                common_tokens=list(common),
                overlap_ratio=round(overlap_ratio, 3),
                score=score,
            )
            return True, score, f"text_overlap:{','.join(common)}"

        return False, 0.0, "no_match"

    def match_value(self, filter_val: Any, target_val: Any, field_name: str = "value") -> Tuple[bool, float, str]:
        """Exact, alphanumeric normalized, or substring equality for discrete value fields."""
        if filter_val is None or target_val is None:
            return False, 0.0, "empty"

        f_str = re.sub(r"[^a-zA-Z0-9]", "", str(filter_val).lower())
        t_str = re.sub(r"[^a-zA-Z0-9]", "", str(target_val).lower())

        if not f_str or not t_str:
            return False, 0.0, "empty"

        if f_str == t_str or f_str in t_str or t_str in f_str:
            score = self.weights["value"]
            logger.debug(
                "matcher_value_exact_match",
                field=field_name,
                filter_val=filter_val,
                target_val=target_val,
                normalized=f_str,
                score=score,
            )
            return True, score, f"value_match:{filter_val}"

        return False, 0.0, "no_match"

    def match_document(
        self,
        query: str,
        metadata: Dict[str, Any],
        filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, List[str]]:
        """
        Evaluates a document against query and filters using typed field strategies.
        Returns:
            (total_doc_score: float, matched_tags: List[str])
        """
        flat_meta = flatten_metadata_fields(metadata)
        total_score = 0.0
        matched_tags: List[str] = []

        # 1. Evaluate Explicit / Extracted Filters
        if filters:
            for filter_key, filter_val in filters.items():
                if not filter_val:
                    continue
                f_key_low = filter_key.lower()
                for meta_key, meta_val in flat_meta.items():
                    m_key_low = meta_key.lower()
                    if f_key_low in m_key_low or m_key_low in f_key_low:
                        ftype = identify_field_type(meta_key, meta_val, self.custom_type_hints)
                        if ftype == FieldType.ENTITY:
                            is_m, s, reason = self.match_entity(filter_val, meta_val, field_name=meta_key)
                        elif ftype == FieldType.VALUE:
                            is_m, s, reason = self.match_value(filter_val, meta_val, field_name=meta_key)
                        else:
                            is_m, s, reason = self.match_text(filter_val, meta_val, field_name=meta_key)

                        if is_m:
                            total_score += s
                            matched_tags.append(f"{meta_key}:{reason}")
                            break

        # 2. Evaluate Query against all metadata fields using their respective FieldType
        clean_q = extract_clean_tokens(query, self.noise_tokens)
        if clean_q:
            for meta_key, meta_val in flat_meta.items():
                if not meta_val:
                    continue
                ftype = identify_field_type(meta_key, meta_val, self.custom_type_hints)
                if ftype == FieldType.ENTITY:
                    is_m, s, reason = self.match_entity(query, meta_val, field_name=meta_key)
                elif ftype == FieldType.TEXT:
                    is_m, s, reason = self.match_text(query, meta_val, field_name=meta_key)
                else:
                    is_m, s, reason = self.match_value(query, meta_val, field_name=meta_key)

                if is_m:
                    tag_str = f"{meta_key}:{reason}"
                    if tag_str not in matched_tags:
                        total_score += min(s * 0.85, 0.45)
                        matched_tags.append(tag_str)

        return total_score, matched_tags
