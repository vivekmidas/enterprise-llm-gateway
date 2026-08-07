import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models.db_models import Base, LLMProfileDB, CustomerDB
from app.core.profile_resolver import ProfileResolver
from app.api.profiles.sections_router import _patch_section


@pytest_asyncio.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_llm_profile_section_patch_persistence(async_test_db: AsyncSession):
    # 1. Create a customer and LLM profile with initial settings
    cust = CustomerDB(id="tenant-uuid-123", name="Test Customer", status="active")
    async_test_db.add(cust)

    initial_settings = {
        "embedding": {
            "provider": "ollama",
            "model": "nomic-embed-text",
            "dimension": 768,
        },
        "generation": {
            "provider": "ollama",
            "model": "llama3.2",
        },
    }
    prof = LLMProfileDB(
        id="profile-uuid-456",
        name="Default Profile",
        is_default=True,
        customer_id="tenant-uuid-123",
        created_by="user-1",
        settings=initial_settings,
    )
    async_test_db.add(prof)
    await async_test_db.commit()

    # 2. Patch generation section (e.g. changing model from llama3.2 to gpt-4o)
    mock_user = {"role": "admin", "tenant": "tenant-uuid-123", "id": "user-1"}
    patch_payload = {
        "provider": "openai",
        "model": "gpt-4o",
        "url": "https://api.openai.com",
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    updated_prof = await _patch_section(
        profile_id="profile-uuid-456",
        section_name="generation",
        section_data=patch_payload,
        current_user=mock_user,
        db=async_test_db,
    )

    assert updated_prof.settings["generation"]["model"] == "gpt-4o"
    assert updated_prof.settings["generation"]["provider"] == "openai"

    # 3. Query afresh from DB to verify ORM persistence
    res = await async_test_db.execute(select(LLMProfileDB).where(LLMProfileDB.id == "profile-uuid-456"))
    db_prof = res.scalar_one()
    assert db_prof.settings["generation"]["model"] == "gpt-4o"
    assert db_prof.settings["generation"]["provider"] == "openai"
    assert db_prof.settings["embedding"]["model"] == "nomic-embed-text"  # preserved

    # 4. Verify ProfileResolver resolves updated profile with string UUIDs
    resolver = ProfileResolver(db=async_test_db)
    resolved = await resolver.resolve(profile_id="profile-uuid-456", customer_id="tenant-uuid-123")
    assert resolved.generation.model == "gpt-4o"
    assert resolved.generation.provider == "openai"
    assert resolved.embedding.model == "nomic-embed-text"
