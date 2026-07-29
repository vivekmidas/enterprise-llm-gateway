from __future__ import annotations

from dataclasses import dataclass

from .source_spans import SourceSpan


@dataclass
class DomainChunk:
    chunk_id: str
    text: str
    page_start: int | None
    page_end: int | None
    section: str | None
    metadata: dict


class LegalChunker:
    """Structural chunks that retain source-span provenance."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 200):
        self.chunk_size = max(chunk_size, 200)
        self.overlap = max(0, min(overlap, self.chunk_size // 2))

    def chunk(self, full_text: str, source_spans: list[SourceSpan] | None = None) -> list[dict]:
        if not full_text.strip():
            return []

        if source_spans:
            blocks = [s.text for s in source_spans if s.text.strip()]
            span_ids = [s.span_id for s in source_spans if s.text.strip()]
        else:
            blocks = [b.strip() for b in full_text.split("\n\n") if b.strip()]
            span_ids = [None] * len(blocks)

        chunks: list[dict] = []
        current_text = ""
        current_span_ids: list[str] = []

        def emit(text: str, ids: list[str]):
            if not text.strip():
                return
            chunks.append({
                "text": text.strip(),
                "section": None,
                "metadata": {
                    "chunking": "paragraph_structural_v1_1_4",
                    "source_span_ids": list(dict.fromkeys(i for i in ids if i)),
                },
            })

        for block, sid in zip(blocks, span_ids):
            candidate = f"{current_text}\n\n{block}".strip() if current_text else block
            if len(candidate) <= self.chunk_size:
                current_text = candidate
                if sid:
                    current_span_ids.append(sid)
                continue

            if current_text:
                emit(current_text, current_span_ids)

            tail = current_text[-self.overlap:] if self.overlap and current_text else ""
            current_text = f"{tail}\n\n{block}".strip()
            current_span_ids = [sid] if sid else []

            while len(current_text) > self.chunk_size:
                emit(current_text[:self.chunk_size], current_span_ids)
                current_text = current_text[self.chunk_size - self.overlap:] if self.overlap else current_text[self.chunk_size:]
                # A split inside a paragraph is no longer a clean one-to-one
                # source unit, but the originating span remains attached.

        if current_text:
            emit(current_text, current_span_ids)

        for i, item in enumerate(chunks):
            item["chunk_id"] = f"legal-{i+1:05d}"
        return chunks
