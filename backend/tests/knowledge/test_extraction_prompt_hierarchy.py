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


