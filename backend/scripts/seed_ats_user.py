#!/usr/bin/env python3
"""
Seed script: create the ATS demo user recruitment@midasminds.in

Usage:
    cd /Users/vivekjain/projects/enterprise-llm-gateway/backend
    python scripts/seed_ats_user.py

The script:
  1. Finds the MidasMinds customer record (by domain midasminds.in or name)
  2. Creates user recruitment@midasminds.in with role=admin and status=active
  3. Also creates a Knowledge Base named "ATS CV Pool" for the tenant
  4. Prints the KB id — use this in the ATS workflow node config
"""
import asyncio
import os
import sys

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security.hash import get_password_hash
from app.models.db_models import CustomerDB, UserDB, KnowledgeBaseDB

# ── Config ────────────────────────────────────────────────────────────────────
USER_EMAIL    = "recruitment@midasminds.in"
USER_NAME     = "Recruitment Admin"
USER_PASSWORD = "ATS@Demo2026!"      # Change after first login
USER_ROLE     = "admin"

CUSTOMER_DOMAIN = "midasminds.in"
CUSTOMER_NAME   = "MidasMinds"

KB_NAME         = "ATS CV Pool"
KB_DESCRIPTION  = "Tenant-scoped knowledge base for CV storage and semantic candidate retrieval."


async def main():
    async with AsyncSessionLocal() as db:
        # ── Find / create customer ────────────────────────────────────────────
        stmt = select(CustomerDB).where(
            (CustomerDB.domain == CUSTOMER_DOMAIN) | (CustomerDB.name == CUSTOMER_NAME)
        )
        result = await db.execute(stmt)
        customer = result.scalar_one_or_none()

        if not customer:
            print(f"[WARN] Customer '{CUSTOMER_NAME}' not found — creating one...")
            customer = CustomerDB(
                name=CUSTOMER_NAME,
                domain=CUSTOMER_DOMAIN,
                status="active",
            )
            db.add(customer)
            await db.flush()
            print(f"[OK]   Customer created: id={customer.id}")
        else:
            print(f"[OK]   Customer found:   id={customer.id}, name={customer.name}")

        # ── Check if user already exists ─────────────────────────────────────
        dup = await db.execute(select(UserDB).where(UserDB.email_id == USER_EMAIL))
        if dup.scalar_one_or_none():
            print(f"[SKIP] User '{USER_EMAIL}' already exists.")
        else:
            hashed = get_password_hash(USER_PASSWORD)
            user = UserDB(
                username=USER_EMAIL,
                email_id=USER_EMAIL,
                password=hashed,
                name=USER_NAME,
                role=USER_ROLE,
                customer_id=customer.id,
                status="active",
            )
            db.add(user)
            await db.flush()
            print(f"[OK]   User created:")
            print(f"         email    : {USER_EMAIL}")
            print(f"         password : {USER_PASSWORD}")
            print(f"         role     : {USER_ROLE}")
            print(f"         tenant   : {customer.id} ({customer.name})")

        # ── Create ATS Knowledge Base if not present ──────────────────────────
        kb_check = await db.execute(
            select(KnowledgeBaseDB).where(
                KnowledgeBaseDB.customer_id == customer.id,
                KnowledgeBaseDB.name == KB_NAME,
            )
        )
        kb = kb_check.scalar_one_or_none()

        if kb:
            print(f"[SKIP] Knowledge Base '{KB_NAME}' already exists: id={kb.id}")
        else:
            kb = KnowledgeBaseDB(
                name=KB_NAME,
                description=KB_DESCRIPTION,
                customer_id=customer.id,
                created_by=0,   # system seed
                status="active",
            )
            db.add(kb)
            await db.flush()
            print(f"[OK]   Knowledge Base created:")
            print(f"         name : {KB_NAME}")
            print(f"         id   : {kb.id}")

        await db.commit()

        print()
        print("━" * 60)
        print("ATS DEMO SETUP COMPLETE")
        print("━" * 60)
        print(f"  Login      : {USER_EMAIL}")
        print(f"  Password   : {USER_PASSWORD}")
        print(f"  Role       : {USER_ROLE}")
        print(f"  Tenant ID  : {customer.id}")
        print(f"  ATS KB ID  : {kb.id}   ← use in workflow node config")
        print()
        print("Next steps:")
        print("  1. Log in as recruitment@midasminds.in")
        print(f"  2. Open the ATS demo workflow in the builder")
        print(f"  3. Set knowledge_base_id = {kb.id} on the VectorDB Ingest node")
        print(f"  4. Set knowledge_base_ids = [{kb.id}] on the Candidate Search node")
        print("  5. Configure an LLM profile for the tenant")
        print(f"  6. Enable the workflow and POST to /webhooks/run/ats")
        print("━" * 60)


if __name__ == "__main__":
    asyncio.run(main())
