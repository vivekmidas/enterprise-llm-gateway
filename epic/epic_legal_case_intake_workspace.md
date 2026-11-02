# EPIC: Intelligent Legal Case Intake Workspace & Statutory Section Reckoner

## Executive Summary
Provides legal practitioners, litigators, associates, and paralegals with a streamlined, intelligent **Legal Case Intake Workspace**. The intake modal enables rapid onboarding of new disputes by combining:
1. Flexible **Case Category & Domain Selection** (Commercial, Criminal/BNS, Constitutional, Arbitration, Civil).
2. **AI-Powered Intake Extraction** from plain English summaries or uploaded document extracts using customizable extraction prompt profiles.
3. **Statutory Ready Reckoner Autocomplete & Section Pill Management** with **BNS, BNSS, and BSA** as the universal baseline, supplemented dynamically by category-specific acts (Commercial Courts Act, Arbitration Act, NI Act, CPC, Constitution of India).
4. **Automated Party & Headline Recognition** with full user editability.
5. **Dynamic Domain Schema Optional Fields** tailored to the selected legal domain (e.g., Police Jurisdiction, Coram, Court level, Arbitral Seat).
6. **Multi-Document Ingestion** directly linking uploaded filings to the case's persistent Evidence Vault.

---

## Personas & User Journeys

### Personas
- **Litigator / Legal Associate / Paralegal**: Primary user. Needs to initiate a case in under 60 seconds with minimal manual typing, having statutory sections, parties, and headline parsed automatically from a brief or draft complaint.
- **Tenant Admin / Managing Partner**: Configures domain schemas, court jurisdictions, and default extraction profiles for firm-wide consistency.

### User Journey
1. **Initiation**: User clicks "+ New Case" from the matter selector.
2. **Domain Selection**: Chooses category (e.g., Criminal, Commercial) or lets AI infer it from the brief.
3. **Intake & Extraction**: User types plain English brief or uploads a document/extract. Clicks "Extract & Map Fields". System triggers extraction profile prompt; if no matches found, alerts user with "No data identified" while allowing full manual entry.
4. **Statutory Refinement**: Reviews AI-extracted section pills (e.g., *BNS Sec 318(4)*, *NI Act Sec 138*). Types query (e.g., "Bns 165", "CrPC 156") into typeahead to add additional sections as pills; deletes irrelevant pills.
5. **Headline & Parties**: Reviews auto-recognized matter headline and parties; edits inline.
6. **Domain Fields & Multi-Docs**: Fills optional domain-specific schema fields (Police jurisdiction, Coram, Forum). Uploads additional supporting documents.
7. **Workspace Launch**: Clicks "Create Case Workspace". System provisions new matter with populated Evidence Vault, statutory reckoners, parties, and dynamic gap analysis.

---

## User Stories

### STORY-INTAKE-01: Baseline Case Workspace & Left Dossier Navigation (Existing Implementation)
- **Status**: Implemented.
- **Scope**: Multi-matter switcher, Left Evidence Vault & Timeline accordion, Statutory Ready Reckoners, Categorized Action Matrix, Dynamic Gap Enrichment.

### STORY-INTAKE-02: Intelligent Multi-Modal Case Intake Modal (New Feature)
- **Status**: Ready for Implementation.
- **Components**:
  - **Selector**: Category selector (Commercial, Criminal/BNS, Constitutional, Arbitration, Civil).
  - **AI Extraction Engine**: Unified extraction interface using profile prompt (`extractIntakeDetails`). Graceful fallback if no data identified.
  - **Base Statutory Corpus**: BNS, BNSS, BSA as base, plus CPC, CrPC, NI Act, CCA, Arbitration Act, Constitution.
  - **Typeahead & Section Pills**: Autocomplete for section codes/names with click-to-add and pill delete `[x]`.
  - **Party & Headline Sync**: Auto-extraction with dual editable inputs.
  - **Dynamic Domain Schemas**: Dynamic optional fields rendered per case category.
  - **Multi-Document Upload**: Multi-file attachment with direct persistence into the matter's Evidence Vault.

---

## Technical Specifications & Integration Architecture

### Extraction Profile Prompt Schema
```json
{
  "profile_id": "default_legal_intake_v1",
  "system_instruction": "Extract structured legal intake fields: case_category, matter_headline, parties, statutory_sections, and domain_fields.",
  "target_fields": [
    "matter_headline",
    "case_category",
    "initiating_party",
    "opposing_party",
    "statutory_sections",
    "disputed_value",
    "forum_or_court",
    "police_jurisdiction",
    "secondary_reference"
  ]
}
```
the prompt should be editable for adding or modification in the future.

### Statutory Typeahead Database
Expanded catalogue in `mock_autopilot_data.ts` including:
- BNS (Bharatiya Nyaya Sanhita): 318, 316, 165, 61, 111, 303, etc.
- BNSS (Bharatiya Nagarik Suraksha Sanhita): 35, 173, 175, 528, etc.
- BSA (Bharatiya Sakshya Adhiniyam): 63, 65, 24, 32, etc.
- Special & Procedural Acts: NI Act 138/141, Commercial Courts Act 12A, Arbitration Act 9/11/21/34, CPC Order 37/39/Sec 9, Constitution Art 226/32.

### Case Identifier & Audit Metadata Schema
- **Case ID Format**: `(tenant-name-caseid)` e.g. `delhi_law_chambers-case_1741172800000`.
- **User Audit**: Captures `created_by_user_id` (current logged-in user id), creation date and time (`created_at` ISO format + `created_at_display`).
- **Section 5 - Dynamic Optional Domain Fields**: Optional fields pool (e.g., Disputed Valuation, Police Station, Coram, Court Hierarchy, Limitation Date, ADR Docket, Interim Relief, Billing Code) extracted from configured field list or case type. Users can add or remove (`[×]`) any field on demand.

---

## Verification & Acceptance Criteria
1. Clicking "+ New Case" opens the unified intake modal.
2. Case ID generated as `(tenant-name-caseid)` capturing creator user ID, creation date and time.
3. Selecting or changing case category defaults active optional fields from the catalog, with instant removal (`[×]`) or addition (`+ Add Field`) from `CONFIGURED_DOMAIN_FIELDS_CATALOG`.
4. Typing brief or dropping document extract and clicking "Magic Parse" populates headline, parties, case category, and relevant section pills.
5. If input is empty or invalid, system triggers "No data identified for intake form" warning banner and allows full manual editing.
6. User can search sections (e.g. "bns 165", "crpc 156", "order 37") and select from autocomplete dropdown to add pills.
7. User can delete section pills with `[×]`.
8. User can attach multiple files and delete attached files before submitting.
9. Submitting modal provisions new matter with `(tenant-name-caseid)` format, attaches uploaded files to Evidence Vault, and switches active matter to newly created case.

