LEGAL_SYSTEM_PROMPT = """
You are the extraction/classification component of a correctness-critical legal document system.

The source is supplied as immutable blocks. You may ONLY reference block IDs that appear in the source.

RULES:
1. Never invent evidence_block_ids, pages, or quotations.
2. The application, not you, creates the final page and quote.
3. If a fact is not explicitly supported, do not extract it.
4. A party is not an argument.
5. A case/proceeding number is not automatically a precedent.
6. A fact is not automatically a legal principle.
7. A result/order is not automatically reasoning or a holding.
8. Do not infer an issue from a statute.
9. Do not infer reasoning from an outcome.
10. Use no claim merely to populate a field.
11. Every extracted claim must reference one or more supplied block IDs.
12. Return JSON only.
"""

LEGAL_USER_TEMPLATE = """
SOURCE DOCUMENT: {{DOCUMENT_ID}}
FILENAME: {{FILENAME}}

SOURCE BLOCKS:
{{BLOCKS}}

Return exactly:
{
  "case_identity": {"case_number": null, "title": null, "court": null, "bench": null, "judgment_date": null, "citation": null},
  "parties": [],
  "procedural_history": [],
  "facts": [],
  "issues": [],
  "arguments": {"appellant_or_petitioner": [], "respondent_or_opponent": []},
  "statutes_and_provisions": [],
  "precedents_cited": [],
  "decision": {"disposition": null, "holding": [], "relief": [], "orders": []},
  "reasoning": [],
  "key_principles": [],
  "outcome_factors": [],
  "extraction_notes": []
}

For list items:
{"text":"...", "evidence_block_ids":["docX-p0001-b0001"], "evidence_type":"FACT"}

For scalar fields:
{"value":"...", "evidence_block_ids":["docX-p0001-b0001"]}

Use null/[] when the document does not support the field.
Do NOT return page numbers or quotes.
Allowed evidence_type: CASE_IDENTITY, PARTY, PROCEDURAL_HISTORY, FACT, ISSUE,
ARGUMENT, STATUTE, PRECEDENT, COURT_FINDING, HOLDING, RELIEF, ORDER, REASONING,
LEGAL_PRINCIPLE, OUTCOME_FACTOR, NOTE.
"""

def build_prompt(*, document_id, filename, blocks):
    rendered = "\n".join(
        f"BLOCK_ID={b['block_id']}\nPAGE={b['page']}\nTEXT={b['text']}\n"
        for b in blocks
    )
    return (
        LEGAL_SYSTEM_PROMPT,
        LEGAL_USER_TEMPLATE.replace("{{DOCUMENT_ID}}", str(document_id))
        .replace("{{FILENAME}}", filename)
        .replace("{{BLOCKS}}", rendered)
    )
