class EvidenceLinkedChunker:
    def __init__(self, chunk_size=1000, overlap=200):
        self.chunk_size = max(200, chunk_size)
        self.overlap = max(0, min(overlap, self.chunk_size // 2))

    def chunk(self, source_document):
        chunks = []
        for page_no, text in source_document.pages.items():
            text = text.strip()
            if not text:
                continue
            block_ids = [b.block_id for b in source_document.blocks if b.page == page_no]
            start, ordinal = 0, 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                piece = text[start:end].strip()
                if piece:
                    ordinal += 1
                    chunks.append({
                        "chunk_id": f"p{page_no:04d}-{ordinal:03d}",
                        "text": piece,
                        "page_start": page_no,
                        "page_end": page_no,
                        "source_block_ids": block_ids,
                        "metadata": {"chunking": "evidence_linked_page_preserving_v1_1_1", "source_page": page_no},
                    })
                if end >= len(text):
                    break
                start = max(end - self.overlap, start + 1)
        return chunks
