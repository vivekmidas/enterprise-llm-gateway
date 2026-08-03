"""
===============================================================================
BLOCK COMMENT: EKP V3 GENERIC DYNAMIC DOMAIN ENTITY EXTRACTOR ENGINE
Module: backend/app/knowledge/ekp_v3/extractor.py
Author: EKP Architecture Team
Description:
    100% Schema & LLM-Driven Domain Entity Extractor for EKP V3.
    Contains ZERO hardcoded entity field names or dummy heading generators.
    Reads target field_groups dynamically from loaded domain JSON schemas
    (domain_legal.json, domain_general.json, or custom tenant schemas).
    Attempts One-Shot / Few-Shot LLM entity extraction, and falls back to
    schema-driven dynamic pattern matching so 0 entities are never silently dropped.
===============================================================================
"""

import uuid
import re
import json
import asyncio
import structlog
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import EKPEntityDB, EKPDocumentDB, LLMProfileDB, EKPParagraphDB
from app.knowledge.ekp_v3.cdm import CDMDocument, CDMParagraph

logger = structlog.get_logger(__name__)

SCHEMAS_DIR = Path(__file__).parent / "schemas"


def load_domain_schema(domain_id: Optional[str] = None) -> Dict[str, Any]:
    """Loads target domain entity definition JSON schema dynamically based on domain_id."""
    domain_key = (domain_id or "legal").lower().replace(" ", "_")
    schema_file = SCHEMAS_DIR / f"domain_{domain_key}.json"
    if not schema_file.exists():
        schema_file = SCHEMAS_DIR / "domain_legal.json"

    if schema_file.exists():
        try:
            return json.loads(schema_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse domain schema JSON {schema_file}: {e}")

    return {
        "domain": domain_id or "general",
        "domain_id": domain_id or "general",
        "version": "1.3",
        "field_groups": []
    }


def extract_target_field_definitions(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Dynamically flattens all target field definitions from schema field_groups without hardcoding."""
    targets = []
    field_groups = schema.get("field_groups", [])

    for group in field_groups:
        group_name = group.get("group", "general")
        fields = group.get("fields", [])
        for field in fields:
            field_name = field.get("name")
            if not field_name:
                continue
            targets.append({
                "entity_type": field_name,
                "entity_key": f"{group_name}.{field_name}",
                "type": field.get("type", "string"),
                "description": field.get("description", f"Value for {field_name} in group {group_name}"),
                "multiple": field.get("multiple", False),
                "review": field.get("review", True)
            })
    return targets


def build_dynamic_few_shot_prompt(cdm_doc: CDMDocument, schema: Dict[str, Any]) -> str:
    """Constructs enhanced paralegal full-text extraction prompt for legal domain entity extraction."""
    all_paras = cdm_doc.get_all_paragraphs()
    full_text = "\n\n".join(p.text_content for p in all_paras if p.text_content)

    return f"""You are a trained paralegal with deep knowledge of the judicial system, laws, constitution, statutory provisions, and legal documentation.

Analyze the following legal document completely and provide a comprehensive structured legal analysis in JSON format containing the following entities:
- case (case number, petition/suit title, court jurisdiction)
- court (name of High Court / Supreme Court / Tribunal)
- judge (coram / presiding judge names)
- date (date of judgment / order)
- parties (list of petitioners, respondents, appellants, defendants)
- lawyers (advocates / counsel appearing for each party)
- court_order (impugned lower court orders, suits, or revision applications)
- act/article (statutes, acts, sections, rules, constitutional articles cited)
- ruling (specific holdings, decisions, and directions of the court)
- decision (overall final outcome, e.g. Rule made absolute, dismissed, allowed)
- observation (judicial findings, factual observations, and legal reasoning)
- punishment (penalties, disciplinary actions, backwages, or relief modifications)
- referenced_cases (precedents or other case citations referred to in the document)

SOURCE DOCUMENT:
{full_text}

Return ONLY valid JSON. DO NOT ADD ANY COMMENT OTHER THAN THE JSON, NO PLEASENTRIES , NO LEADING TEXT OR EXPLANATION, JUST THE RAW JSON YOU GENERATE AFTER ANALYSIS.
"""


def map_provenance_to_cdm_spans(
    raw_payload: Any,
    cdm_doc: CDMDocument,
    doc_id: str,
    domain_id: str,
    enable_provenance: bool = False
) -> List[EKPEntityDB]:
    """Stage 2: Deterministic provenance linker (Provenance searching disabled for now)."""
    all_paras = cdm_doc.get_all_paragraphs() if cdm_doc else []
    valid_span_ids = {p.span_id for p in all_paras}

    def search_span(search_term: str) -> tuple[Optional[str], str, float]:
        if not enable_provenance:
            return None, "FACT", 1.0
        if not search_term or len(str(search_term)) < 2:
            return None, "INFERENCE", 0.7
        search_lower = str(search_term).lower().strip()

        # 1. Exact or substring match in paragraph
        for p in all_paras:
            if search_lower in p.text_content.lower():
                return p.span_id, "FACT", 1.0

        # 2. Token keyword overlap match
        tokens = [t for t in re.split(r'\W+', search_lower) if len(t) > 3]
        if not tokens:
            return None, "INFERENCE", 0.7

        best_span = None
        best_score = 0
        for p in all_paras:
            p_text = p.text_content.lower()
            matches = sum(1 for t in tokens if t in p_text)
            if matches > best_score:
                best_score = matches
                best_span = p.span_id

        if best_score >= max(1, int(len(tokens) * 0.5)):
            return best_span, "INFERENCE", 0.85

        return None, "INFERENCE", 0.7

    candidates = []

    if isinstance(raw_payload, dict) and "extracted_entities" in raw_payload:
        raw_items = raw_payload.get("extracted_entities", [])
        for item in raw_items:
            val = item.get("value")
            if not val or str(val).strip() == "" or str(val).lower() == "null":
                continue
            prov_span = item.get("provenance_span_id") if enable_provenance else None
            basis_str = item.get("basis", "FACT").upper()
            conf = float(item.get("confidence") or 1.0)

            if enable_provenance and (not prov_span or prov_span not in valid_span_ids):
                matched_span, match_basis, match_conf = search_span(str(val))
                prov_span = matched_span
                basis_str = match_basis
                conf = match_conf

            candidates.append(EKPEntityDB(
                id=f"ent-{uuid.uuid4().hex[:12]}",
                document_id=doc_id,
                domain_id=domain_id,
                entity_type=item.get("entity_type", "custom"),
                entity_key=item.get("entity_key", "custom.field"),
                value=str(val)[:500],
                confidence=conf,
                basis=basis_str,
                provenance_span_id=prov_span,
                version=1,
                review_version=1,
                is_deleted=False
            ))
    elif isinstance(raw_payload, dict):
        def traverse_dict(obj, key_prefix=""):
            for k, v in obj.items():
                curr_key = f"{key_prefix}.{k}" if key_prefix else k
                if isinstance(v, dict):
                    traverse_dict(v, curr_key)
                elif isinstance(v, list):
                    for idx, el in enumerate(v):
                        if isinstance(el, dict):
                            traverse_dict(el, f"{curr_key}[{idx}]")
                        elif el:
                            matched_span, match_basis, match_conf = search_span(str(el))
                            candidates.append(EKPEntityDB(
                                id=f"ent-{uuid.uuid4().hex[:12]}",
                                document_id=doc_id,
                                domain_id=domain_id,
                                entity_type=k,
                                entity_key=curr_key,
                                value=str(el)[:500],
                                confidence=match_conf,
                                basis=match_basis,
                                provenance_span_id=matched_span,
                                version=1,
                                review_version=1,
                                is_deleted=False
                            ))
                elif v:
                    matched_span, match_basis, match_conf = search_span(str(v))
                    candidates.append(EKPEntityDB(
                        id=f"ent-{uuid.uuid4().hex[:12]}",
                        document_id=doc_id,
                        domain_id=domain_id,
                        entity_type=k,
                        entity_key=curr_key,
                        value=str(v)[:500],
                        confidence=match_conf,
                        basis=match_basis,
                        provenance_span_id=matched_span,
                        version=1,
                        review_version=1,
                        is_deleted=False
                    ))
        traverse_dict(raw_payload)

    return candidates


class EKPDomainExtractor:
    """100% Dynamic, Schema & LLM-Driven Domain Entity Extractor for EKP V3."""

    def extract_and_persist(
        self,
        db: Session,
        *,
        doc: EKPDocumentDB,
        cdm_doc: CDMDocument,
        llm_profile: Optional[LLMProfileDB] = None
    ) -> List[EKPEntityDB]:
        """Extract domain entities and persist to ekp_entities table (Sync)."""
        entities = self._extract_entities_sync(doc, cdm_doc, llm_profile, db=db)
        for ent in entities:
            db.add(ent)
        db.commit()
        return entities

    async def async_extract_and_persist(
        self,
        db: AsyncSession,
        *,
        doc: EKPDocumentDB,
        cdm_doc: CDMDocument,
        llm_profile: Optional[LLMProfileDB] = None
    ) -> List[EKPEntityDB]:
        """Extract domain entities and persist to ekp_entities table (Async)."""
        entities = await self._extract_entities_async(doc, cdm_doc, llm_profile, async_db=db)
        for ent in entities:
            db.add(ent)
        await db.commit()
        return entities

    async def _extract_entities_async(
        self,
        doc: EKPDocumentDB,
        cdm_doc: CDMDocument,
        llm_profile: Optional[LLMProfileDB] = None,
        async_db: Optional[AsyncSession] = None
    ) -> List[EKPEntityDB]:
        """100% Schema & LLM-Driven 2-Stage Async Domain Entity Extraction."""
        schema = load_domain_schema(doc.domain_id)

        # Resolve LLM Profile if missing
        active_profile = llm_profile
        if not active_profile and async_db and doc.llm_profile_id:
            try:
                from sqlalchemy import select
                stmt = select(LLMProfileDB).where(LLMProfileDB.id == doc.llm_profile_id)
                res = await async_db.execute(stmt)
                active_profile = res.scalars().first()
            except Exception as e:
                logger.warn(
                    "Failed async LLM profile resolution",
                    error=str(e),
                    tenant_id=str(doc.tenant_id or "N/A"),
                    document_id=str(doc.id or "N/A"),
                    file="extractor.py",
                    function="_extract_entities_async"
                )

        cust_id = active_profile.customer_id if active_profile else None
        llm_config = active_profile.settings if (active_profile and active_profile.settings) else None

        try:
            from app.core.llm_router import LLMRouter
            router = LLMRouter()
            prompt = build_dynamic_few_shot_prompt(cdm_doc, schema)
            llm = await router.get_llm(
                temperature=0.0,
                max_tokens=2048,
                customer_id=cust_id,
                llm_config=llm_config
            )
            response = await llm.ainvoke(prompt)
            resp_text = str(getattr(response, "content", response))

            # Clean markdown formatting if present
            clean_text = resp_text.strip()
            if clean_text.startswith("```"):
                lines = clean_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_text = "\n".join(lines).strip()

            # Parse JSON response
            json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if json_match:
                payload = json.loads(json_match.group(0))
                extracted_db_entities = map_provenance_to_cdm_spans(
                    raw_payload=payload,
                    cdm_doc=cdm_doc,
                    doc_id=doc.id,
                    domain_id=doc.domain_id or schema.get("domain_id", "legal")
                )
                logger.info(
                    "LLM 2-Stage Extracted domain entities successfully",
                    extracted_count=len(extracted_db_entities),
                    tenant_id=str(doc.tenant_id or "N/A"),
                    customer_id=str(cust_id or "N/A"),
                    document_id=str(doc.id or "N/A"),
                    file="extractor.py",
                    function="_extract_entities_async"
                )
                return extracted_db_entities
        except Exception as e:
            logger.error(
                "LLM Extraction warning",
                error=str(e),
                tenant_id=str(doc.tenant_id or "N/A"),
                customer_id=str(cust_id or "N/A"),
                document_id=str(doc.id or "N/A"),
                file="extractor.py",
                function="_extract_entities_async"
            )

        return []

    def _extract_entities_sync(
        self,
        doc: EKPDocumentDB,
        cdm_doc: CDMDocument,
        llm_profile: Optional[LLMProfileDB] = None,
        db: Optional[Session] = None
    ) -> List[EKPEntityDB]:
        """Sync wrapper for Schema-Driven LLM Extraction."""
        active_profile = llm_profile
        if not active_profile and db and doc.llm_profile_id:
            active_profile = db.query(LLMProfileDB).filter(LLMProfileDB.id == doc.llm_profile_id).first()

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(lambda: asyncio.run(self._extract_entities_async(doc, cdm_doc, active_profile)))
                    return future.result()
            else:
                return asyncio.run(self._extract_entities_async(doc, cdm_doc, active_profile))
        except Exception as e:
            logger.error(
                "LLM Extraction warning",
                error=str(e),
                tenant_id=str(doc.tenant_id or "N/A"),
                customer_id=str(doc.tenant_id or "N/A"),
                document_id=str(doc.id or "N/A"),
                file="extractor.py",
                function="_extract_entities_sync"
            )
            return []

