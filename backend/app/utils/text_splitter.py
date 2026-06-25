import re
from typing import List

class RecursiveCharacterTextSplitter:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200, separators: List[str] = None):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []
        return self._split_text(text, self.separators)

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]

        if not separators:
            # Force hard character split as fallback
            step = max(1, self.chunk_size - self.chunk_overlap)
            return [text[i:i + self.chunk_size] for i in range(0, len(text), step)]

        separator = separators[0]
        next_separators = separators[1:]

        # Split text by current separator, preserving it using capture groups
        if separator == "":
            splits = list(text)
        else:
            escaped_sep = re.escape(separator)
            raw_splits = re.split(f"({escaped_sep})", text)
            splits = []
            # Merge separator tokens back to follow content
            for i in range(0, len(raw_splits), 2):
                part = raw_splits[i]
                if i + 1 < len(raw_splits):
                    part += raw_splits[i + 1]
                if part:
                    splits.append(part)

        chunks = []
        current_chunk = ""

        for split in splits:
            if len(split) > self.chunk_size:
                # If current part itself exceeds chunk size, split it with next separator recursively
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                sub_chunks = self._split_text(split, next_separators)
                if sub_chunks:
                    chunks.extend(sub_chunks[:-1])
                    current_chunk = sub_chunks[-1]
            elif len(current_chunk) + len(split) <= self.chunk_size:
                current_chunk += split
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # Overlap logic: take the overlap text from end of previous chunk
                overlap_start = max(0, len(current_chunk) - self.chunk_overlap)
                current_chunk = current_chunk[overlap_start:] + split
                # Safe-check if overlap + split exceeds limit
                if len(current_chunk) > self.chunk_size:
                    chunks.append(current_chunk)
                    current_chunk = ""

        if current_chunk:
            chunks.append(current_chunk)

        return [c.strip() for c in chunks if c.strip()]
