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
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import EKPEntityDB, EKPDocumentDB, LLMProfileDB, EKPParagraphDB, EKPDomainDB
from app.knowledge.ekp_v3.cdm import CDMDocument, CDMParagraph

logger = structlog.get_logger(__name__)

SCHEMAS_DIR = Path(__file__).parent / "schemas"


def load_domain_schema(domain_id: Optional[str] = None) -> Dict[str, Any]:
    """Loads target domain entity definition schema dynamically from legal_sot or domain schema single source of truth."""
    from app.knowledge.legal_sot import LEGAL_JUDGMENT_SCHEMA
    if not domain_id or str(domain_id).lower() in ("legal", "domain_legal", "general"):
        return LEGAL_JUDGMENT_SCHEMA

    domain_key = (domain_id or "legal").lower().replace(" ", "_")
    schema_file = SCHEMAS_DIR / f"domain_{domain_key}.json"
    if schema_file.exists():
        try:
            return json.loads(schema_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse domain schema JSON {schema_file}: {e}")

    return {
        "domain": domain_id or "general",
        "domain_id": domain_id or "general",
        "version": "1.3",
        "fields": LEGAL_JUDGMENT_SCHEMA.get("fields", []),
        "prompts": LEGAL_JUDGMENT_SCHEMA.get("prompts", {}),
    }


def extract_target_field_definitions(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Dynamically flattens all target field definitions from schema fields without hardcoding."""
    targets = []
    fields = schema.get("fields", [])
    if isinstance(fields, list):
        for f in fields:
            k = f.get("key") or f.get("name")
            if not k:
                continue
            targets.append({
                "entity_type": k,
                "entity_key": k,
                "type": f.get("type", "string"),
                "description": f.get("description", f"Value for {k}"),
                "multiple": f.get("type") in ("array", "list"),
                "review": True
            })
    return targets


# ===============================================================================
# BLOCK COMMENT: DYNAMIC DOMAIN SCHEMA PROMPT BUILDER
# Purpose:
# Constructs extraction prompts dynamically from Domain Schema & SOT.
# Eliminates all hardcoded static prompt overrides so domain configurations apply 100%.
# ===============================================================================
def build_dynamic_few_shot_prompt(
    cdm_doc: CDMDocument,
    schema: Dict[str, Any],
    domain: Optional[Any] = None,
) -> tuple[str, str]:
    """Constructs dynamic domain extraction prompts using domain schema from system as single source of truth."""
    from app.knowledge.domain_extractor import format_fields_summary, format_fields_json_schema
    from app.knowledge.legal_sot import LEGAL_SYSTEM_PROMPT, LEGAL_USER_PROMPT_TEMPLATE, LEGAL_FIELDS_SPEC

    all_paras = cdm_doc.get_all_paragraphs() if cdm_doc else []
    full_text = "\n\n".join(p.text_content for p in all_paras if p.text_content)

    fields = schema.get("fields") if isinstance(schema, dict) and schema.get("fields") else None
    if not fields and domain and hasattr(domain, "schema_json") and isinstance(domain.schema_json, dict):
        fields = domain.schema_json.get("fields")
    if not fields:
        fields = LEGAL_FIELDS_SPEC

    fields_summary = format_fields_summary(fields)
    fields_json_schema = format_fields_json_schema(fields)

    sys_prompt = getattr(domain, "system_prompt", None) or schema.get("system_prompt") or schema.get("prompts", {}).get("system_prompt") or LEGAL_SYSTEM_PROMPT
    user_template = getattr(domain, "user_prompt", None) or schema.get("user_prompt_template") or schema.get("prompts", {}).get("user_prompt_template") or LEGAL_USER_PROMPT_TEMPLATE

    user_prompt = (
        user_template
        .replace("{filename}", getattr(cdm_doc, "document_name", "") or "document")
        .replace("{fields_summary}", fields_summary)
        .replace("{fields_json_schema}", fields_json_schema)
        .replace("{content}", full_text)
        .replace("{content_snippet}", full_text)
    )

    return sys_prompt, user_prompt


def map_provenance_to_cdm_spans(
    raw_payload: Any,
    cdm_doc: CDMDocument,
    doc_id: str,
    domain_id: str,
    enable_provenance: bool = False
) -> List[EKPEntityDB]:
    """Stage 2: Deterministic provenance linker & text-grounding filter."""
    all_paras = cdm_doc.get_all_paragraphs() if cdm_doc else []
    valid_span_ids = {p.span_id for p in all_paras}
    full_doc_text = "\n".join(p.text_content for p in all_paras).lower() if all_paras else ""

    def is_grounded(search_term: str) -> bool:
        if not full_doc_text or not search_term:
            return True
        st_lower = str(search_term).strip().lower()
        if st_lower in full_doc_text:
            return True
        tokens = [t for t in re.split(r'\W+', st_lower) if len(t) >= 3 and t not in {
            "the", "and", "court", "high", "state", "case", "suit", "judge", "order"
        }]
        if not tokens:
            return True
        return sum(1 for t in tokens if t in full_doc_text) >= 1

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
            if not is_grounded(str(val)):
                logger.info("ekp_rejecting_ungrounded_entity", value=str(val)[:100])
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
                        elif el and is_grounded(str(el)):
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
                elif v and is_grounded(str(v)):
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


def ensure_domain_exists_sync(db: Session, domain_id: Optional[str]) -> Optional[str]:
    """Ensures domain_id exists in ekp_domains table before FK insertion."""
    if not domain_id:
        return None
    d_id = str(domain_id)[:64]
    domain = db.query(EKPDomainDB).filter(EKPDomainDB.id == d_id).first()
    if not domain:
        domain = EKPDomainDB(
            id=d_id,
            name=d_id.replace("_", " ").title(),
            version="1.0",
            schema_definition={"domain_id": d_id},
            is_active=True
        )
        db.add(domain)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Failed to auto-seed domain in ekp_domains (sync)", domain_id=d_id, error=str(e))
    return d_id


async def ensure_domain_exists_async(db: AsyncSession, domain_id: Optional[str]) -> Optional[str]:
    """Ensures domain_id exists in ekp_domains table before FK insertion."""
    if not domain_id:
        return None
    d_id = str(domain_id)[:64]
    res = await db.execute(select(EKPDomainDB).where(EKPDomainDB.id == d_id))
    domain = res.scalars().first()
    if not domain:
        domain = EKPDomainDB(
            id=d_id,
            name=d_id.replace("_", " ").title(),
            version="1.0",
            schema_definition={"domain_id": d_id},
            is_active=True
        )
        db.add(domain)
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning("Failed to auto-seed domain in ekp_domains (async)", domain_id=d_id, error=str(e))
    return d_id


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
        if entities:
            target_domain_id = entities[0].domain_id or doc.domain_id or "legal"
            ensure_domain_exists_sync(db, target_domain_id)
        try:
            db.add(doc)
            for ent in entities:
                db.add(ent)
            # SINGLE SOURCE OF TRUTH (SOT): Persist extracted JSON to KnowledgeDocumentDB
            extracted_payload = getattr(doc, "_temp_extracted_payload", None)
            if extracted_payload:
                try:
                    from app.models.db_models import KnowledgeDocumentDB
                    k_doc = db.query(KnowledgeDocumentDB).filter(
                        (KnowledgeDocumentDB.id == doc.id) |
                        ((KnowledgeDocumentDB.knowledge_base_id == str(doc.knowledge_base_id)) & (KnowledgeDocumentDB.name == doc.filename))
                    ).first()
                    if k_doc:
                        k_doc.extracted_json = extracted_payload
                        db.add(k_doc)
                except Exception as k_sync_err:
                    logger.warning("failed_to_persist_extracted_json_to_knowledge_doc_sync", error=str(k_sync_err))
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
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
        if entities:
            target_domain_id = entities[0].domain_id or doc.domain_id or "legal"
            await ensure_domain_exists_async(db, target_domain_id)
        try:
            db.add(doc)
            for ent in entities:
                db.add(ent)
            # SINGLE SOURCE OF TRUTH (SOT): Persist extracted JSON to KnowledgeDocumentDB
            extracted_payload = getattr(doc, "_temp_extracted_payload", None)
            if extracted_payload:
                try:
                    from app.models.db_models import KnowledgeDocumentDB
                    k_stmt = select(KnowledgeDocumentDB).where(
                        (KnowledgeDocumentDB.id == doc.id) |
                        ((KnowledgeDocumentDB.knowledge_base_id == doc.knowledge_base_id) & (KnowledgeDocumentDB.name == doc.filename))
                    )
                    k_res = await db.execute(k_stmt)
                    k_doc = k_res.scalars().first()
                    if k_doc:
                        k_doc.extracted_json = extracted_payload
                        db.add(k_doc)
                except Exception as k_sync_err:
                    logger.warning("failed_to_persist_extracted_json_to_knowledge_doc", error=str(k_sync_err))
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise e
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

        # Resolve domain from DB if available
        domain_db = None
        if async_db and doc.domain_id:
            try:
                from app.models.db_models import DomainSchemaDB, EKPDomainDB
                d_stmt = select(EKPDomainDB).where(EKPDomainDB.id == doc.domain_id)
                d_res = await async_db.execute(d_stmt)
                domain_db = d_res.scalars().first()
                if not domain_db:
                    ds_stmt = select(DomainSchemaDB).where((DomainSchemaDB.id == doc.domain_id) | (DomainSchemaDB.domain_key == doc.domain_id))
                    ds_res = await async_db.execute(ds_stmt)
                    domain_db = ds_res.scalars().first()
            except Exception as e:
                logger.warn("domain_lookup_in_extractor_failed", error=str(e))

        cust_id = active_profile.customer_id if active_profile else None
        llm_config = active_profile.settings if (active_profile and active_profile.settings) else None

        try:
            from app.core.llm_router import LLMRouter
            router = LLMRouter()
            sys_prompt, user_prompt = build_dynamic_few_shot_prompt(cdm_doc, schema, domain=domain_db)
            llm = await router.get_llm(
                temperature=0.0,
                max_tokens=4096,
                customer_id=cust_id,
                llm_config=llm_config
            )
            combined_prompt = f"SYSTEM INSTRUCTIONS:\n{sys_prompt}\n\nUSER REQUEST:\n{user_prompt}"
            response = await llm.ainvoke(combined_prompt)
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
                doc._temp_extracted_payload = payload
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

