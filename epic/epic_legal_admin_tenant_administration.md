# Epic: Legal Admin & Legal AI Platform Scope (Streamlined)

**Epic ID**: `EPIC-LEGAL-ADMIN-01`  
**Target Persona**: `legal_admin` (Law Firm Administrator / Managing Partner) & Firm Advocates/Paralegals  
**Scope Focus**: User Administration, Legacy Case Data Ingestion, Precedent & Case Search, AI Legal Advice Grounded in Case Data, IPC-to-BNS Statutory Bridge, Document Save & Export  
**Status**: Updated with Legacy Case Data Ingestion per User Direction  

---

## 1. Persona & System Core Statement

### 1.1 Persona Responsibilities
* **Tenant Legal Admin (`legal_admin`)**: 
  - Manage firm team members (Add User, Deactivate Account, Assign Role).
  - Manage tenant case knowledge base (Upload digital legacy case files, monitor parsing/embedding pipeline, delete/re-index files).
  - View seat usage indicator (Read-only total seats vs. active assigned users).
* **Firm Fee-Earners (`lawyer`, `paralegal`)**:
  - Search legal precedents, judgments, and tenant-ingested case papers.
  - Seek grounded AI advice based on case facts and precedent data.
  - Perform statutory cross-mapping (IPC/CrPC/IEA ↔ BNS/BNSS/BSA).
  - Save research and export reworked legal drafts (DOCX / PDF).

---

## 2. Core Functional Features (In-Scope)

```
===================================================================================
                   STREAMLINED LEGAL AI PLATFORM & ADMIN CONTROL
===================================================================================
 [1] User Management  │ [2] Legacy Case Data│ [3] Precedent & Case│ [4] AI Legal Advice
     & Seat Indicator │     Ingestion (Admin)│     Search Engine   │     (Case-Grounded)
 ─────────────────────┼─────────────────────┼───────────────────┼─────────────────
 • Add / Deactivate   │ • Upload Case Files │ • Precedent Search│ • Fact-Based QA
 • Role Assignment    │ • Auto Parse/Chunk  │ • Ingested Case   │ • Ratio Extract
 • Read-Only Seats    │ • Vector Embedding  │   Paper Search    │ • Source Citations
 • User List View     │ • Index Status View │ • Filter Court/Yr │ • Grounded Answers
 ─────────────────────┼─────────────────────┼───────────────────┼─────────────────
 [5] Statutory Cross- │ [6] Reworked Doc    │                   │ 
     Mapping (IPC↔BNS)│     Save & Export   │                   │ 
 ─────────────────────┼─────────────────────┼───────────────────┤ 
 • IPC → BNS Bridge   │ • Save Research     │                   │ 
 • CrPC → BNSS Bridge │ • Export DOCX / PDF │                   │ 
 • IEA → BSA Bridge   │ • Reworked Drafts   │                   │ 
===================================================================================
```

### Module 1: User Management & Seat Indicator (Legal Admin)
- **User Lifecycle**: Simple UI controls to "Add User", "Deactivate User", and select role (`Senior Advocate`, `Advocate`, `Paralegal`).
- **Read-Only Seat Counter**: Visual status badge showing assigned users vs. system-provisioned seat cap (e.g., `8 of 10 Seats Used`). License tier & seat caps are provisioned by System Admin.

### Module 2: Legacy Case Data Ingestion & Knowledge Management (Legal Admin)
- **Digital Case Upload**: Upload digital legacy case files (PDF, DOCX, TXT, court records).
- **Automated Pipeline**: System automatically parses text, chunks content semantically, generates vector embeddings, and stores them in tenant-isolated knowledge collection.
- **Index Management UI**: Legal Admin can view uploaded files, monitor processing status (`Queued` → `Parsing` → `Embedded` / `Failed`), and trigger re-index or deletion.

### Module 3: Precedent & Case Paper Search
- **Judgment Precedent Search**: Hybrid keyword & semantic search across Supreme Court and High Court precedents.
- **Tenant Case Paper Search**: Search ingested legacy case files uploaded by Legal Admin.
- **Structured Extracts**: Quick view of parties, bench, key issues, ratio decidendi, and verdict tags.

### Module 4: Grounded AI Legal Advice
- **Case Data Advice Engine**: Ask research questions grounded in ingested case data and precedent extracts with exact source citations.
- **Strict Grounding**: System answers strictly from retrieved case authorities without hallucinating invalid precedents.

### Module 5: Statutory Cross-Mapping (IPC ↔ BNS / BNSS / BSA)
- **IPC to BNS Conversion**: Map older Indian Penal Code (IPC) sections to corresponding Bharatiya Nyaya Sanhita (BNS) provisions.
- **CrPC & IEA Bridge**: Cross-reference Code of Criminal Procedure (CrPC) to BNSS and Indian Evidence Act (IEA) to BSA.

### Module 6: Reworked Document Save & Export
- **Save Research**: Save AI advice, citation lists, and research notes to personal/team saved briefs.
- **Document Exporter**: Export reworked briefs and research summaries into formatted Word (.docx) or PDF files.

---

## 3. UI Wireframes & Layout Breakdown

### 3.1 Streamlined Admin & User Hub

```
+---------------------------------------------------------------------------------------------------+
|  [LOGO] Legal AI Platform  | Firm: AZB & Partners | Seats Used: 8/10 | Role: Legal Admin           |
+---------------------------------------------------------------------------------------------------+
| NAV TABS              | MAIN PANEL                                                                |
|                       |                                                                           |
|  [ Precedent Search ] | LEGACY CASE DATA INGESTION (LEGAL ADMIN)                                  |
|  [ Case Search ]      | +-----------------------------------------------------------------------+ |
|  [ AI Legal Advice ]  | | [ Drag & Drop Legacy Case Files (PDF / DOCX) or Browse Files ]        | |
|  [ IPC ↔ BNS Bridge ] | +-----------------------------------------------------------------------+ |
|  [ Saved Briefs ]     | Action: [ Upload & Index Case Data ]                                      |
|  [ Case Ingestion ]   | +-----------------------------------------------------------------------+ |
|  [ User Management ]  | | Document Name      | Upload Date | Chunks | Status          | Action   | |
|                       | |--------------------|-------------|--------|-----------------|----------| |
|                       | | Alpha_v_State.pdf  | 08-Aug-2026 | 142    | [Embedded]      | [Delete] | |
|                       | | Beta_Property.docx | 08-Aug-2026 | 86     | [Parsing...]    | [Cancel] | |
|                       | +-----------------------------------------------------------------------+ |
+---------------------------------------------------------------------------------------------------+
```

---

## 4. Acceptance Criteria (AC Matrix)

| ID | Feature | Acceptance Criteria |
|---|---|---|
| **AC-01** | User Management | Admin can add and deactivate users. Active seats counter updates automatically against System Admin quota. |
| **AC-02** | Case Data Ingestion | Legal Admin can upload digital case files (PDF/DOCX). Backend automatically parses, chunks, and embeds data into tenant vector store. |
| **AC-03** | Precedent & Case Search | Fee-earner can search public legal precedents and tenant-ingested case papers with filters. |
| **AC-04** | AI Legal Advice | System provides grounded advice based on ingested case data and precedents with exact citations. |
| **AC-05** | Statutory Mapping | System maps IPC, CrPC, and IEA sections to BNS, BNSS, and BSA provisions with comparative view. |
| **AC-06** | Document Export | Fee-earner can save research briefs and export reworked documents to formatted DOCX or PDF files. |

---

## 5. Explicit Exclusions (Out of Scope for Now)

* **No Case/Matter Management**: Full case lifecycle management, matter folders, and practice tracking excluded for now.
* **No System Admin Tasks**: License tier purchasing, seat quota changes, RAG parameter tuning, and LLM model selection are handled by System Admin / system defaults.
* **No PDF Template Management**: Form template management excluded.
