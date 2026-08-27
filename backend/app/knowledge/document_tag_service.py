# ==============================================================================
# BLOCK COMMENT: DOMAIN-AGNOSTIC CENTRAL TAXONOMY & DOCUMENT TAG SERVICE
# Module: app/knowledge/document_tag_service.py
# Purpose:
#   1. Domain-Agnostic Generic Tag Extraction:
#      Dynamically crawls any structured/unstructured metadata JSON (Legal, Medical,
#      Financial, Insurance, Government, Technical) without domain-specific hardcoding.
#   2. Standardized DD-Mon-YYYY Timeline Normalization:
#      Automatically detects and normalizes all dates and 4-digit years.
#   3. Central Master Taxonomy (`taxonomy_terms`) & Junction Mapping (`document_tag_mappings`):
#      Self-learning canonical dictionary + lightweight foreign key mappings (3NF).
#   4. Sub-Millisecond 2-Tier Filter Acceleration:
#      Phonetic + Normalized Exact Tag Index Seek -> Instant candidate document ID resolution.
# ==============================================================================

import re
import uuid
from typing import Dict, Any, List, Optional, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_, and_, func, cast, String

from app.models.db_models import (
    TaxonomyTermDB,
    DocumentTagMappingDB,
    KnowledgeDocumentDB,
)
from app.knowledge.typed_metadata_matcher import (
    metaphone,
    soundex,
    nysiis,
)
import structlog

logger = structlog.get_logger(__name__)


# ==============================================================================
# BLOCK COMMENT: STANDARDIZED DATE & YEAR NORMALIZATION (DD-Mon-YYYY)
# ==============================================================================

MONTH_MAP = {
    "jan": "Jan", "january": "Jan",
    "feb": "Feb", "february": "Feb",
    "mar": "Mar", "march": "Mar",
    "apr": "Apr", "april": "Apr",
    "may": "May",
    "jun": "Jun", "june": "Jun",
    "jul": "Jul", "july": "Jul",
    "aug": "Aug", "august": "Aug",
    "sep": "Sep", "sept": "Sep", "september": "Sep",
    "oct": "Oct", "october": "Oct",
    "nov": "Nov", "november": "Nov",
    "dec": "Dec", "december": "Dec",
}


def normalize_standard_date(raw_date: Any) -> Optional[str]:
    """
    Standardizes any date string into canonical DD-Mon-YYYY format (e.g. '31-Dec-2016', '05-Nov-2012').
    Corrects issues like '31st December 2016', '2016-12-31', '31/12/2016', 'Dec 31, 2016'.
    """
    if not raw_date:
        return None
    s = str(raw_date).strip()
    if not s or s.lower() in ("null", "none", "unknown", "n/a"):
        return None

    # Remove ordinal suffixes: 31st -> 31, 1st -> 1, 2nd -> 2, 3rd -> 3, 4th -> 4
    s_clean = re.sub(r"(\d+)(?:st|nd|rd|th)", r"\1", s, flags=re.IGNORECASE)
    s_clean = s_clean.replace(",", " ")
    s_clean = re.sub(r"\s+", " ", s_clean).strip()

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    # Pattern 1: ISO format YYYY-MM-DD, YYYY/MM/DD, or YYYY.MM.DD
    m_iso = re.match(r"^(\d{4})[-/. ](\d{1,2})[-/. ](\d{1,2})", s_clean)
    if m_iso:
        yr, mo_num, day = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if 1 <= mo_num <= 12 and 1 <= day <= 31:
            return f"{day:02d}-{month_names[mo_num - 1]}-{yr}"

    # Pattern 2: DD-MM-YYYY, DD/MM/YYYY, or DD.MM.YYYY
    m_dmy = re.match(r"^(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{4})", s_clean)
    if m_dmy:
        day, mo_num, yr = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        if 1 <= mo_num <= 12 and 1 <= day <= 31:
            return f"{day:02d}-{month_names[mo_num - 1]}-{yr}"

    # Pattern 3: DD Month YYYY (e.g. 31 December 2016, 5 Nov 2012, 31-Jul-2018, 31.July.2018)
    m_text = re.match(r"^(\d{1,2})\s*[-/. ]\s*([a-zA-Z]+)\s*[-/. ]\s*(\d{4})", s_clean)
    if m_text:
        day = int(m_text.group(1))
        mo_str = m_text.group(2).lower()
        yr = int(m_text.group(3))
        canon_mo = MONTH_MAP.get(mo_str) or MONTH_MAP.get(mo_str[:3])
        if canon_mo and 1 <= day <= 31:
            return f"{day:02d}-{canon_mo}-{yr}"

    # Pattern 4: Month DD YYYY (e.g. December 31 2016)
    m_text2 = re.match(r"^([a-zA-Z]+)\s*[-/. ]\s*(\d{1,2})\s*[-/. ]\s*(\d{4})", s_clean)
    if m_text2:
        mo_str = m_text2.group(1).lower()
        day = int(m_text2.group(2))
        yr = int(m_text2.group(3))
        canon_mo = MONTH_MAP.get(mo_str) or MONTH_MAP.get(mo_str[:3])
        if canon_mo and 1 <= day <= 31:
            return f"{day:02d}-{canon_mo}-{yr}"

    # Fallback: find 4 digit year and preserve if valid
    m_yr = re.search(r"\b(19\d{2}|20\d{2})\b", s)
    if m_yr and len(s) <= 25:
        return s[:25]
    return None


def extract_standard_year(raw_val: Any) -> Optional[str]:
    """
    Extracts a clean 4-digit year (e.g. '2016') and rejects day fragments like '31st'.
    """
    if not raw_val:
        return None
    s = str(raw_val).strip()
    m_yr = re.search(r"\b(19\d{2}|20\d{2})\b", s)
    if m_yr:
        return m_yr.group(1)
    return None


from app.knowledge.legal_sot import canonicalize_disposition


def normalize_tag_text(text: str) -> str:
    """Normalize tag text by lowercasing, stripping honorifics/prefixes and excess whitespace."""
    if not text:
        return ""
    cleaned = text.lower().strip()
    prefix_pattern = re.compile(r"^(?:hon'ble|justice|mr|mrs|ms|dr|judge|section|sec|article|art)[\.\s]+", re.IGNORECASE)
    while True:
        new_cleaned = prefix_pattern.sub("", cleaned).strip()
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ==============================================================================
# BLOCK COMMENT: DOMAIN-AGNOSTIC RECURSIVE METADATA TAG EXTRACTOR
# ==============================================================================

def extract_generic_tags(metadata: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Domain-Agnostic Tag Extractor:
    Recursively inspects any arbitrary metadata JSON object (Legal, Healthcare, Finance, Policy, General)
    and extracts clean (category, value) tag tuples.
    Automatically identifies date/year strings and normalizes them to DD-Mon-YYYY.
    Ignores huge text paragraphs (>250 chars) or raw binary chunks.
    """
    tags: List[Tuple[str, str]] = []

    def _process_item(key: str, val: Any, depth: int = 0):
        if depth > 4 or val is None:
            return

        clean_key = str(key).lower().strip().replace(" ", "_")
        from app.knowledge.domain_extractor import FIELD_CANONICAL_ALIASES
        clean_key = FIELD_CANONICAL_ALIASES.get(clean_key) or clean_key

        # Skip huge text blobs or internal embedding arrays
        if clean_key in (
            "text", "content", "raw_content", "full_text", "summary",
            "executive_case_summary", "arguments", "findings", "reasoning",
            "page_content", "embedding", "vectors", "tokens",
            "procedural_history", "facts", "background", "holding", "ratio_decidendi"
        ):
            return

        # 1. String values
        if isinstance(val, str):
            s = val.strip()
            if not s or len(s) > 200 or len(s.split()) > 15:  # Skip empty or giant text paragraphs
                return
            
            # Check for date / timeline patterns in key or value
            if any(d_kw in clean_key for d_kw in ("date", "dob", "created", "issued", "filed", "hearing", "trial", "decision", "judgment")):
                norm_date = normalize_standard_date(s)
                if norm_date:
                    tags.append((clean_key, norm_date))
                    yr = extract_standard_year(norm_date)
                    if yr:
                        tags.append(("year", yr))
                    return
            
            if clean_key == "year" or "year" in clean_key:
                yr = extract_standard_year(s)
                if yr:
                    tags.append(("year", yr))
                    return

            # Check for disposition / status
            if clean_key in ("final_decision", "disposition", "outcome", "status"):
                disp = canonicalize_disposition(s)
                tags.append((clean_key, disp or s))
                return

            tags.append((clean_key, s))

        # 2. Numeric values
        elif isinstance(val, (int, float)):
            tags.append((clean_key, str(val)))

        # 3. List of values
        elif isinstance(val, list):
            for item in val:
                _process_item(clean_key.rstrip("s"), item, depth + 1)

        # 4. Nested Dictionary
        elif isinstance(val, dict):
            for sub_k, sub_v in val.items():
                _process_item(f"{sub_k}", sub_v, depth + 1)

    # Search extracted fields or top-level metadata
    search_root = metadata.get("extracted_fields") or metadata.get("domain_info", {}).get("extracted_fields") or metadata
    for k, v in search_root.items():
        _process_item(k, v, 0)

    # Also capture custom top-level tags
    if "tags" in metadata and isinstance(metadata["tags"], list):
        for t in metadata["tags"]:
            if isinstance(t, str) and t.strip():
                tags.append(("user_tag", t.strip()))

    return tags


# ==============================================================================
# BLOCK COMMENT: CENTRAL TAXONOMY REGISTRY & SYNC SERVICE
# ==============================================================================

async def upsert_taxonomy_term(
    db: AsyncSession,
    category: str,
    raw_value: str,
    customer_id: Optional[str] = None,
    alias: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Self-learning Central Taxonomy Registry:
    Finds or creates a canonical taxonomy term, updates aliases and usage count.
    Returns (term_id, canonical_name).
    """
    if not raw_value or not str(raw_value).strip():
        return None, None

    val_str = str(raw_value).strip()
    if len(val_str) > 120 or len(val_str.split()) > 10:
        # Long narrative sentences are not master taxonomy terms
        return None, val_str[:250]

    norm_val = normalize_tag_text(val_str)
    if not norm_val or len(norm_val) < 2:
        return None, val_str

    m_code = (metaphone(norm_val) or "")[:50] or None
    s_code = (soundex(norm_val) or "")[:20] or None
    n_code = (nysiis(norm_val) or "")[:50] or None

    match_conditions = [
        TaxonomyTermDB.canonical_normalized == norm_val,
        TaxonomyTermDB.canonical_name == val_str,
    ]
    if m_code:
        match_conditions.append(TaxonomyTermDB.metaphone_code == m_code)
    if s_code:
        match_conditions.append(TaxonomyTermDB.soundex_code == s_code)

    where_conditions = [
        TaxonomyTermDB.category == category,
        or_(*match_conditions),
    ]
    if customer_id:
        where_conditions.append(
            or_(
                TaxonomyTermDB.customer_id == str(customer_id),
                TaxonomyTermDB.customer_id.is_(None),
            )
        )
    else:
        where_conditions.append(TaxonomyTermDB.customer_id.is_(None))

    stmt = select(TaxonomyTermDB).where(and_(*where_conditions)).limit(1)

    try:
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.usage_count = (existing.usage_count or 1) + 1
            aliases = list(existing.aliases_json or [])
            candidate_alias = (alias or val_str).lower().strip()
            if candidate_alias and candidate_alias != existing.canonical_normalized and candidate_alias not in aliases:
                aliases.append(candidate_alias)
                existing.aliases_json = aliases
            return existing.id, existing.canonical_name

        term_id = str(uuid.uuid4())
        aliases_init = []
        if alias and alias.lower().strip() != norm_val:
            aliases_init.append(alias.lower().strip())

        new_term = TaxonomyTermDB(
            id=term_id,
            customer_id=str(customer_id) if customer_id else None,
            category=category,
            canonical_name=val_str[:250],
            canonical_normalized=norm_val[:250],
            aliases_json=aliases_init,
            soundex_code=s_code,
            metaphone_code=m_code,
            nysiis_code=n_code,
            usage_count=1,
            is_auto_discovered=True,
            is_verified=False,
        )
        db.add(new_term)
        await db.flush()
        return term_id, val_str
    except Exception as e:
        logger.debug("upsert_taxonomy_term_skipped", category=category, val=val_str, error=str(e))
        return None, val_str


async def sync_document_tags(
    db: AsyncSession,
    document_id: str,
    customer_id: str,
    knowledge_base_id: str,
    metadata: Dict[str, Any],
    is_inferred: bool = True,
) -> int:
    """
    Domain-Agnostic Tag Synchronizer:
    Dynamically extracts tags from metadata, resolves central taxonomy terms,
    and updates junction mappings in DocumentTagMappingDB.
    Uses two-pass resolution with db.flush() for transactional integrity.
    """
    if not metadata or not isinstance(metadata, dict):
        return 0

    tags_to_process = extract_generic_tags(metadata)
    if not tags_to_process:
        return 0

    try:
        # Pass 1: Upsert all central taxonomy terms first
        resolved_terms: List[Tuple[str, str, str]] = [] # (tag_type, term_id, canon_name)
        for tag_type, tag_val in tags_to_process:
            try:
                term_id, canon_name = await upsert_taxonomy_term(
                    db=db,
                    category=tag_type,
                    raw_value=tag_val,
                    customer_id=str(customer_id) if customer_id else None,
                )
                if term_id:
                    resolved_terms.append((tag_type, term_id, canon_name or tag_val[:250]))
                else:
                    # Fallback: create a master taxonomy term so tag_id is never null
                    norm_v = normalize_tag_text(tag_val) or tag_val.lower().strip()
                    fb_term_id = str(uuid.uuid4())
                    fb_term = TaxonomyTermDB(
                        id=fb_term_id,
                        customer_id=str(customer_id) if customer_id else None,
                        category=tag_type,
                        canonical_name=tag_val[:250],
                        canonical_normalized=norm_v[:250],
                        usage_count=1,
                    )
                    db.add(fb_term)
                    resolved_terms.append((tag_type, fb_term_id, tag_val[:250]))
            except Exception as tax_err:
                logger.debug("taxonomy_resolution_skipped", tag_val=tag_val, error=str(tax_err))

        # Flush all central terms so their primary keys exist in DB
        await db.flush()

        # Pass 2: Delete existing mappings for document and insert fresh junction rows
        del_stmt = delete(DocumentTagMappingDB).where(
            DocumentTagMappingDB.customer_id == str(customer_id),
            DocumentTagMappingDB.document_id == str(document_id),
        )
        await db.execute(del_stmt)

        inserted_count = 0
        for tag_type, term_id, canon_name in resolved_terms:
            if not term_id:
                continue
            try:
                mapping = DocumentTagMappingDB(
                    id=str(uuid.uuid4()),
                    customer_id=str(customer_id),
                    document_id=str(document_id),
                    knowledge_base_id=str(knowledge_base_id),
                    tag_id=term_id,
                    tag_type=tag_type,
                    tag_value=canon_name,
                    is_inferred=is_inferred if tag_type != "user_tag" else False,
                )
                db.add(mapping)
                inserted_count += 1
            except Exception as map_err:
                logger.debug("mapping_insert_skipped", tag_type=tag_type, error=str(map_err))

        await db.flush()
        logger.info(
            "document_tags_synced",
            document_id=str(document_id),
            tenant_id=str(customer_id),
            mappings_count=inserted_count,
        )
        return inserted_count
    except Exception as e:
        logger.warning(
            "sync_document_tags_error",
            document_id=str(document_id),
            error=str(e),
        )
        return 0


async def query_candidate_document_ids(
    db: AsyncSession,
    customer_id: str,
    filters: Dict[str, Any],
    knowledge_base_id: Optional[str] = None,
) -> Set[str]:
    """
    Executes fast 2-step indexed SQL query:
    1. Resolves matching tag IDs from central TaxonomyTermDB using Exact + Phonetic logic.
    2. Looks up candidate document IDs from DocumentTagMappingDB.
    """
    if not filters:
        return set()

    matching_tag_ids: Set[str] = set()

    for f_key, f_val in filters.items():
        if not f_val:
            continue
        val_str = str(f_val).strip()
        norm_val = normalize_tag_text(val_str)
        m_code = metaphone(norm_val) or None
        s_code = soundex(norm_val) or None

        key_lower = f_key.lower()
        tag_type_candidates = [key_lower]
        if key_lower in ("judge", "coram", "bench"):
            tag_type_candidates = ["judge", "coram", "bench"]
        elif key_lower in ("section", "statute", "article", "provision", "sections_or_articles_involved"):
            tag_type_candidates = ["section", "statute", "article", "provision", "sections_or_articles_involved"]
        elif key_lower in ("court", "jurisdiction"):
            tag_type_candidates = ["court", "jurisdiction"]
        elif key_lower in ("disposition", "status", "outcome", "final_decision"):
            tag_type_candidates = ["disposition", "status", "outcome", "final_decision"]

        match_conds = [
            TaxonomyTermDB.canonical_normalized == norm_val,
            TaxonomyTermDB.canonical_name.ilike(f"%{norm_val}%"),
            cast(TaxonomyTermDB.aliases_json, String).ilike(f"%{norm_val}%"),
        ]
        if m_code:
            match_conds.append(TaxonomyTermDB.metaphone_code == m_code)
        if s_code:
            match_conds.append(TaxonomyTermDB.soundex_code == s_code)

        tax_stmt = select(TaxonomyTermDB.id).where(
            TaxonomyTermDB.category.in_(tag_type_candidates),
            or_(*match_conds),
            or_(
                TaxonomyTermDB.customer_id == str(customer_id),
                TaxonomyTermDB.customer_id.is_(None),
            ),
        )
        tax_res = await db.execute(tax_stmt)
        for row in tax_res.all():
            matching_tag_ids.add(str(row[0]))

    if not matching_tag_ids:
        return set()

    where_clauses = [
        or_(
            DocumentTagMappingDB.customer_id == str(customer_id),
            DocumentTagMappingDB.customer_id == customer_id,
        ),
        DocumentTagMappingDB.tag_id.in_(list(matching_tag_ids)),
    ]
    if knowledge_base_id:
        where_clauses.append(DocumentTagMappingDB.knowledge_base_id == str(knowledge_base_id))

    stmt = (
        select(DocumentTagMappingDB.document_id)
        .where(*where_clauses)
        .distinct()
        .limit(100)
    )

    res = await db.execute(stmt)
    matched_ids = {str(row[0]) for row in res.all()}
    return matched_ids


async def suggest_taxonomy_terms(
    db: AsyncSession,
    query_str: str,
    customer_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """
    Returns auto-complete taxonomy suggestions across categories (Courts, Statutes, Judges, Dispositions)
    ordered by frequency/usage_count.
    """
    if not query_str or not query_str.strip():
        return []

    q_clean = normalize_tag_text(query_str)
    m_code = metaphone(q_clean) or None

    conds = [
        TaxonomyTermDB.canonical_normalized.ilike(f"%{q_clean}%"),
        TaxonomyTermDB.canonical_name.ilike(f"%{query_str}%"),
        cast(TaxonomyTermDB.aliases_json, String).ilike(f"%{q_clean}%"),
    ]
    if m_code:
        conds.append(TaxonomyTermDB.metaphone_code == m_code)

    where_conditions = [
        or_(*conds),
        or_(
            TaxonomyTermDB.customer_id == str(customer_id) if customer_id else False,
            TaxonomyTermDB.customer_id.is_(None),
        ),
    ]
    if category:
        where_conditions.append(TaxonomyTermDB.category == category)

    stmt = (
        select(TaxonomyTermDB)
        .where(*where_conditions)
        .order_by(TaxonomyTermDB.usage_count.desc())
        .limit(limit)
    )

    res = await db.execute(stmt)
    records = res.scalars().all()

    suggestions = []
    for term in records:
        suggestions.append({
            "id": term.id,
            "category": term.category,
            "canonical_name": term.canonical_name,
            "code": term.code,
            "usage_count": term.usage_count,
            "is_auto_discovered": term.is_auto_discovered,
        })
    return suggestions


async def get_document_tags(
    db: AsyncSession,
    customer_id: str,
    document_id: str,
) -> List[Dict[str, Any]]:
    """
    Fetches the authoritative list of tags for a single document from document_tag_mappings (SOT).
    """
    stmt = (
        select(DocumentTagMappingDB)
        .where(
            DocumentTagMappingDB.customer_id == str(customer_id),
            DocumentTagMappingDB.document_id == str(document_id),
        )
        .order_by(DocumentTagMappingDB.tag_type, DocumentTagMappingDB.created_at)
    )
    res = await db.execute(stmt)
    mappings = res.scalars().all()
    return [
        {
            "id": m.id,
            "tag_id": m.tag_id,
            "type": m.tag_type,
            "value": m.tag_value,
            "is_inferred": m.is_inferred,
        }
        for m in mappings
    ]


async def batch_get_document_tags(
    db: AsyncSession,
    customer_id: str,
    document_ids: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Batch fetches authoritative tags for multiple documents in a single indexed query.
    Returns {document_id: [tag_dict, ...]}.
    """
    if not document_ids:
        return {}

    stmt = (
        select(DocumentTagMappingDB)
        .where(
            DocumentTagMappingDB.customer_id == str(customer_id),
            DocumentTagMappingDB.document_id.in_(document_ids),
        )
        .order_by(DocumentTagMappingDB.document_id, DocumentTagMappingDB.tag_type)
    )
    res = await db.execute(stmt)
    mappings = res.scalars().all()

    result: Dict[str, List[Dict[str, Any]]] = {doc_id: [] for doc_id in document_ids}
    for m in mappings:
        if m.document_id in result:
            result[m.document_id].append({
                "id": m.id,
                "tag_id": m.tag_id,
                "type": m.tag_type,
                "value": m.tag_value,
                "is_inferred": m.is_inferred,
            })
    return result


async def set_document_tags(
    db: AsyncSession,
    customer_id: str,
    knowledge_base_id: str,
    document_id: str,
    tags: List[Any],
    is_inferred: bool = False,
) -> int:
    """
    Authoritative method to update document tags directly in document_tag_mappings (SOT)
    without needing to read or serialize the heavy metadata_json blob.
    """
    # Delete existing mappings for document
    del_stmt = delete(DocumentTagMappingDB).where(
        DocumentTagMappingDB.customer_id == str(customer_id),
        DocumentTagMappingDB.document_id == str(document_id),
    )
    await db.execute(del_stmt)

    if not tags:
        await db.flush()
        return 0

    inserted = 0
    for item in tags:
        if isinstance(item, dict):
            tag_type = item.get("type") or item.get("category") or "user_tag"
            tag_val = item.get("value") or item.get("name") or item.get("tag") or ""
        else:
            tag_type = "user_tag"
            tag_val = str(item).strip()

        if not tag_val or not tag_val.strip():
            continue

        tag_val_clean = tag_val.strip()
        term_id, canon_name = await upsert_taxonomy_term(
            db=db,
            category=tag_type,
            raw_value=tag_val_clean,
            customer_id=str(customer_id),
        )
        if not term_id:
            fb_term_id = str(uuid.uuid4())
            fb_term = TaxonomyTermDB(
                id=fb_term_id,
                customer_id=str(customer_id),
                category=tag_type,
                canonical_name=tag_val_clean[:250],
                canonical_normalized=tag_val_clean.lower()[:250],
                usage_count=1,
            )
            db.add(fb_term)
            term_id = fb_term_id

        mapping = DocumentTagMappingDB(
            id=str(uuid.uuid4()),
            customer_id=str(customer_id),
            document_id=str(document_id),
            knowledge_base_id=str(knowledge_base_id),
            tag_id=term_id,
            tag_type=tag_type,
            tag_value=canon_name or tag_val_clean[:250],
            is_inferred=is_inferred,
        )
        db.add(mapping)
        inserted += 1

    await db.flush()
    return inserted
