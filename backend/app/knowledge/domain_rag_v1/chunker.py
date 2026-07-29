from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DomainChunk:
    chunk_id: str
    text: str
    page_start: int | None
    page_end: int | None
    section: str | None
    metadata: dict


class LegalChunker:
    """Structural chunking for the first V1; semantic chunking can be added later."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 200):
        self.chunk_size = max(chunk_size, 200)
        self.overlap = max(0, min(overlap, self.chunk_size // 2))

    def chunk(self, full_text: str) -> list[dict]:
        if not full_text.strip():
            return []

        blocks = [b.strip() for b in full_text.split("\n\n") if b.strip()]
        chunks: list[dict] = []
        current = ""

        for block in blocks:
            candidate = f"{current}\n\n{block}".strip() if current else block
            if len(candidate) <= self.chunk_size:
                current = candidate
                continue

            if current:
                chunks.append({
                    "text": current,
                    "section": None,
                    "metadata": {"chunking": "structural_v1"},
                })

            tail = current[-self.overlap:] if self.overlap and current else ""
            current = f"{tail}\n\n{block}".strip()

            while len(current) > self.chunk_size:
                chunks.append({
                    "text": current[:self.chunk_size],
                    "section": None,
                    "metadata": {"chunking": "structural_v1"},
                })
                current = current[self.chunk_size - self.overlap:] if self.overlap else current[self.chunk_size:]

        if current:
            chunks.append({
                "text": current,
                "section": None,
                "metadata": {"chunking": "structural_v1"},
            })

        for i, item in enumerate(chunks):
            item["chunk_id"] = f"legal-{i+1:05d}"
        return chunks
