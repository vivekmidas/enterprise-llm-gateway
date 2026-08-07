"""
Unit test for domain schema seeding and synchronization across EKPDomainDB and DomainSchemaDB.
"""

import pytest
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.seed_data import seed_all_domains
from app.models.db_models import DomainSchemaDB, EKPDomainDB


@pytest.mark.asyncio
async def test_seed_all_domains():
    async with AsyncSessionLocal() as session:
        await seed_all_domains(session)

        # Verify EKPDomainDB populated
        ekp_stmt = select(EKPDomainDB).where(EKPDomainDB.id == "legal_judgment")
        ekp_res = await session.execute(ekp_stmt)
        ekp_domain = ekp_res.scalar_one_or_none()

        assert ekp_domain is not None
        assert ekp_domain.name == "Legal Judgments & Court Orders"
        assert "sections" in ekp_domain.schema_definition
        assert len(ekp_domain.schema_definition["sections"]) == 18

        # Verify all 18 sections present
        expected_sections = [
            "executive_case_summary", "document", "parties", "procedural_history",
            "facts", "legal_provisions", "issues", "labour_court_findings",
            "industrial_court", "high_court_arguments", "evidence", "legal_concepts",
            "research_topics", "keywords", "citations", "judgment_status",
            "knowledge_graph_entities", "embedding_metadata"
        ]
        for section in expected_sections:
            assert section in ekp_domain.schema_definition["sections"]

        # Verify DomainSchemaDB populated
        schema_stmt = select(DomainSchemaDB).where(DomainSchemaDB.domain_key == "legal_judgment")
        schema_res = await session.execute(schema_stmt)
        domain_schema = schema_res.scalar_one_or_none()

        assert domain_schema is not None
        assert domain_schema.system_prompt is not None
        assert domain_schema.user_prompt is not None
        assert "executive_case_summary" in domain_schema.user_prompt
