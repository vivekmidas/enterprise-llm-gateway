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
    "connected_cases",
    "parties",
    "procedural_history",
    "facts",
    "legal_provisions",
    "issues",
    "labour_court_findings",
    "industrial_court",
    "high_court_arguments",
    "evidence",
    "court_findings",
    "legal_concepts",
    "research_topics",
    "keywords",
    "citations",
    "judgment_status",
    "knowledge_graph_entities",
    "embedding_metadata",
]

# Map of legal field descriptions (for extraction runtime validation and schema rendering)
LEGAL_FIELDS = {
    "executive_case_summary": {
        "one_line_summary": "Single sentence executive summary of the case or agreement",
        "case_overview": "Comprehensive overview describing dispute/contract, main parties, statutory provisions or contract purpose, outcome, and favoured party",
        "favoured_party": "Name and role of party in whose favour the ruling was decided (if court judgment)",
        "key_sections_involved": ["List of key statutory sections or clauses involved"],
    },
    "document": {
        "court": "",
        "location": "",
        "case_number": [""],
        "citation": "",
        "decision_date": "",
        "judge": [""],
        "judgment_type": "",
    },
    "case_identity": {
        "court": "",
        "location": "",
        "case_number": [""],
        "connected_cases": "",
        "number_of_connected_cases": "",
        "report_number": "",
        "case_date": "",
        "judge": [""],
    },
    "parties": {
        "petitioners": [""],
        "respondents": [""],
        "appellants": [""],
        "prosecutors": [""],
        "defendants": [""],
        "advocates": [""],
        "other_parties": [""],
    },
    "facts": {
        "incident_date": "",
        "allegations": "",
        "dispute_history": "",
    },
    "legal_provisions": {
        "statutes": [""],
        "sections": [""]
    },
    "labour_court_findings": {
        "enquiry_fairness": "",
        "natural_justice": "",
        "misconduct": "",
        "relief_granted": "",
    },
    "industrial_court": {
        "revision_application": "",
        "revision_order": "",
    },
    "high_court_arguments": {
        "petitioner_arguments": [""],
        "respondent_arguments": [""],
    },
    "evidence": {
        "documentary_evidence": [""],
        "witness_statements": [""],
    },
    "citations": {
        "precedents": [""],
        "statutes_referred": [""],
    },
    "judgment_status": {
        "final_decision": "",
        "holding": "",
        "sentence_or_penalty": "",
        "relief": "",
    },
    "contract_overview": {
        "agreement_type": "",
        "purpose": "",
        "effective_date": "",
        "expiration_date": "",
        "governing_law": "",
        "jurisdiction": "",
    },
    "contract_parties": {
        "party_a": "",
        "party_b": "",
        "other_signatories": [""]
    },
    "financial_terms": {
        "contract_value": "",
        "payment_schedule": "",
        "currency": "",
        "penalties_or_interest": "",
    },
    "termination_and_renewal": {
        "termination_for_convenience": "",
        "termination_for_breach": "",
        "notice_period": "",
        "renewal_terms": "",
    },
    "liability_and_indemnity": {
        "liability_cap": "",
        "indemnity_obligations": "",
    },
    "dispute_resolution": {
        "method": "",
        "arbitration_seat": "",
        "applicable_rules": "",
    },
    "knowledge_graph_entities": {
        "persons": [""],
        "organizations": [""],
        "locations": [""],
        "dates": [""],
    },
    "embedding_metadata": {
        "domain": "legal",
        "practice_areas": [""],
        "confidence": 1.0,
    },
    "substance": {
        "timeline_and_key_dates": [""],
        "procedural_history": [""],
        "charges_or_claims": [""],
        "evidence_and_witnesses": [""],
        "issues": [""],
        "facts": [""],
        "arguments": [""],
        "statutes": [""],
        "statutory_interpretations": [""],
        "precedents": [""],
        "additional_observations": [""],
    },
    "decision": {
        "disposition": "",
        "holding": "",
        "sentence_or_penalty": "",
        "relief": "",
    },
}

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
        "properties": LEGAL_FIELDS["executive_case_summary"],
    },
    {
        "key": "document",
        "label": "Document Metadata",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Title, court, jurisdiction, primary case number, connected cases, citation, decision date, coram, judgment type",
        "properties": LEGAL_FIELDS["document"],
    },
    {
        "key": "connected_cases",
        "label": "Connected & Consolidated Cases",
        "type": "array",
        "weight": 2.5,
        "importance": "high",
        "required": False,
        "description": "Array of case objects pairing each connected case/petition to its plaintiff and respondent",
        "items": {
            "case": "<case number>",
            "plaintiff": "<petitioner/plaintiff name>",
            "respondent": "<respondent/defendant name>",
            "advocate": "<advocate name>",
            "date": "<date>",
        },
    },
    {
        "key": "parties",
        "label": "Parties & Advocates",
        "type": "object",
        "weight": 2.5,
        "importance": "high",
        "required": False,
        "description": "Petitioner, respondent, prosecutor, defendant, and advocates for each side",
        "properties": LEGAL_FIELDS["parties"],
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
        "description": "Incident date, timeline, background facts, allegations, claims, or contractual dispute background",
        "properties": LEGAL_FIELDS["facts"],
    },
    {
        "key": "legal_provisions",
        "label": "Legal Provisions",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Statutes, acts, sections, and schedule items cited in judgment or contract",
        "properties": LEGAL_FIELDS["legal_provisions"],
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
        "properties": LEGAL_FIELDS["labour_court_findings"],
    },
    {
        "key": "industrial_court",
        "label": "Industrial Court Findings",
        "type": "object",
        "weight": 2.0,
        "importance": "medium",
        "required": False,
        "description": "Revision application details and revision order",
        "properties": LEGAL_FIELDS["industrial_court"],
    },
    {
        "key": "high_court_arguments",
        "label": "High Court Arguments",
        "type": "object",
        "weight": 2.5,
        "importance": "high",
        "required": False,
        "description": "Submissions and arguments of petitioner, respondent, prosecutor, and defense",
        "properties": LEGAL_FIELDS["high_court_arguments"],
    },
    {
        "key": "evidence",
        "label": "Evidence & Witnesses",
        "type": "object",
        "weight": 1.5,
        "importance": "medium",
        "required": False,
        "description": "Documentary evidence, inspection reports, and witness statements",
        "properties": LEGAL_FIELDS["evidence"],
    },
    {
        "key": "legal_concepts",
        "label": "Legal Concepts",
        "type": "array",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Core legal concepts (e.g. Natural Justice, Perversity, Unfair Labour Practice, Force Majeure)",
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
        "properties": LEGAL_FIELDS["citations"],
    },
    {
        "key": "judgment_status",
        "label": "Judgment Status & Holding",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Portion available, final decision, ratio decidendi, obiter dicta",
        "properties": LEGAL_FIELDS["judgment_status"],
    },
    {
        "key": "contract_overview",
        "label": "Contract & Agreement Overview",
        "type": "object",
        "weight": 2.5,
        "importance": "high",
        "required": False,
        "description": "Agreement title, contract type, effective date, term duration, governing law, and jurisdiction",
        "properties": LEGAL_FIELDS["contract_overview"],
    },
    {
        "key": "contract_parties",
        "label": "Contracting Parties",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Party A, Party B, parent entities, and authorized signatories",
        "properties": LEGAL_FIELDS["contract_parties"],
    },
    {
        "key": "key_clauses",
        "label": "Key Clauses & Obligations",
        "type": "array",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Major covenants, deliverables, warranties, non-compete, or confidentiality clauses",
    },
    {
        "key": "financial_terms",
        "label": "Financial & Payment Terms",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Contract value, consideration, payment schedule, and penalty terms",
        "properties": LEGAL_FIELDS["financial_terms"],
    },
    {
        "key": "termination_and_renewal",
        "label": "Termination & Renewal Terms",
        "type": "object",
        "weight": 2.0,
        "importance": "medium",
        "required": False,
        "description": "Termination for cause/convenience, notice periods, and renewal conditions",
        "properties": LEGAL_FIELDS["termination_and_renewal"],
    },
    {
        "key": "liability_and_indemnity",
        "label": "Liability & Indemnity",
        "type": "object",
        "weight": 2.0,
        "importance": "medium",
        "required": False,
        "description": "Limitation of liability, indemnity obligations, and exclusions",
        "properties": LEGAL_FIELDS["liability_and_indemnity"],
    },
    {
        "key": "dispute_resolution",
        "label": "Dispute Resolution & Jurisdiction",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Arbitration seat, arbitration rules, mediation, and court venue",
        "properties": LEGAL_FIELDS["dispute_resolution"],
    },
    {
        "key": "knowledge_graph_entities",
        "label": "Knowledge Graph Entities",
        "type": "object",
        "weight": 2.0,
        "importance": "high",
        "required": False,
        "description": "Extracted persons, organizations, and key dates",
        "properties": LEGAL_FIELDS["knowledge_graph_entities"],
    },
    {
        "key": "embedding_metadata",
        "label": "Embedding Metadata",
        "type": "object",
        "weight": 1.0,
        "importance": "low",
        "required": False,
        "description": "Domain, practice areas, extraction confidence score",
        "properties": LEGAL_FIELDS["embedding_metadata"],
    },
]

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
                "case_number": {"type": "array", "items": {"type": "string"}},
                "connected_cases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "case": {"type": ["string", "null"]},
                            "case_number": {"type": "array", "items": {"type": "string"}},
                            "plaintiff": {"type": ["string", "null"]},
                            "respondent": {"type": ["string", "null"]},
                            "advocate": {"type": ["string", "null"]},
                            "date": {"type": ["string", "null"]},
                        },
                    },
                },
                "number_of_connected_cases": {"type": ["integer", "number", "null"]},
                "report_number": {"type": ["string", "null"]},
                "case_date": {"type": ["string", "null"]},
                "judge": {"type": "array", "items": {"type": "string"}},
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
    "RULE 4: STRICT FIELD CANONICALIZATION: Follow exact canonical schema field names. Do NOT drift or rename "
    "(e.g. use `judge` (as an array of strings), NOT `coram`/`judges`/`bench`; use `case_number` (as an array of strings), NOT `case_numbers`/`case_no`; "
    "use `decision_date`, NOT `order_date`/`judgment_date`; use `court`, NOT `court_name`/`forum`; use `statutes`, NOT `acts`; "
    "use `sections`, NOT `provisions`/`articles`; use `petitioners`, NOT `petitioner`; use `respondents`, NOT `respondent`; "
    "use `advocates`, NOT `counsels`/`lawyers`; use `final_decision`, NOT `disposition`/`outcome`).\n"
    "RULE 5: STRICT SCHEMA BOUNDARY: Place ONLY defined schema fields under 'extracted_fields'. "
    "Any additional unmapped facts, observed attributes, or case details MUST go under 'extra_fields'. "
    "NEVER place unmapped keys into 'extracted_fields'.\n"
    "RULE 6: For party names, extract actual names of people, government bodies, or companies, NOT generic roles.\n"
    "RULE 7: Capture specific arguments made by the Prosecutor/Prosecution/State, Defendant/Accused/Defense counsel, Petitioner/Appellant, Respondent, and Other Parties (Intervenors/Amicus Curiae).\n"
    "RULE 8: When multiple cases/petitions are decided together, DO NOT separate plaintiffs and case numbers into separate detached lists. Pair each case directly with its respective plaintiff and respondent in 'connected_cases'\n"
    "RULE 9: Use exact wording from the document for all values.\n"
    "RULE 10: DO NOT MISS ANY HELPFUL INFORMATION. Capture all timeline events, evidence, lower court details, judicial observations, statutory interpretations, and additional data points present in the text.\n"
    "RULE 11: You are a strict factual extractor. Never invent information. Never use placeholder names such as Party A, Party B, AAA, BBB, XYZ, etc. Never create fake dates or timelines.  Only output information that is explicitly written in the DOCUMENT TEXT." 
)

# ==============================================================================
# BLOCK COMMENT: PROMPT TEMPLATES & HELPER FUNCTIONS (SINGLE SOURCE OF TRUTH)
# Purpose:
# 1. System prompt defines extraction rules without duplicate hardcoded field lists.
# 2. User prompt uses placeholders ({filename}, {fields_summary}, {fields_json_schema}, {content}).
# 3. Dynamic prompt builder constructs field summaries and target JSON directly from LEGAL_FIELDS_SPEC / fields.
# ==============================================================================

LEGAL_USER_PROMPT_TEMPLATE = (

    "Extract a comprehensive structured JSON from the legal document {content} matching the target schema.\n"
    "CRITICAL INSTRUCTIONS:\n"
    "- Extract ONLY factual information explicitly present in the document.\n"
    "- Omit any field not found — do NOT write null, empty strings, or bracketed placeholders like '[Name]' or '[Judge]'.\n"
    "- STRICT CANONICAL FIELD NAMES: Use judge (array of strings), case_number (array of strings), court, decision_date, statutes, sections, petitioners, respondents, advocates.\n"
    "- Place ONLY defined target schema fields in 'extracted_fields'.\n"
    "- Place ALL unmapped extra facts, observations, or additional metadata in 'extra_fields'.\n"
    "- For connected/consolidated cases: DO NOT separate plaintiffs and case numbers into separate detached lists. Extract each case as a paired object in 'connected_cases'.\n"
    "- For party names, extract actual names of people, government bodies, or companies, NOT generic roles.\n"
    "- Capture specific arguments mapped to the party making them where present.\n"
    '- Output valid JSON only matching: {"extracted_fields": { ... }, "extra_fields": { ... }}.\n'
    'Extract information STRICTLY from the DOCUMENT TEXT below.\n'
    'Use only facts that appear in the document.\n'
    'Do not invent any names, dates, parties, courts, or events.\n'
    'Omit any field that has no information.\n'
    'Return valid JSON in this structure:\n'
    """{
        "extracted_fields": {
        "executive_case_summary": {
        "one_line_summary": "",
        "case_overview": "",
        "favoured_party": "",
        "key_sections_involved": []
        },
        "document": {
        "court": "",
        "judge": [],
        "citation": "",
        "case_number": [],
        "decision_date": "",
        "judgment_type": ""
        },
        "parties": {
        "appellants": [],
        "respondents": [],
        "advocates": []
        },
        "procedural_history": [],
        "facts": {
        "allegations": "",
        "incident_date": "",
        "dispute_history": ""
        },
        "legal_provisions": {
        "statutes": [],
        "sections": []
        },
        "issues": [],
        "citations": {
        "precedents": [],
        "statutes_referred": []
        },
        "judgment_status": {
        "final_decision": "",
        "holding": ""
        },
        "knowledge_graph_entities": {
        "persons": [],
        "organizations": [],
        "locations": [],
        "dates": []
        }
    },
    "extra_fields": {}
    }"""
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

TARGET SCHEMA STRUCTURE:
{{TARGET_SCHEMA}}

SOURCE BLOCKS:
{{BLOCKS}}

Extract all verifiable entities and factual claims referencing valid block IDs.
Allowed evidence_type: CASE_IDENTITY, PARTY, PROCEDURAL_HISTORY, FACT, ISSUE,
ARGUMENT, STATUTE, PRECEDENT, COURT_FINDING, HOLDING, RELIEF, ORDER, REASONING,
LEGAL_PRINCIPLE, OUTCOME_FACTOR, NOTE.
Return JSON only.
"""

# ==============================================================================
# BLOCK COMMENT: LEGAL SEARCH SYNTHESIS PROMPT (SINGLE SOURCE OF TRUTH)
# Purpose:
# Formats multi-case search results into a JSON list of cases with minimum basic information:
# - case_summary: 2 sentences or 30-40 words maximum
# - sections_or_articles_involved
# - court_type
# - judge
# - current_status / outcome
# ==============================================================================
LEGAL_SEARCH_SYSTEM_PROMPT = """You are an expert Legal Document Knowledge Assistant analyzing the provided Context.
    "You are an expert Enterprise Legal and Knowledge Assistant.\n"
    "When the search results contain information from different cases (matters), format them as a JSON list under a top-level 'cases' key.\n"
    "- DO NOT GIVE PLEASANTRIES REASONING OR THOUGHTS OR SUMMARY JUST GIVE FACTUAL INFORMATION"
    " Return valid JSON only. Do not invent external citations or facts." 
### CRITICAL GROUNDING RULES:
1. Extract values ONLY from the provided Context.
2. NEVER copy dates, names, or summaries from the FEW-SHOT EXAMPLES below.
3. Group all co-accused, sections, and findings for the SAME proceeding into ONE case object. Do NOT split one judgment into multiple case entries.
4. If appeal is "Allowed in part" (e.g. some accused acquitted, one convicted), accurately state who was acquitted and who was convicted in `case_summary` (2 sentences or 30-40 words).
5. RULES to be followed - If convicted but appeal lost is convicted, if convicted earlier but appeal won is acquitted. If acquitted but appealed by other party and appeal lost is acquitted.
### TARGET JSON FORMAT:
{
  "cases": [
    {
      "case_title": "<Extract from Context>",
      "court_type": "<Extract from Context>",
      "judge": "<Extract from Context>",
      "decision_date": "<Extract from Context>",
      "outcome": "<Allowed / Dismissed / Allowed in Part>",
      "current_status": "<Current case status / disposition>",
      "parties": "<Extract from Context>",
      "respondents": ["<Extract from Context>"],
      "plaintiffs": ["<Extract from Context>"],
      "sections_or_articles_involved": ["<Extract from Context>"],
      "case_summary": "<2 sentences or 30-40 words factual summary from Context only>"
    }
  ]
}

### FEW-SHOT STRUCTURAL EXAMPLES:

[Example 1 - Acquittal / Appeal Allowed]
Context: "[Order in Appeal 999: State vs John Doe. Judge X. Date 01-Jan-2020. Accused convicted by lower court under Sec 302. High Court sets aside conviction and acquits accused.]"
Query: "case with 302 acquittal"
Response:
{
  "cases": [
    {
      "case_title": "State vs John Doe",
      "court_type": "High Court",
      "judge": "Judge X",
      "decision_date": "01-Jan-2020",
      "outcome": "Appeal Allowed (Acquitted)",
      "parties": "State vs John Doe",
      "respondents": ["John Doe"],
      "plaintiffs": ["State"],
      "sections_or_articles_involved": ["Section 302"],
      "case_summary": "High Court allowed the appeal and set aside conviction under Section 302."
    }
  ]
}

[Example 2 - Conviction Upheld / Appeal Dismissed]
Context: "[Order in Appeal 888: State vs Jane Doe. Judge Y. Date 01-Jan-2020. Conviction under Sec 302 upheld. Appeal dismissed.]"
Query: "case with 302 acquittal"
Response:
{
  "cases": []
}
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
        "search_system_prompt": LEGAL_SEARCH_SYSTEM_PROMPT,
    },
}

# ==============================================================================
# 6. HELPER FUNCTIONS FOR PROMPT BUILDERS (DYNAMIC SINGLE SOURCE OF TRUTH)
# ==============================================================================
def format_legal_fields_summary(fields: list[dict[str, Any]] | None = None) -> str:
    """Format human-readable bullet list of legal schema fields from SOT."""
    target_fields = fields if fields is not None else LEGAL_FIELDS_SPEC
    if not target_fields:
        return "Extract all key legal entities, facts, citations, and findings."
    lines = []
    for f in target_fields:
        k = f.get("key", "")
        lbl = f.get("label", k)
        t = f.get("type", "string")
        d = f.get("description", "")
        lines.append(f"- {k} ({lbl}, {t}): {d}" if d else f"- {k} ({lbl}, {t})")
    return "\n".join(lines)


def format_legal_fields_json_structure(fields: list[dict[str, Any]] | None = None) -> str:
    """Format target JSON schema structure dynamically from schema fields list with explicit subfield structure."""
    target_fields = fields if fields is not None else LEGAL_FIELDS_SPEC
    extracted_spec: dict[str, Any] = {}
    for f in target_fields:
        k = f.get("key")
        if not k:
            continue
        ft = (f.get("type") or "string").lower()
        desc = f.get("description") or f.get("label") or k
        if k == "connected_cases":
            extracted_spec[k] = [
                {
                    "case": "",
                    "plaintiff": "",
                    "respondent": "",
                    "advocate": "",
                    "date": "",
                }
            ]
        elif k in LEGAL_FIELDS and isinstance(LEGAL_FIELDS[k], dict):
            extracted_spec[k] = LEGAL_FIELDS[k]
        elif ft in ("array", "list"):
            extracted_spec[k] = [f"<{desc}>"]
        elif ft in ("object", "dict"):
            extracted_spec[k] = {"details": f"<{desc}>"}
        elif ft in ("number", "integer", "float"):
            extracted_spec[k] = f"0.0 (<{desc}>)"
        elif ft in ("bool", "boolean"):
            extracted_spec[k] = f"true/false (<{desc}>)"
        else:
            extracted_spec[k] = f"<{desc}>"

    import json
    return json.dumps({
        "extracted_fields": extracted_spec,
        "extra_fields": {"<unmapped_extra_field>": "<value>"}
    }, indent=2)


def build_free_extract_prompts(
    filename: str,
    content_snippet: str,
    fields: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Build system and user prompts for free-form legal document extraction dynamically from schema fields."""
    sys_prompt = LEGAL_SYSTEM_PROMPT
    fields_summary = format_legal_fields_summary(fields)
    fields_json_schema = format_legal_fields_json_structure(fields)

    user_prompt = (
        LEGAL_USER_PROMPT_TEMPLATE
        .replace("{filename}", str(filename or ""))
        .replace("{fields_summary}", fields_summary)
        .replace("{fields_json_schema}", fields_json_schema)
        .replace("{content}", str(content_snippet or ""))
        .replace("{content_snippet}", str(content_snippet or ""))
    )
    return sys_prompt, user_prompt


def build_rag_prompt(*, document_id: int | str, filename: str, blocks: list[dict[str, Any]]) -> tuple[str, str]:
    """Build block-level evidence provenance prompts for RAG V1 processing dynamically from SOT."""
    rendered = "\n".join(
        f"BLOCK_ID={b['block_id']}\nPAGE={b['page']}\nTEXT={b['text']}\n"
        for b in blocks
    )
    target_schema = format_legal_fields_json_structure()
    user_prompt = (
        LEGAL_RAG_USER_TEMPLATE.replace("{{DOCUMENT_ID}}", str(document_id))
        .replace("{{FILENAME}}", filename)
        .replace("{{TARGET_SCHEMA}}", target_schema)
        .replace("{{BLOCKS}}", rendered)
    )
    return LEGAL_RAG_SYSTEM_PROMPT, user_prompt


# ==============================================================================
# 7. CANONICAL LEGAL DISPOSITIONS & OUTCOMES (DOMAIN SINGLE SOURCE OF TRUTH)
# ==============================================================================
CANONICAL_DISPOSITIONS = [
    ("anticipatory bail", "ANTICIPATORY BAIL GRANTED"),
    ("regular bail", "REGULAR BAIL GRANTED"),
    ("bail granted", "BAIL GRANTED"),
    ("benefit of doubt", "ACQUITTED (BENEFIT OF DOUBT)"),
    ("partly allowed", "PARTLY ALLOWED"),
    ("partially allowed", "PARTLY ALLOWED"),
    ("conviction modified", "CONVICTION MODIFIED"),
    ("modified", "CONVICTION MODIFIED"),
    ("altered", "CONVICTION MODIFIED"),
    ("quash", "QUASHED"),
    ("acquit", "ACQUITTED"),
    ("dismiss", "DISMISSED"),
    ("rejected", "DISMISSED / REJECTED"),
    ("remand", "REMANDED"),
    ("allowed", "ALLOWED"),
]


def canonicalize_disposition(raw_outcome: str | None) -> str | None:
    """Legal domain helper to map outcome/disposition text into canonical uppercase terms."""
    if not raw_outcome:
        return None
    raw_lower = str(raw_outcome).lower().strip()
    for kw, canon in CANONICAL_DISPOSITIONS:
        if kw in raw_lower:
            return canon
    return str(raw_outcome)[:50].upper().strip()

