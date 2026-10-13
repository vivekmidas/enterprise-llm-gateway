# Mock presidio and spacy libraries to prevent network calls and spaCy downloads during test runs
import sys
import re
from unittest.mock import MagicMock

class MockRecognizerResult:
    def __init__(self, entity_type: str, start: int, end: int, score: float = 0.85):
        self.entity_type = entity_type
        self.start = start
        self.end = end
        self.score = score

class MockPattern:
    def __init__(self, name: str = "", regex: str = "", score: float = 0.85):
        self.name = name
        self.regex = regex
        self.score = score

class MockPatternRecognizer:
    def __init__(self, supported_entity: str = "", patterns: list = None, deny_list: list = None):
        self.supported_entity = supported_entity
        self.patterns = patterns or []
        self.deny_list = deny_list or []

class MockAnalyzerEngine:
    def __init__(self, *args, **kwargs):
        self.registry = MagicMock()

    def analyze(self, text: str, entities: list = None, language: str = "en", score_threshold: float = 0.0, ad_hoc_recognizers: list = None):
        if not text:
            return []
        results = []
        if not entities or "EMAIL_ADDRESS" in entities:
            for m in re.finditer(r"[\w\.-]+@[\w\.-]+\.\w+", text):
                results.append(MockRecognizerResult("EMAIL_ADDRESS", m.start(), m.end()))
        if not entities or "PHONE_NUMBER" in entities:
            for m in re.finditer(r"\+?\d[\d -]{8,15}\d", text):
                results.append(MockRecognizerResult("PHONE_NUMBER", m.start(), m.end()))
        if not entities or "PERSON" in entities:
            for m in re.finditer(r"\bJohn Doe\b", text):
                results.append(MockRecognizerResult("PERSON", m.start(), m.end()))
        if ad_hoc_recognizers:
            for rec in ad_hoc_recognizers:
                entity = getattr(rec, "supported_entity", "CUSTOM")
                for word in getattr(rec, "deny_list", []):
                    for m in re.finditer(re.escape(word), text, re.IGNORECASE):
                        results.append(MockRecognizerResult(entity, m.start(), m.end()))
                for pat in getattr(rec, "patterns", []):
                    regex = getattr(pat, "regex", None)
                    if regex:
                        for m in re.finditer(regex, text):
                            results.append(MockRecognizerResult(entity, m.start(), m.end()))
        return results

class MockOperatorConfig:
    def __init__(self, operator_name: str = "replace", params: dict = None):
        self.operator_name = operator_name
        self.params = params or {}

class MockAnonymizedText:
    def __init__(self, text: str):
        self.text = text

class MockAnonymizerEngine:
    def anonymize(self, text: str, analyzer_results: list, operators: dict = None):
        res_sorted = sorted(analyzer_results, key=lambda x: x.start, reverse=True)
        res_text = text
        for r in res_sorted:
            replacement = f"[REDACTED-{r.entity_type}]"
            if operators and r.entity_type in operators:
                op = operators[r.entity_type]
                replacement = op.params.get("new_value", replacement) if hasattr(op, "params") else replacement
            res_text = res_text[:r.start] + replacement + res_text[r.end:]
        return MockAnonymizedText(res_text)

presidio_mock = MagicMock()
presidio_mock.__path__ = []
presidio_mock.AnalyzerEngine = MockAnalyzerEngine
presidio_mock.Pattern = MockPattern
presidio_mock.PatternRecognizer = MockPatternRecognizer
sys.modules['presidio_analyzer'] = presidio_mock
sys.modules['presidio_analyzer.nlp_engine'] = MagicMock()

anonymizer_mock = MagicMock()
anonymizer_mock.__path__ = []
anonymizer_mock.AnonymizerEngine = MockAnonymizerEngine
sys.modules['presidio_anonymizer'] = anonymizer_mock

entities_mock = MagicMock()
entities_mock.OperatorConfig = MockOperatorConfig
sys.modules['presidio_anonymizer.entities'] = entities_mock

sys.modules['spacy'] = MagicMock()

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB
from sqlalchemy import select
from app.core.security.hash import get_password_hash
from app.core.security.jwt import create_access_token

import pytest_asyncio

@pytest_asyncio.fixture(scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture(scope="module")
async def system_admin_token() -> str:
    from app.core.database import init_db
    from app.nodes.registry import NodesRegistry
    await init_db()
    await NodesRegistry.node_auto_discover()
    async with AsyncSessionLocal() as session:
        stmt = select(UserDB).where(UserDB.email_id == "admin@gateway.com")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            user = UserDB(
                username="admin@gateway.com",
                email_id="admin@gateway.com",
                password=get_password_hash("password"),
                name="System Admin",
                role="system_admin",
                customer_id=None,
                status="active"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        elif user.role != "system_admin":
            user.role = "system_admin"
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
        token = create_access_token({
            "user_id": str(user.id),
            "email": user.email_id,
            "role": user.role,
            "customer_id": user.customer_id
        })
        return token

@pytest.fixture(scope="module")
async def system_admin_headers(system_admin_token: str) -> dict:
    return {"Authorization": f"Bearer {system_admin_token}"}
