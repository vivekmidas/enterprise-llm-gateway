"""
# ==============================================================================
# LEGAL DOMAIN SINGLE SOURCE OF TRUTH (SOT)
# ==============================================================================
# This module defines the canonical Single Source of Truth for the Legal Domain.
# It powers database recovery/seeding (seed_data.py) and execution pipelines
# (domain_extractor.py, domain_rag_v1).
# ==============================================================================
"""

from __future__ import annotations
from typing import Any

# ==============================================================================
# 1. DOMAIN METADATA & SECTIONS
# ==============================================================================
LEGAL_DOMAIN_KEY = "legal_judgment"
LEGAL_DOMAIN_NAME = "Legal Judgments & Court Orders"
LEGAL_DOMAIN_VERSION = "1.0"
LEGAL_DOMAIN_DESCRIPTION = (
    "Exhaustive legal judgment document domain schema for courts, advocates, findings, and arguments."
)

LEGAL_SECTIONS = [
    "executive_case_summary",
    "document",
    "parties",
    "procedural_history",
    "facts",
    "legal_provisions",
    "issues",
    "labour_court_findings",
    "industrial_court",
    "high_court_arguments",
    "evidence",
    "legal_concepts",
    "research_topics",
    "keywords",
    "citations",
    "judgment_status",
    "knowledge_graph_entities",
    "embedding_metadata",
]

# ==============================================================================
# 2. FIELD SPECIFICATIONS (For Database Seeding & Metadata Tracking)
# ==============================================================================
LEGAL_FIELDS_SPEC = [
    {
        "key": "executive_case_summary",
        "label": "Executive Case Summary",
        "type": "object",
        "weight": 3.0,
        "importance": "critical",
        "required": False,
        "description": "Single line summary, case overview describing dispute, favoured party, and key sections involved",
    },
    {
        "key": "document",
        "label": "Document Metadata",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Title, court, jurisdiction, case number, citation, decision date, coram, judgment type",
    },
    {
        "key": "parties",
        "label": "Parties & Advocates",
        "type": "object",
        "weight": 2.5,
        "importance": "high",
        "required": False,
        "description": "Petitioner, respondent, prosecutor, defendant, and advocates for each side",
    },
    {
        "key": "procedural_history",
        "label": "Procedural History",
        "type": "array",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Chronological history of dates and events leading up to current appeal/petition",
    },
    {
        "key": "facts",
        "label": "Factual Background",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Employment details, incident date & allegations, and disciplinary action history",
    },
    {
        "key": "legal_provisions",
        "label": "Legal Provisions",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Statutes, acts, sections, and schedule items cited in judgment",
    },
    {
        "key": "issues",
        "label": "Legal Issues",
        "type": "array",
        "weight": 2.5,
        "importance": "critical",
        "required": False,
        "description": "Key legal questions and issues framed by the court",
    },
    {
        "key": "labour_court_findings",
        "label": "Labour Court Findings",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Enquiry fairness, natural justice, misconduct, and relief granted",
    },
    {
        "key": "industrial_court",
        "label": "Industrial Court Findings",
        "type": "object",
        "weight": 2.0,
        "importance": "medium",
        "required": False,
        "description": "Revision application details and revision order",
    },
    {
        "key": "high_court_arguments",
        "label": "High Court Arguments",
        "type": "object",
        "weight": 2.5,
        "importance": "high",
        "required": False,
        "description": "Submissions and arguments of petitioner, respondent, prosecutor, and defense",
    },
    {
        "key": "evidence",
        "label": "Evidence & Witnesses",
        "type": "object",
        "weight": 1.5,
        "importance": "medium",
        "required": False,
        "description": "Documentary evidence, inspection reports, and witness statements",
    },
    {
        "key": "legal_concepts",
        "label": "Legal Concepts",
        "type": "array",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Core legal concepts (e.g. Natural Justice, Perversity, Unfair Labour Practice)",
    },
    {
        "key": "research_topics",
        "label": "Research Topics",
        "type": "array",
        "weight": 1.5,
        "importance": "medium",
        "required": False,
        "description": "Categorized practice areas and legal research topics",
    },
    {
        "key": "keywords",
        "label": "Search Keywords",
        "type": "array",
        "weight": 1.0,
        "importance": "low",
        "required": False,
        "description": "Searchable keywords extracted from document text",
    },
    {
        "key": "citations",
        "label": "Citations & Precedents",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Cases and statutes referred to in the judgment",
    },
    {
        "key": "judgment_status",
        "label": "Judgment Status & Holding",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Portion available, final decision, ratio decidendi, obiter dicta",
    },
    {
        "key": "knowledge_graph_entities",
        "label": "Knowledge Graph Entities",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Extracted persons, organizations, and key dates",
    },
    {
        "key": "embedding_metadata",
        "label": "Embedding Metadata",
        "type": "object",
        "weight": 1.0,
        "importance": "low",
        "required": False,
        "description": "Domain, practice areas, extraction confidence score",
    },
]

# Map of legal field descriptions (for extraction runtime validation)
LEGAL_FIELDS = {
    "executive_case_summary": {
        "one_line_summary": "Single sentence executive summary of the case",
        "case_overview": "Comprehensive case overview describing dispute, main parties (AAA v. BBB), key statutory provisions (IPC/BNS/CrPC/BNSS), outcome, and favoured party",
        "favoured_party": "Name and role of party in whose favour the ruling was decided",
        "key_sections_involved": "List of key statutory sections involved in the case (e.g. IPC 302 / BNS 103)",
    },
    "case_identity": {
        "court": "Court or tribunal name",
        "location": "Court location / jurisdiction if explicitly available",
        "case_number": "Primary case number",
        "report_number": "Report / reference number if present",
        "case_date": "Date of the judgment/order/case document",
        "judge": "Judge, justice, bench or coram",
    },
    "parties": {
        "petitioners": "Petitioner(s), applicant(s), claimant(s) or equivalent",
        "respondents": "Respondent(s), opponent(s), defendant(s) or equivalent",
        "appellants": "Appellant(s), if applicable",
        "prosecutor": "Prosecutor(s), State, Public Prosecutor or equivalent",
        "defendants": "Defendant(s), accused, defense or equivalent",
        "other_parties": "Other materially identified parties and their roles (intervenors, amicus curiae)",
    },
    "substance": {
        "timeline_and_key_dates": "Key timeline events, dates, FIR dates, arrest dates, or lower court milestone dates",
        "procedural_history": "Lower court orders, FIRs, chargesheets, or procedural timeline",
        "charges_or_claims": "Specific offences, sections, or claims alleged",
        "evidence_and_witnesses": "Witness testimonies (PW/DW) and physical or documentary evidence",
        "issues": "Material legal issues expressly raised or decided",
        "facts": "Material facts stated in the document",
        "arguments": "Material arguments/positions expressly attributed to a party (prosecutor, defendant, appellant, respondent, other parties)",
        "statutes": "Statutes, regulations and provisions expressly cited",
        "statutory_interpretations": "Specific interpretations or constructions of statutory sections/articles",
        "precedents": "Cases/authorities expressly cited",
        "additional_observations": "Additional judicial remarks, obiter dicta, or context notes",
    },
    "decision": {
        "disposition": "Outcome/order/disposition expressly stated",
        "holding": "Holding or legal conclusion, if stated",
        "sentence_or_penalty": "Sentence, duration of imprisonment, fine, or penalty imposed",
        "relief": "Relief granted/refused/ordered, if stated",
    },
}

# ==============================================================================
# 3. EXTRACTION JSON SCHEMA (Strict JSON Schema for JsonLLM validation)
# ==============================================================================
LEGAL_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["case_identity", "parties", "substance", "decision"],
    "properties": {
        "executive_case_summary": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "one_line_summary": {"type": ["string", "null"]},
                "case_overview": {"type": ["string", "null"]},
                "favoured_party": {"type": ["string", "null"]},
                "key_sections_involved": {"type": "array"},
            },
        },
        "case_identity": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "court": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"]},
                "case_number": {"type": ["string", "null"]},
                "report_number": {"type": ["string", "null"]},
                "case_date": {"type": ["string", "null"]},
                "judge": {"type": ["string", "null"]},
            },
        },
        "parties": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "petitioners": {"type": "array"},
                "respondents": {"type": "array"},
                "appellants": {"type": "array"},
                "prosecutor": {"type": "array"},
                "defendants": {"type": "array"},
                "other_parties": {"type": "array"},
            },
        },
        "substance": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "timeline_and_key_dates": {"type": "array"},
                "procedural_history": {"type": "array"},
                "charges_or_claims": {"type": "array"},
                "evidence_and_witnesses": {"type": "array"},
                "issues": {"type": "array"},
                "facts": {"type": "array"},
                "arguments": {"type": ["array", "object"]},
                "statutes": {"type": "array"},
                "statutory_interpretations": {"type": "array"},
                "precedents": {"type": "array"},
                "additional_observations": {"type": "array"},
            },
        },
        "decision": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "disposition": {"type": ["string", "null"]},
                "holding": {"type": ["string", "null"]},
                "sentence_or_penalty": {"type": ["string", "null"]},
                "relief": {"type": ["string", "null"]},
            },
        },
    },
}

# ==============================================================================
# 4. EXECUTION PROMPTS (Free Extract & Evidence RAG)
# ==============================================================================

LEGAL_SYSTEM_PROMPT = (
    "You are a specialized legal document analyst.\n"
    "RULE 1: Extract ONLY factual information explicitly present in the document.\n"
    "RULE 2: Omit any field not found — do NOT write null, empty strings, or 0.\n"
    "RULE 3: NEVER write bracketed placeholders like '[Name]', '[Judge]', '[Advocate]', or '[Title]'. Extract exact real proper names or omit.\n"
    "RULE 4: For party names, extract actual names of people, government bodies, or companies, NOT generic roles.\n"
    "RULE 5: Capture specific arguments made by the Prosecutor/Prosecution/State, Defendant/Accused/Defense counsel, Petitioner/Appellant, Respondent, and Other Parties (Intervenors/Amicus Curiae).\n"
    "RULE 6: Use exact wording from the document for all values.\n"
    "RULE 7: DO NOT MISS ANY HELPFUL INFORMATION. Capture all timeline events, evidence, lower court details, judicial observations, statutory interpretations, and additional data points present in the text.\n"
    "Return a single valid JSON object only."
)

LEGAL_USER_PROMPT_TEMPLATE = (
    "Document Filename: {filename}\n\n"
    "Document Content:\n{content_snippet}\n\n"
    "Extract a comprehensive structured JSON from the above legal document.\n"
    "CRITICAL INSTRUCTIONS:\n"
    "- Omit any field not found in the document.\n"
    "- NEVER output bracketed placeholders like '[Name]', '[Advocate]', '[Judge]', or '[Date]'.\n"
    "- For parties, extract exact names of entities/people (e.g., 'State of Maharashtra', 'John Doe'), not just role labels.\n"
    "- 'arguments' MUST map specific arguments to the party making them:\n"
    "  - 'prosecutor': arguments by Prosecution, State, Public Prosecutor, or Complainant.\n"
    "  - 'defendant': arguments by Defendant, Accused, or Defense Counsel.\n"
    "  - 'appellant': arguments by Appellant or Petitioner.\n"
    "  - 'respondent': arguments by Respondent.\n"
    "  - 'other_parties': arguments by Intervenors, Amicus Curiae, Co-accused, or 3rd Parties.\n"
    "- DO NOT MISS ANY HELPFUL INFORMATION. Include all key dates, facts, evidence items, statutory interpretations, and observations.\n"
    "- 'legal_principles' must be legal propositions EXPLICITLY STATED or CONFIRMED by the court in this document only — not inferred.\n"
    "- 'number_of_connected_cases' must be an integer (number), not a string.\n\n"
    "Structure (omit any section not present):\n"
    "{\n"
    '  "executive_case_summary": {\n'
    '    "one_line_summary": "High-level single line summary (e.g. Case of AAA v. BBB regarding XYZ decided in favour of AAA under Section 302 IPC / Section 103 BNS)",\n'
    '    "case_overview": "Natural language narrative describing dispute, main parties (AAA v. BBB), core subject matter, key statutory sections (IPC/BNS/CrPC/BNSS/Acts), final outcome, and favoured party",\n'
    '    "favoured_party": "Name and role of party in whose favour the ruling was decided",\n'
    '    "key_sections_involved": ["IPC 302 / BNS 103", "..."]\n'
    '  },\n'
    '  "document": {"title": "...", "document_type": "...", "court": "...", "jurisdiction": "...", "case_number": "...", "citation": "...", "decision_date": "...", "coram": ["..."], "judgment_type": "..."},\n'
    '  "parties": {\n'
    '    "petitioner": {"name": "...", "type": "..."}, "respondent": {"name": "...", "type": "..."},\n'
    '    "prosecutor": {"name": "...", "type": "..."}, "defendant": {"name": "...", "type": "..."},\n'
    '    "advocates": {"petitioner": ["..."], "respondent": ["..."], "prosecutor": ["..."], "defense": ["..."]}\n'
    '  },\n'
    '  "procedural_history": [{"date": "...", "event": "..."}],\n'
    '  "facts": {\n'
    '    "summary": "...",\n'
    '    "employment": {"designation": "...", "employer": "..."},\n'
    '    "incident": {"inspection_date": "...", "allegation": "..."},\n'
    '    "disciplinary_action": {"charge_sheet_issued": true, "departmental_enquiry": true, "dismissal_date": "..."}\n'
    '  },\n'
    '  "legal_provisions": {"statutes": [{"name": "...", "abbreviation": "..."}], "sections": [], "schedule_items": ["..."]},\n'
    '  "issues": [{"id": 1, "issue": "..."}],\n'
    '  "labour_court_findings": {"enquiry": {}, "natural_justice": {}, "misconduct": {}, "relief": {}},\n'
    '  "industrial_court": {"revision_application": "...", "decision": "..."},\n'
    '  "high_court_arguments": {\n'
    '    "petitioner": ["..."],\n'
    '    "respondent": ["..."],\n'
    '    "prosecutor": ["..."],\n'
    '    "defendant": ["..."]\n'
    '  },\n'
    '  "arguments": {\n'
    '    "prosecutor": ["..."],\n'
    '    "defendant": ["..."],\n'
    '    "petitioner": ["..."],\n'
    '    "respondent": ["..."]\n'
    '  },\n'
    '  "evidence": {"documentary": ["..."], "inspection": ["..."]},\n'
    '  "legal_concepts": ["..."],\n'
    '  "research_topics": ["..."],\n'
    '  "keywords": ["..."],\n'
    '  "citations": {"cases_referred": [], "statutes_referred": ["..."]},\n'
    '  "judgment_status": {"portion_available": "...", "final_decision": "...", "ratio_decidendi": "... "},\n'
    '  "knowledge_graph_entities": {"persons": ["..."], "organizations": ["..."], "dates": ["..."]},\n'
    '  "embedding_metadata": {"document_domain": "...", "practice_area": ["..."], "confidence": 0.95}\n'
    "}\n"
    "Output ONLY the JSON. Omit fields not present in the document."
)

# Evidence RAG Prompts (for Block-level provenance in Domain RAG V1)
LEGAL_RAG_SYSTEM_PROMPT = """
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

LEGAL_RAG_USER_TEMPLATE = """
SOURCE DOCUMENT: {{DOCUMENT_ID}}
FILENAME: {{FILENAME}}

SOURCE BLOCKS:
{{BLOCKS}}

Return exactly:
{
  "executive_case_summary": {"one_line_summary": null, "case_overview": null, "favoured_party": null, "key_sections_involved": []},
  "case_identity": {"case_number": null, "title": null, "court": null, "bench": null, "judgment_date": null, "citation": null},
  "parties": [],
  "timeline_and_key_dates": [],
  "procedural_history": [],
  "charges_or_claims": [],
  "evidence_and_witnesses": [],
  "facts": [],
  "issues": [],
  "arguments": {"prosecutor_or_state": [], "defendant_or_accused": [], "appellant_or_petitioner": [], "respondent_or_opponent": [], "other_parties": []},
  "statutes_and_provisions": [],
  "statutory_interpretations": [],
  "precedents_cited": [],
  "decision": {"disposition": null, "holding": [], "sentence_or_penalty": null, "relief": [], "orders": []},
  "reasoning": [],
  "key_principles": [],
  "additional_observations": [],
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

# ==============================================================================
# 5. CANONICAL DATABASE SEED SCHEMA OBJECT
# ==============================================================================
LEGAL_JUDGMENT_SCHEMA = {
    "domain_name": LEGAL_DOMAIN_NAME,
    "domain_key": LEGAL_DOMAIN_KEY,
    "version": LEGAL_DOMAIN_VERSION,
    "description": LEGAL_DOMAIN_DESCRIPTION,
    "sections": LEGAL_SECTIONS,
    "fields": LEGAL_FIELDS_SPEC,
    "prompts": {
        "system_prompt": LEGAL_SYSTEM_PROMPT,
        "user_prompt_template": LEGAL_USER_PROMPT_TEMPLATE,
    },
}

# ==============================================================================
# 6. HELPER FUNCTIONS FOR PROMPT BUILDERS
# ==============================================================================
def build_free_extract_prompts(filename: str, content_snippet: str) -> tuple[str, str]:
    """Build system and user prompts for free-form legal document extraction."""
    sys_prompt = LEGAL_SYSTEM_PROMPT
    user_prompt = LEGAL_USER_PROMPT_TEMPLATE.format(
        filename=filename, content_snippet=content_snippet
    )
    return sys_prompt, user_prompt

def build_rag_prompt(*, document_id: int | str, filename: str, blocks: list[dict[str, Any]]) -> tuple[str, str]:
    """Build block-level evidence provenance prompts for RAG V1 processing."""
    rendered = "\n".join(
        f"BLOCK_ID={b['block_id']}\nPAGE={b['page']}\nTEXT={b['text']}\n"
        for b in blocks
    )
    user_prompt = (
        LEGAL_RAG_USER_TEMPLATE.replace("{{DOCUMENT_ID}}", str(document_id))
        .replace("{{FILENAME}}", filename)
        .replace("{{BLOCKS}}", rendered)
    )
    return LEGAL_RAG_SYSTEM_PROMPT, user_prompt
