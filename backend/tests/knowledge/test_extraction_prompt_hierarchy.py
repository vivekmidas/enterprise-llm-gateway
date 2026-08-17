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
        system_prompt_template=kb_custom_prompt,
        user_prompt_template=kb_user_prompt,
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
        system_prompt_template=domain_sys_prompt,
        user_prompt_template=domain_user_prompt,
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
        system_prompt_template=None,
        user_prompt_template=None,
    )

    called_sys_prompt, called_user_prompt = mock_llm.complete.call_args[0][:2]
    assert "precise document entity extractor" in called_sys_prompt
    assert res["extracted_fields"]["contract_id"] == "CNT-777"
