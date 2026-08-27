import pytest
from unittest.mock import AsyncMock

from app.knowledge.domain_extractor import DomainExtractor


@pytest.mark.asyncio
async def test_kb_custom_prompt_overrides_domain_schema():
    """Verify that KB-level extraction_prompt takes precedence over DomainSchema prompt."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = '''
    {
      "extracted_fields": {
        "invoice_number": "INV-2026-999",
        "vendor": "Acme Corp"
      },
      "extra_fields": {}
    }
    '''
    extractor = DomainExtractor(llm=mock_llm)

    kb_custom_prompt = "You are a specialized Invoice Extractor. Extract invoice numbers strictly."
    kb_user_prompt = "Invoice Document: {filename}\nContent:\n{content}"

    res = await extractor.extract_domain_knowledge(
        text="Invoice Document INV-2026-999 from vendor Acme Corp total 1000",
        filename="invoice_sample.pdf",
        domain_name="Finance",
        domain_key="finance",
        schema_json={"fields": [{"key": "invoice_number", "label": "Invoice #"}]},
        kb_extraction_system_prompt=kb_custom_prompt,
        kb_extraction_user_prompt=kb_user_prompt,
        strategy="override",
    )

    # Check LLM call arguments
    mock_llm.complete.assert_called_once()
    called_sys_prompt, called_user_prompt = mock_llm.complete.call_args[0][:2]

    assert called_sys_prompt == kb_custom_prompt
    assert "invoice_sample.pdf" in called_user_prompt
    assert res["extracted_fields"]["invoice_number"] == "INV-2026-999"
    assert res["debug_info"]["system_prompt"] == kb_custom_prompt


@pytest.mark.asyncio
async def test_domain_schema_prompt_used_when_kb_prompt_missing():
    """Verify domain schema prompt is used when KB has no custom extraction_prompt."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = '''
    {
      "extracted_fields": {
        "employee_id": "EMP-42",
        "department": "Engineering"
      }
    }
    '''
    extractor = DomainExtractor(llm=mock_llm)

    domain_sys_prompt = "You are an HR Policy Extractor for {domain_name}."
    domain_user_prompt = "Filename: {filename}\n\nSchema:\n{fields_summary}\n\nText:\n{content}"

    res = await extractor.extract_domain_knowledge(
        text="Employee handbook for EMP-42 in Engineering department",
        filename="handbook.docx",
        domain_name="HR",
        domain_key="hr",
        schema_json={"fields": [{"key": "employee_id", "label": "Employee ID"}]},
        schema_extraction_system_prompt=domain_sys_prompt,
        schema_extraction_user_prompt=domain_user_prompt,
        strategy="inherit",
    )

    called_sys_prompt, called_user_prompt = mock_llm.complete.call_args[0][:2]
    assert "HR" in called_sys_prompt
    assert "handbook.docx" in called_user_prompt
    assert res["extracted_fields"]["employee_id"] == "EMP-42"


@pytest.mark.asyncio
async def test_system_default_prompt_when_no_templates():
    """Verify system default grounded prompt when no custom templates are set."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = '''
    {
      "contract_id": "CNT-777"
    }
    '''
    extractor = DomainExtractor(llm=mock_llm)

    res = await extractor.extract_domain_knowledge(
        text="General agreement contract_id CNT-777 effective immediately",
        filename="contract.txt",
        domain_name="General",
        domain_key="general",
        schema_json=None,
        schema_extraction_system_prompt=None,
        schema_extraction_user_prompt=None,
        strategy="inherit",
    )

    called_sys_prompt, called_user_prompt = mock_llm.complete.call_args[0][:2]
    assert "precise document entity extractor" in called_sys_prompt
    assert res["extracted_fields"]["contract_id"] == "CNT-777"


@pytest.mark.asyncio
async def test_legal_search_prompt_and_schema():
    """Verify LEGAL_SEARCH_SYSTEM_PROMPT includes multi-case list instruction and required keys."""
    from app.knowledge.legal_sot import LEGAL_SEARCH_SYSTEM_PROMPT, LEGAL_JUDGMENT_SCHEMA

    assert "cases" in LEGAL_SEARCH_SYSTEM_PROMPT
    assert "case_summary" in LEGAL_SEARCH_SYSTEM_PROMPT
    assert "2 sentences or 30-40 words" in LEGAL_SEARCH_SYSTEM_PROMPT
    assert "sections_or_articles_involved" in LEGAL_SEARCH_SYSTEM_PROMPT
    assert "court_type" in LEGAL_SEARCH_SYSTEM_PROMPT
    assert "judge" in LEGAL_SEARCH_SYSTEM_PROMPT
    assert "current_status" in LEGAL_SEARCH_SYSTEM_PROMPT
    assert "respondents" in LEGAL_SEARCH_SYSTEM_PROMPT
    assert "search_system_prompt" in LEGAL_JUDGMENT_SCHEMA["prompts"]


@pytest.mark.asyncio
async def test_kb_combine_strategy_concatenates_prompts():
    """Verify that combine strategy concatenates Schema extraction system prompt and KB custom prompt."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = '{"extracted_fields": {"clause": "Confidentiality"}}'
    extractor = DomainExtractor(llm=mock_llm)

    schema_prompt = "You are a Legal Contract Extractor."
    kb_prompt = "Emphasize arbitration and confidentiality clauses specifically."

    res = await extractor.extract_domain_knowledge(
        text="This agreement is governed by confidentiality and arbitration rules.",
        filename="contract.pdf",
        domain_name="Legal",
        domain_key="legal",
        schema_json={"fields": [{"key": "clause", "label": "Clause"}]},
        schema_extraction_system_prompt=schema_prompt,
        kb_extraction_system_prompt=kb_prompt,
        strategy="combine",
    )

    mock_llm.complete.assert_called_once()
    called_sys_prompt, _ = mock_llm.complete.call_args[0][:2]

    assert "You are a Legal Contract Extractor." in called_sys_prompt
    assert "Emphasize arbitration and confidentiality clauses specifically." in called_sys_prompt
    assert "### Knowledge Base Extraction Directives:" in called_sys_prompt
    assert res["debug_info"]["strategy"] == "combine"
    assert res["debug_info"]["prompt_source"] == "combined"


@pytest.mark.asyncio
async def test_kb_inherit_strategy_uses_domain_schema():
    """Verify that inherit strategy uses DomainSchema prompt as-is."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = '{"extracted_fields": {"patient_id": "P-101"}}'
    extractor = DomainExtractor(llm=mock_llm)

    schema_prompt = "You are a Clinical Healthcare Extractor for {domain_name}."
    kb_prompt = "Ignore this KB prompt under inherit mode."

    res = await extractor.extract_domain_knowledge(
        text="Patient P-101 diagnosis report admitted yesterday.",
        filename="report.pdf",
        domain_name="Healthcare",
        domain_key="healthcare",
        schema_json={"fields": [{"key": "patient_id", "label": "Patient ID"}]},
        schema_extraction_system_prompt=schema_prompt,
        kb_extraction_system_prompt=kb_prompt,
        strategy="inherit",
    )

    called_sys_prompt, _ = mock_llm.complete.call_args[0][:2]
    assert "Healthcare" in called_sys_prompt
    assert "Ignore this KB prompt" not in called_sys_prompt
    assert res["debug_info"]["strategy"] == "inherit"
    assert res["debug_info"]["prompt_source"] == "domain_schema"


def test_domain_research_schemas_support_client_prompts():
    """Verify SearchRequest and SynthesizeRequest schemas accept clear client-level prompt fields."""
    from app.api.knowledge.domain_research_router import SearchRequest, SynthesizeRequest, IngestRequest

    search_req = SearchRequest(
        query="tax appeal",
        search_system_prompt="Custom Search Persona",
        search_user_prompt="Context:\n{context}\n\nQuery:\n{query}",
    )
    assert search_req.search_system_prompt == "Custom Search Persona"
    assert "{context}" in search_req.search_user_prompt

    synth_req = SynthesizeRequest(
        instruction="Summarize judgments",
        drafting_system_prompt="Custom Drafter Persona",
        drafting_user_prompt="Records:\n{context}\n\nTask:\n{instruction}",
    )
    assert synth_req.drafting_system_prompt == "Custom Drafter Persona"
    assert "{instruction}" in synth_req.drafting_user_prompt
    # Alias compatibility
    synth_req_alias = SynthesizeRequest(
        instruction="Summarize judgments",
        synthesize_system_prompt="Custom Synthesizer Persona",
    )
    assert synth_req_alias.synthesize_system_prompt == "Custom Synthesizer Persona"

    ingest_req = IngestRequest(
        title="Document 1",
        schema_extraction_system_prompt="Custom Ingest Extractor",
        strategy="combine",
    )
    assert ingest_req.strategy == "combine"
    assert ingest_req.schema_extraction_system_prompt == "Custom Ingest Extractor"


@pytest.mark.asyncio
async def test_canonical_anti_drift_cues_in_prompts():
    """Verify that default and legal system prompts contain strict anti-drift cues."""
    from app.knowledge.legal_sot import LEGAL_SYSTEM_PROMPT, LEGAL_USER_PROMPT_TEMPLATE

    assert "STRICT FIELD CANONICALIZATION" in LEGAL_SYSTEM_PROMPT
    assert "judge (singular), NOT `coram`" in LEGAL_SYSTEM_PROMPT or "judge" in LEGAL_SYSTEM_PROMPT
    assert "case_number" in LEGAL_SYSTEM_PROMPT
    assert "extra_fields" in LEGAL_SYSTEM_PROMPT
    assert "extracted_fields" in LEGAL_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_reconcile_drifted_keys_and_extra_fields():
    """Verify that drifted keys (coram, case_numbers, acts) are reconciled to canonical schema keys and unmapped keys route to extra_fields."""
    import json
    from app.knowledge.domain_extractor import reconcile_extracted_payload, DomainExtractor
    from unittest.mock import AsyncMock

    fields = [
        {"key": "document", "label": "Document Metadata", "properties": {"judge": "Judge name", "case_number": "Case No", "court": "Court name"}},
        {"key": "legal_provisions", "label": "Provisions", "properties": {"statutes": ["Acts"], "sections": ["Sections"]}},
    ]

    mock_llm = AsyncMock()
    # LLM returned drifted keys: coram instead of judge, case_numbers instead of case_number, custom unmapped field
    mock_llm.complete.return_value = json.dumps({
        "extracted_fields": {
            "document": {
                "coram": "Justice H.C. Mishra",
                "case_numbers": "Cr. Appeal 423 of 2006",
                "court_name": "High Court of Jharkhand",
            },
            "acts": ["Indian Penal Code", "Arms Act"],
            "unmapped_custom_metric": "Risk Score 95",
        },
        "extra_fields": {
            "additional_fact": "Hospitalized at MGM",
        }
    })

    extractor = DomainExtractor(llm=mock_llm)
    res = await extractor.extract_domain_knowledge(
        text="High Court of Jharkhand. Justice H.C. Mishra presided. Cr. Appeal 423 of 2006. Indian Penal Code and Arms Act. Hospitalized at MGM. Risk Score 95.",
        filename="judgment.pdf",
        domain_name="Legal Judgments",
        domain_key="legal_judgment",
        schema_json={"fields": fields},
    )

    extracted = res["extracted_fields"]
    extra = res["extra_fields"]

    # Reconciled to canonical keys inside document
    assert "document" in extracted
    assert extracted["document"]["judge"] == "Justice H.C. Mishra"
    assert extracted["document"]["case_number"] == "Cr. Appeal 423 of 2006"
    assert extracted["document"]["court"] == "High Court of Jharkhand"

    # Drifted key 'acts' mapped to schema key 'legal_provisions' or preserved canonically
    # Unmapped custom metric moved to extra_fields
    assert "unmapped_custom_metric" in extra or "unmapped_custom_metric" in str(extra)
    assert extra.get("additional_fact") == "Hospitalized at MGM"


@pytest.mark.asyncio
async def test_domain_extractor_passes_clean_prompt_and_document_text():
    """Verify that DomainExtractor passes decoupled user_prompt template and raw document_text to LLM."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = '{"extracted_fields": {"court": "Supreme Court of India"}}'
    extractor = DomainExtractor(llm=mock_llm)

    custom_user_template = "Extract a comprehensive structured JSON from the above legal document matching the target schema."
    sample_text = "IN THE SUPREME COURT OF INDIA. Civil Appeal No. 1234 of 2024. Justice ABC."

    res = await extractor.extract_domain_knowledge(
        text=sample_text,
        filename="judgment_sc.pdf",
        domain_name="Legal",
        domain_key="legal",
        schema_json={"fields": [{"key": "court", "label": "Court"}]},
        kb_extraction_user_prompt=custom_user_template,
        strategy="override",
    )

    mock_llm.complete.assert_called_once()
    called_sys_prompt, called_user_prompt = mock_llm.complete.call_args[0][:2]
    kwargs = mock_llm.complete.call_args[1]

    # Verify template is passed to LLM and text is passed via document_text
    assert custom_user_template in called_user_prompt
    assert kwargs.get("document_text") == sample_text
    assert res["extracted_fields"]["court"] == "Supreme Court of India"


@pytest.mark.asyncio
async def test_domain_llm_render_user_prompt_and_single_pass():
    """Verify that DomainLLM properly renders user_prompt with document_text in single-pass mode."""
    from app.knowledge.domain_rag_v1.domains.legal.llm import DomainLLM

    llm = DomainLLM()
    # Test template without placeholder
    rendered = llm._render_user_prompt("Extract all fields.", "Sample Judgment Text")
    assert "Document Content:\nSample Judgment Text" in rendered
    assert "Extract all fields." in rendered

    # Test template with {content} placeholder
    rendered_placeholder = llm._render_user_prompt("Text:\n{content}\nTask: extract", "Sample Judgment Text")
    assert rendered_placeholder == "Text:\nSample Judgment Text\nTask: extract"

