from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import re
from typing import Any, Iterable


_TERMINAL = (".", ":", ";", ",", "?", "!", ")", "]", "}")


def _collapse_pdf_repetition(text: str) -> str:
    """Remove obvious PDF text-layer duplication without changing normal prose.

    Only collapse repeated *whole phrases* that are duplicated contiguously.
    We deliberately do not collapse ordinary repeated words such as
    "very very" or legally meaningful repetition.
    """
    text = text.strip()
    if not text:
        return ""

    words = text.split()
    n = len(words)

    # Detect exact repeated phrase covering most/all of a block.
    # Examples: "IN IN IN THE..." are handled as repeated one-token noise;
    # "REPORT REPORT REPORT" is also handled below.
    if n >= 2:
        for unit_len in range(1, min(12, n // 2) + 1):
            if n % unit_len:
                continue
            repetitions = n // unit_len
            if repetitions < 2:
                continue
            units = [w.casefold() for w in words[:unit_len]]
            if all(
                [w.casefold() for w in words[i * unit_len:(i + 1) * unit_len]] == units
                for i in range(repetitions)
            ):
                # Only collapse if the repetition is strong enough to be
                # clearly a PDF extraction artifact.
                if repetitions >= 3 or unit_len >= 2:
                    return " ".join(words[:unit_len])

    # Collapse repeated single tokens only when the same token occurs 3+
    # times consecutively. This avoids changing legitimate "very very".
    cleaned: list[str] = []
    i = 0
    while i < len(words):
        j = i + 1
        while j < n and words[j].casefold() == words[i].casefold():
            j += 1
        run = j - i
        cleaned.append(words[i])
        if run >= 3:
            i = j
        else:
            i += 1

    return " ".join(cleaned)


def normalize_text(text: str) -> str:
    """Normalize PDF layout noise while preserving substantive wording."""
    text = str(text or "").replace("\u00ad", "")
    text = re.sub(r"-\s*\n\s*(?=[a-z])", "", text, flags=re.I)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = _collapse_pdf_repetition(text)
    return text.strip()


def _is_noise_block(text: str) -> bool:
    """Reject obvious PDF artifacts before paragraph numbering."""
    text = normalize_text(text)
    if not text:
        return True

    # Standalone page-number / footer artifacts such as ':1:', '1', '[1]'.
    if re.fullmatch(r"[\s:;,\-–—.\[\](){}]*\d+[\s:;,\-–—.\[\](){}]*", text):
        return True

    # Punctuation-only or one-character artifacts.
    if not re.search(r"[A-Za-z0-9]", text):
        return True
    if len(re.sub(r"[^A-Za-z0-9]", "", text)) <= 1:
        return True

    return False


@dataclass(frozen=True)
class SourceSpan:
    """Authoritative semantic evidence unit: document -> page -> paragraph."""
    span_id: str
    document_id: int
    page: int
    paragraph: int
    span_type: str
    text: str
    text_hash: str
    ordinal: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_boundary(
    previous: dict[str, Any],
    current: dict[str, Any],
    median_height: float,
) -> bool:
    pb = previous.get("bbox") or [0, 0, 0, 0]
    cb = current.get("bbox") or [0, 0, 0, 0]
    vertical_gap = float(cb[1]) - float(pb[3])
    indent_change = abs(float(cb[0]) - float(pb[0]))

    txt = normalize_text(str(current.get("text", "")))
    starts_like_list = bool(re.match(r"^(?:\(?\d+[.)]|[-•*])\s+", txt))

    starts_like_heading = (
        len(txt) < 120
        and not txt.endswith(_TERMINAL)
        and vertical_gap > max(6.0, median_height * 1.2)
    )

    # If the preceding block is a complete sentence and the next block
    # starts a new sentence, prefer separate logical paragraphs. This is
    # deliberately conservative: wrapped lines normally don't end in
    # terminal punctuation.
    prev_txt = normalize_text(str(previous.get("text", "")))
    sentence_boundary = (
        bool(prev_txt)
        and prev_txt.endswith((".", "?", "!"))
        and bool(re.match(r"^[A-Z(]", txt))
        and vertical_gap > max(2.0, median_height * 0.35)
    )

    return (
        vertical_gap > max(8.0, median_height * 1.65)
        or indent_change > max(18.0, median_height * 2.0)
        or starts_like_list
        or starts_like_heading
        or sentence_boundary
    )


def build_paragraph_spans(
    *,
    document_id: int,
    page: int,
    blocks: Iterable[dict[str, Any]],
) -> list[SourceSpan]:
    """Build deterministic page/paragraph evidence spans.

    PDF regions remain an extraction/layout concern only. They are not part
    of the semantic evidence contract.
    """
    usable: list[dict[str, Any]] = []
    for block in blocks:
        text = normalize_text(str(block.get("text", "")))
        if _is_noise_block(text):
            continue
        copy = dict(block)
        copy["text"] = text
        usable.append(copy)

    usable.sort(
        key=lambda b: (
            float((b.get("bbox") or [0, 0, 0, 0])[1]),
            float((b.get("bbox") or [0, 0, 0, 0])[0]),
        )
    )
    if not usable:
        return []

    heights = [
        float(b["bbox"][3]) - float(b["bbox"][1])
        for b in usable if b.get("bbox")
    ]
    median_height = sorted(heights)[len(heights) // 2] if heights else 10.0

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for block in usable:
        if not current:
            current = [block]
            continue

        if _is_boundary(current[-1], block, median_height):
            groups.append(current)
            current = [block]
        else:
            current.append(block)

    if current:
        groups.append(current)

    spans: list[SourceSpan] = []
    for ordinal, group in enumerate(groups, start=1):
        text = normalize_text(" ".join(str(b["text"]) for b in group))
        if not text:
            continue

        span_id = f"doc{document_id}-p{page:04d}-para{ordinal:04d}"
        spans.append(
            SourceSpan(
                span_id=span_id,
                document_id=document_id,
                page=page,
                paragraph=ordinal,
                span_type="paragraph",
                text=text,
                text_hash=sha256(text.encode("utf-8")).hexdigest(),
                ordinal=ordinal,
            )
        )

    return spans
