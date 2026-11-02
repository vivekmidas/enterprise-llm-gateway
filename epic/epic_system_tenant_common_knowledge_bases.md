# EPIC: System-Level & Domain-Common Knowledge Bases (Cross-Tenant Shared Law Repository)

## 1. Problem Statement
Tenants within a specific domain (e.g., Legal) require access to shared canonical repositories (such as the Constitution, IPC/BNS, CrPC/BNSS, Evidence Act/BSA, Central Statutes, and Tax Codes). Currently:
1. Knowledge Bases and Documents are strictly partitioned by `customer_id`. Every tenant must re-upload and re-index the exact same legal statutes.
2. Duplicated storage, Qdrant vectors, and token extraction waste system resources.
3. Users lack unified search across their private tenant cases and universal domain statutes.

## 2. Objective
Introduce **System-Level Knowledge Bases (Domain Repositories)**:
1. **Single Source of Truth**: Managed solely by System Admin (e.g. all Indian laws, BNS sections, CrPC to BNS concordance tables in 1 KB).
2. **Cross-Tenant Access**: Read-only access for all users/tenants belonging to or querying that domain.
3. **Unified Retrieval & Search**: Default auto-merging of domain statutes alongside tenant case documents with clear origin badges.
4. **Immutability for Tenants**: Tenant admins and standard users cannot edit, modify, reprocess, or delete system-level KBs.

---

## 3. Architecture & Data Model

### 3.1 Database Changes
- **`knowledge_bases` table (`KnowledgeBaseDB`)**:
  - `scope`: `VARCHAR(50)` default `'TENANT'` (`'SYSTEM'` or `'TENANT'`).
  - `is_system`: `BOOLEAN` default `FALSE`, indexed.
  - `customer_id`: Modified to `nullable=True` (or system ID `'0'`).
  - `domain_id`: Foreign key to `domain_schemas.id` (links system KB directly to domain, e.g. "legal").
- **`knowledge_documents` table (`KnowledgeDocumentDB`)**:
  - `is_system`: `BOOLEAN` default `FALSE`, indexed.
  - `customer_id`: Modified to `nullable=True`.
- **`knowledge_collections` table (`KnowledgeCollectionDB`)**:
  - `customer_id`: Modified to `nullable=True`.
- **`knowledge_chunks` table (`KnowledgeChunkDB`)**:
  - `is_system`: `BOOLEAN` default `FALSE`, indexed.
  - `customer_id`: Modified to `nullable=True`.
- **`llm_profiles` table (`LLMProfileDB`)**:
  - `is_system`: `BOOLEAN` default `FALSE`, indexed.
  - `scope`: `VARCHAR(50)` default `'TENANT'` (`'SYSTEM'` or `'TENANT'`).
  - `customer_id`: Modified to `nullable=True`.

### 3.2 System LLM Profile Resolution
1. System Admin creates/assigns a System LLM Profile (`customer_id=NULL`, `is_system=True`) or links default preset.
2. When creating a System KB, the system profile defines the embedding model (e.g. `nomic-embed-text` 768d / `bge-m3`) and vector dimension.
3. Document ingestion into System KB executes under the System Profile.

### 3.3 Search & Merged Retrieval (Tri-Path Hybrid)
1. **Scope Expansion**:
   - `KnowledgeDocumentDB.customer_id == user_tenant_id OR KnowledgeDocumentDB.is_system == True` (filtered by active `domain_id`).
2. **Vector & Chunk Search**:
   - Qdrant queries executed against tenant collection(s) AND domain system collection(s).
3. **Candidate Synthesis & Attribution**:
   - Results from System KBs marked with `is_system: true`, `source_type: "domain_law"`.
   - Distinct display in UI: "System Law / Domain Repository" pill.

---

## 4. UI / UX Design & Wireframes

### 4.1 Knowledge Base Management (`/admin/knowledge`)
```
+---------------------------------------------------------------------------------------------------+
| Knowledge Bases                                                    [+ New Knowledge Base]         |
| Filter: [ All (5) ] [ Tenant KBs (3) ] [ System KBs (2) ]                                         |
+---------------------------------------------------------------------------------------------------+
| Name                     Domain      Scope       Docs    Embed Model    Updated       Actions     |
+---------------------------------------------------------------------------------------------------+
| Indian Penal Code & BNS  Legal       [ System ]  48      nomic-embed    2026-09-04    [View]      |
| (Read-only for tenants)                                                                           |
| Corporate Contracts      Corporate   [ Tenant ]  12      bge-m3         2026-09-02    [Edit][Del] |
| FIR & Charge-sheets      Legal       [ Tenant ]  35      nomic-embed    2026-09-01    [Edit][Del] |
+---------------------------------------------------------------------------------------------------+
```

### 4.2 Domain Editor Modal (`/admin/domains`) -> "Knowledge Bases" Tab
```
+---------------------------------------------------------------------------------------------------+
| Domain: Legal AI Platform                                                                    [X]  |
| [ General ] [ Schema Fields ] [ Prompts ] [ Knowledge Bases ] [ Advanced ]                        |
+---------------------------------------------------------------------------------------------------+
| Linked Domain Knowledge Bases                                      [+ Add System KB to Domain]    |
| - Indian Penal Code & Bharatiya Nyaya Sanhita (System KB)           Docs: 48   Status: Active     |
| - Code of Criminal Procedure & BNSS Concordance (System KB)        Docs: 22   Status: Active     |
+---------------------------------------------------------------------------------------------------+
```

### 4.3 Search & Research UI (`/legal-research` / `/search`)
```
+---------------------------------------------------------------------------------------------------+
| Search Query: [ Section 302 IPC equivalent in BNS                                   ] [ Search ]  |
| Options: [v] Include System Laws & Statutes (BNS / CrPC / IPC)                                     |
+---------------------------------------------------------------------------------------------------+
| Found 4 matching sources:                                                                         |
| 1. [ SYSTEM LAW ] Bharatiya Nyaya Sanhita - Section 103 (Punishment for Murder) (Relevance: 0.96) |
|    Concordance: Replaces IPC Section 302. Death or imprisonment for life...                       |
| 2. [ FIR #204/2026 ] State vs Ramesh Kumar (Tenant Case File) (Relevance: 0.84)                   |
|    Charged under BNS 103 / IPC 302...                                                             |
+---------------------------------------------------------------------------------------------------+
```

---

## 5. Security & RBAC Guardrails
1. **Creation/Edit/Delete Guard**:
   - Only users with `role == 'system_admin'` can create, edit, delete, or upload to KBs with `is_system == True`.
   - `PUT /api/knowledge/bases/{id}`, `DELETE /api/knowledge/bases/{id}`, and document ingest reject non-system admins with `403 Forbidden`.
2. **Tenant Isolation**:
   - Tenant documents are NEVER exposed to other tenants.
   - Only system-flagged KBs (`is_system == True`) are readable across tenants within the matching domain.
   - Conversational assistant queries are strictly scoped to user tenant case documents and shared domain system laws.

---

## 6. User Stories

### STORY-SYSKB-04: Multilingual Voice Conversational Knowledge Assistant
- **Status**: In Progress
- **Summary**: Free-flowing conversational assistant in Legal Portal allowing users to query both system statutes (CrPC, IPC, BNS, BNSS, bare acts, concordance) and private tenant cases.
- **Key Capabilities**:
  1. **Free-Flowing Cross-Retrieval**: Unrestricted queries across system knowledge bases and tenant matter repositories.
  2. **Internal Case Link Redirection**: Assistant displays direct clickable links for detected tenant cases (e.g. `[Open Case Dossier: State v. Ramesh Kumar]`), navigating user directly to case tab on click.
  3. **Multilingual by Default**: English, Hindi, and regional languages supported with auto-detection and language preservation in responses.
  4. **Speech-to-Text (STT)**: Web Speech API voice capture enabling speech queries without keyboard input.
  5. **Inactivity Engine**: Client and server track user idle time; pings user after $n$ seconds of inactivity, and cleanly ends session with farewell after another $n$ seconds.
  6. **Future Reference Persistence**: All sessions, questions, answers, citations, and internal case references persisted in database for future search and compliance audit.
  7. **Window Controls**: Minimalist, uncluttered floating window with Minimize (`_`) and Close (`X`) buttons using relative responsive positioning.

---

## 7. Acceptance Criteria
- [ ] Database schema updated to support `is_system`, `scope`, and nullable `customer_id` for KBs, Collections, Documents, and LLM Profiles.
- [ ] System Admin can create a System Knowledge Base and attach it to a Domain.
- [ ] System Admin can upload documents (laws, bare acts, concordance tables) into the System KB.
- [ ] Tenant users can view the System KB in the KB list with a `System` pill badge, but cannot edit or delete it.
- [ ] Universal Search & Legal Search automatically include System KBs for the domain and merge results.
- [ ] Search results distinguish System Law citations from Tenant Case documents.
- [ ] STORY-SYSKB-04: Chatbot assistant supports free-flowing cross-KB queries (system statutes + tenant cases).
- [ ] STORY-SYSKB-04: Internal case citations contain direct redirection links to `/legal?tab=autopilot&matter=<id>`.
- [ ] STORY-SYSKB-04: STT voice transcription functional with live microphone pulse.
- [ ] STORY-SYSKB-04: Multilingual responses rendered accurately (English, Hindi).
- [ ] STORY-SYSKB-04: Inactivity timer triggers warning nudge at $n$ seconds and farewell close at $2n$ seconds.
- [ ] STORY-SYSKB-04: Window supports Minimize (`_`) and Close (`X`) without layout clutter.
- [ ] STORY-SYSKB-04: All Q&A pairs and sessions stored in database for future reference.
- [ ] Automated regression tests verify RBAC isolation, search merging, and assistant endpoints.

