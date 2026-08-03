# DOMAIN_RAG_V1_3

This is the simplified domain extraction architecture.

## Design

PDF/OCR ingestion remains common and produces page/paragraph source records.

Domain extraction then asks the LLM to identify only important domain fields.

Each populated field carries:

- `value`
- `confidence` (0..1)
- `basis`: `FACT`, `INFERENCE`, or `UNKNOWN`
- `source_span_ids`
- resolved `source`: page + paragraph
- `review_required`

There is deliberately no mandatory evidence candidate pipeline, lexical evidence
matching, exact evidence matching, or `NEEDS_REVIEW` for every field.

## Review

`review_threshold=0.80` is configurable.

A field below the threshold is flagged. The whole document is marked
`review_required` when the minimum populated-field confidence is below the
threshold.

The human can review/correct the entire case regardless of confidence.

## Source

The implementation uses the existing `app/knowledge/domain_rag_v1` package
rather than creating a `domain_rag_v1_3` directory.

## Expected paragraph input

```python
[
    {
        "span_id": "doc16-p0001-para0004",
        "page": 1,
        "paragraph": 4,
        "text": "CORAM : DR. D.Y. CHANDRACHUD,J. 22ND DECEMBER, 2006."
    }
]
```

## Intentionally removed from V1_3

- evidence candidate generation
- exact/lexical support scoring
- mandatory evidence records
- fixed confidence=0.5
- canonical `procedural_history` dumping of arbitrary source paragraphs
- geometry/region as a required provenance mechanism
- text hash as a required extraction mechanism

Page and paragraph remain the primary provenance.

## curl for uploading documents for parsing 
curl -X POST "http://localhost:8000/api/v3/knowledge/documents" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-01",
    "knowledge_base_id": "kb-legal-v1",
    "filename": "sample_contract.pdf",
    "file_path": "/absolute/path/to/sample_contract.pdf",
    "mime_type": "application/pdf",
    "domain_id": "legal"
  }'

`{
  "document_id": "doc-a1b2c3d4e5f6",
  "tenant_id": "tenant-01",
  "knowledge_base_id": "kb-legal-v1",
  "filename": "sample_contract.pdf",
  "processing_stage": "UPLOADED",
  "approval_status": "PENDING",
  "current_stage_order": 1,
  "created_at": "2026-07-30T17:59:00Z"
}`
