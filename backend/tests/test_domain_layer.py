import pytest
from unittest.mock import AsyncMock

from app.core.database import AsyncSessionLocal, init_db
from app.models.db_models import DomainSchemaDB, KnowledgeBaseDB, CustomerDB, UserDB
from app.knowledge.domain_extractor import DomainExtractor


@pytest.mark.asyncio
async def test_domain_extractor_schema_and_extra_fields():
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = '''
    {
      "extracted_fields": {
        "policy_number": "POL-9988-ABC",
        "validity_expiry": "2028-12-31"
      },
      "extra_fields": {
        "deductible_amount": 500.0,
        "underwriter": "Acme Reinsurance"
      }
    }
    '''

    extractor = DomainExtractor(llm=mock_llm)
    schema_json = {
        "fields": [
            {"key": "policy_number", "label": "Policy Number", "type": "string", "weight": 2.0, "importance": "high"},
            {"key": "validity_expiry", "label": "Expiry Date", "type": "date", "weight": 1.5, "importance": "medium"},
        ]
    }

    res = await extractor.extract_domain_knowledge(
        text="Sample insurance policy document content POL-9988-ABC validity_expiry 2028-12-31 with deductible_amount 500.0 by underwriter Acme Reinsurance",
        filename="policy.pdf",
        domain_name="Insurance",
        domain_key="insurance",
        schema_json=schema_json,
        schema_extraction_system_prompt="Custom System Prompt for {domain_name}",
        schema_extraction_user_prompt="Extract for {filename}:\n{fields_summary}\n\nContent:\n{content}",
    )

    assert res["domain_key"] == "insurance"
    assert res["extracted_fields"]["policy_number"] == "POL-9988-ABC"
    assert res["extra_fields"]["deductible_amount"] == 500.0
    assert res["field_weights"]["policy_number"] == 2.0


from uuid import uuid4

@pytest.mark.asyncio
async def test_domain_schema_db_and_kb_linkage():
    await init_db()
    async with AsyncSessionLocal() as db:
        unique_domain = f"domaintenant_{uuid4().hex[:6]}.com"
        customer = CustomerDB(name=f"Domain Tenant {uuid4().hex[:4]}", domain=unique_domain)
        db.add(customer)
        await db.flush()

        u_id = uuid4().hex[:6]
        user = UserDB(
            username=f"admin_{u_id}",
            email_id=f"admin_{u_id}@domaintenant.com",
            password="hash",
            customer_id=customer.id,
            role="admin",
        )
        db.add(user)
        await db.flush()

        tenant_domain = DomainSchemaDB(
            name="Tenant Insurance Domain",
            domain_key="insurance",
            scope="TENANT",
            customer_id=customer.id,
            schema_json={
                "fields": [
                    {"key": "policy_number", "label": "Policy Number", "type": "string", "weight": 2.5, "importance": "high"}
                ]
            },
            system_prompt="Tenant Custom System Prompt",
            user_prompt="Tenant Custom User Prompt",
        )
        db.add(tenant_domain)
        await db.commit()

        kb = KnowledgeBaseDB(
            name="Insurance Claims KB",
            description="KB linked to insurance domain",
            customer_id=customer.id,
            domain_id=tenant_domain.id,
            created_by=user.id,
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)

        assert kb.domain_id == tenant_domain.id
        assert tenant_domain.schema_json["fields"][0]["weight"] == 2.5


@pytest.mark.asyncio
async def test_domain_weighted_field_boosting():
    query_lower = "pol-9988-abc insurance validity"
    candidates = [
        {
            "chunk_id": 1,
            "score": 0.80,
            "metadata": {
                "domain_info": {
                    "extracted_fields": {
                        "policy_number": "POL-9988-ABC",
                        "validity_expiry": "2028-12-31",
                    },
                    "extra_fields": {},
                    "field_weights": {"policy_number": 3.0, "validity_expiry": 1.5},
                }
            },
        },
        {
            "chunk_id": 2,
            "score": 0.85,
            "metadata": {
                "domain_info": {
                    "extracted_fields": {"policy_number": "POL-0000-XYZ"},
                    "extra_fields": {},
                    "field_weights": {"policy_number": 1.0},
                }
            },
        },
    ]

    for item in candidates:
        domain_info = (item.get("metadata") or {}).get("domain_info") or {}
        extracted_fields = domain_info.get("extracted_fields") or {}
        extra_fields = domain_info.get("extra_fields") or {}
        field_weights = domain_info.get("field_weights") or {}

        field_boost = 0.0

        all_fields = {**extracted_fields, **extra_fields}
        for f_key, f_val in all_fields.items():
            w = float(field_weights.get(f_key, 1.0))
            if f_key.lower() in query_lower:
                field_boost += w * 0.15
            if f_val and str(f_val).lower() in query_lower:
                field_boost += w * 0.25

        if field_boost > 0:
            item["score"] = item["score"] * (1.0 + field_boost)
            item["metadata"]["domain_score_boost"] = round(field_boost, 4)

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Chunk 1 had higher matching field weights and was boosted above Chunk 2
    assert candidates[0]["chunk_id"] == 1
    assert candidates[0]["metadata"]["domain_score_boost"] > 0



