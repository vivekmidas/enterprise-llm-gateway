from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

@dataclass
class SourceRef:
    page: int
    paragraph: Optional[int] = None
    span_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

def build_source_map(paragraphs: list[dict]) -> dict[str, SourceRef]:
    result = {}
    for p in paragraphs:
        span_id = p.get("span_id") or p.get("id")
        if not span_id:
            continue
        result[span_id] = SourceRef(
            page=int(p["page"]),
            paragraph=p.get("paragraph"),
            span_id=span_id,
        )
    return result
