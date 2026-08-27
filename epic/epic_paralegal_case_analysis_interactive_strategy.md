# EPIC: Commercial Case Gap Analysis, Source Traceability, Dynamic Enrichment & Strategy Sandbox (Indian Jurisprudence)

## Executive Summary
Provides paralegals, legal associates, and commercial litigators with an AI-assisted commercial case intake, structured fact extraction with **ubiquitous source traceability**, **intelligent gap analysis (documentary, factual, procedural, contractual, limitation)**, **workflow readiness metrics**, and a **categorized legal action exploration sandbox tailored specifically to Indian commercial practice**.
The workspace features three complete, realistic Indian commercial scenarios (Master Supply Contract Dispute, Service Agreement Termination, and Straightforward Invoiced Recovery), a persistent case dossier panel, an interactive 3-tab analysis suite with Gap Analysis as the signature view, a live **Dynamic Enrichment engine** with measurable before-and-after summaries, and professional first-draft court/notice generators with mandatory human review disclosures.

---

## 1. Five Core Legal Design Principles

### Principle 1: Measurable Outcome & Before-and-After Summary
At the end of every scenario and after any dynamic enrichment, the system displays a quantified **Matter Audit Card**:
- **Documents Reviewed**: (e.g., 6 of 6 ingested)
- **Facts Confirmed**: (e.g., 12 verified facts with citations)
- **Open Gaps**: (e.g., 2 Open, 1 Partially Addressed, 2 Closed)
- **Procedural Risks Detected**: (e.g., 1 limitation notice risk)
- **Possible Next Actions Identified**: (e.g., 5 categorized routes)
- **What Changed After Enrichment**: Explicit diff highlighting closed gaps and revised action feasibility.

### Principle 2: Ubiquitous Source Traceability (Trust Engine)
Every extracted fact, timeline event, and surfaced gap carries a clickable **Source Reference Chip**:
- *Examples*: `[Source: Clause 7.2 of Master Supply Agreement]`, `[Source: Invoice INV-1042, dated 14 March 2025]`, `[Source: Email from Rajesh Sharma dated 22 April 2025]`, `[Source: Bank Return Memo No. 8049 dated 14 Jan 2026]`.

### Principle 3: Prudent, Non-Definitive Legal Terminology
AI outputs avoid declarative legal assertions, framing suggestions with professional caution:
- Instead of *"You must file"* -> **"Possible procedural route"**
- Instead of *"Fatal breach"* -> **"Potential issue / Requires counsel verification"**
- Instead of *"Case will win 88%"* -> **"Evidence completeness: 86% | Subject to counsel review"**

### Principle 4: Categorized Action Matrix
The "Possible Courses of Action" tab is grouped into 5 actionable functional tiers:
1. **Immediate Evidence-Preservation Steps** (Section 65B/63 BSA electronic evidence certificate, litigation hold notice).
2. **Pre-Litigation Actions** (Statutory demand notice, Section 12A Commercial Courts Pre-Institution Mediation).
3. **Settlement & ADR Options** (Without-prejudice commercial settlement, DSLSA / SAMADHAN mediation).
4. **Formal Proceedings** (Summary Suit under Order XXXVII CPC, DIAC / MCIA Arbitration filing).
5. **Interim Relief Measures** (Section 9 Arbitration Act asset freeze / status quo injunction).

### Principle 5: Visible Matter Workflow Signals
Header displays real-time workflow status indicators:
- `Matter Status: Initial Assessment` (or `Active Review` / `Post-Enrichment Analysis`)
- `Evidence Completeness: 68%` (Visual progress bar)
- `Procedural Readiness: Needs Review` (or `Ready for Notice Drafting`)

---

## 2. Navigation Architecture: Left Navigation Bar & Top Subnav Integration

```
+------------------------------------------------------------------------------------------------------------------+
| LEFT NAVIGATION BAR (AdminSidebar & Legal Workflow Rail)                                                         |
+------------------------------------------------------------------------------------------------------------------+
|  [Navigation]                                                                                                    |
|    - Dashboard               (/admin)                                                                            |
|    - Legal Research          (/legal?tab=search)          [Indian Precedents: SC, Del HC, Bom HC]                |
|    - Commercial Gap Sandbox  (/legal?tab=case_strategy)   <-- [FIRST-CLASS LEFT NAVIGATION OPTION]               |
|    - Case Workspaces         (/legal?tab=cases)                                                                  |
|    - Saved Briefs            (/legal?tab=briefs)                                                                 |
|    - Workflows               (/admin?tab=workflows)                                                             |
+------------------------------------------------------------------------------------------------------------------+
| LEGAL WORKSPACE LEFT EXPANDABLE RAIL (Inside Legal Portal)                                                       |
|  1. [Precedent Search]       (Intent & Section Discovery: BNS, BNSS, NI Act, CPC)                                |
|  2. [Commercial Gap Sandbox] (3 Scenarios & Traceable Gap Analysis) <-- [NEW LEFT RAIL SKILL]                    |
|  3. [Draft Pleadings]        (Plaints, Section 138 Complaints, Bail Petitions)                                   |
|  4. [Affidavit Drafter]      (Court Submissions & Statement of Truth)                                            |
|  5. [Case Vault]             (Multi-Doc Dossier & Timeline)                                                      |
|  6. [Opponent Analyzer]      (Written Statement & Contradiction Finder)                                          |
+------------------------------------------------------------------------------------------------------------------+
```

---

## 3. The 3 Realistic Indian Commercial Scenarios

```
+---------------------------------------------------------------------------------------------------------------------+
| SCENARIO A: Supply Contract Dispute (Primary / Most Detailed Deep-Dive)                                             |
| - Matter: Non-payment of ₹1.85 Cr + alleged defective supply under Master Supply Agreement (MSA).                   |
| - Ingested Docs: Master Supply Agreement (Clauses 7, 14, 19), 6 Invoices & Delivery Challans, Email Complaints      |
|   Chain, 2 Debit Notes raised by Buyer, Partial Payment Advice (₹35 Lakhs), Supplier Demand Notice.                 |
| - Source-Backed Gaps:                                                                                               |
|   * Documentary: Missing joint inspection minutes [Ref: MSA Clause 14.2]                                            |
|   * Procedural: Defect notice served on Day 18 (Exceeds 15-day window in MSA Clause 14.1) [Ref: Email 22 Jan 2026]  |
|   * Contractual: DIAC Arbitration clause present but uninvoked [Ref: MSA Clause 19.1]                               |
|   * Financial: Principal outstanding statement ₹1.50 Cr + 18% commercial interest ledger incomplete [Ref: Invoices]  |
+---------------------------------------------------------------------------------------------------------------------+
| SCENARIO B: Service Agreement Termination Dispute (IT / Facilities Manpower)                                        |
| - Matter: Contract prematurely terminated by Client citing SLA non-performance; ₹65 Lakhs unpaid final dues.        |
| - Ingested Docs: Master Services Agreement, Termination Notice, Reply, SLA Logs, Escalation Emails, Final Invoice.  |
| - Source-Backed Gaps: Mandatory 30-day cure period notice bypassed by client [Ref: MSA Clause 11.3].                |
+---------------------------------------------------------------------------------------------------------------------+
| SCENARIO C: Straightforward Invoiced Debt Recovery (High-Speed Summary Case)                                        |
| - Matter: Clear admitted debt of ₹42 Lakhs with signed delivery challans and balance confirmation.                  |
| - Ingested Docs: Purchase Orders, 4 GST Invoices, Counter-signed Delivery Challans, Ledger Confirmation.        |
| - Source-Backed Gaps: Section 12A Pre-Institution Mediation not yet filed [Ref: Commercial Courts Act 2015].        |
+---------------------------------------------------------------------------------------------------------------------+
```

---

## 4. UI Architecture & Signature Screen Layout

```
+-----------------------------------------------------------------------------------------------------------------------------+
|  ENTERPRISE LLM GATEWAY  |  Legal AI Workspace  >  Commercial Gap & Strategy Sandbox                   [Tenant: Apex Legal] |
+-----------------------------------------------------------------------------------------------------------------------------+
|  SCENARIOS:  [ (A) Supply Contract Dispute (₹1.85 Cr) v ]  [ (B) Service Termination ]  [ (C) Invoiced Debt Recovery ]      |
|  MATTER STATUS: [ Initial Assessment ]  |  EVIDENCE COMPLETENESS: [=== 68% ===]  |  PROCEDURAL READINESS: [ Needs Review ]  |
|  Notice: All data is mocked for demonstration purposes | AI-generated suggestion – for human review only                    |
+------------------------------------+----------------------------------------------------------------------------------------+
|  LEFT PERSISTENT PANEL (DOSSIER)   |  MAIN WORKSPACE: 3 ANALYSIS TABS (Gap Analysis is Signature View)                      |
+------------------------------------+----------------------------------------------------------------------------------------+
|  [+] UPLOADED DOCUMENTS (6):       |  [ TAB 1: Source Facts ]  [ TAB 2: Gap Analysis (Signature) ]  [ TAB 3: Action Matrix ]    |
|  - Master_Supply_Agreement.pdf     +----------------------------------------------------------------------------------------+
|  - Tax_Invoices_Challans.pdf       |  TAB 2: STRUCTURED GAP ANALYSIS (Grouped by Category with Source Traceability)         |
|  - Email_Complaints_Trail.pdf      |                                                                                        |
|  - Debit_Notes_Buyer.pdf           |  1. DOCUMENTARY GAPS                                                                   |
|  - Demand_Notice_Supplier.pdf      |  [ OPEN - HIGH SEVERITY ] Missing Joint Inspection Minutes / Quality Certificate       |
|  [ + Add Mocked Document ]         |  - Explanation: MSA Clause 14.2 mandates joint laboratory test within 7 days of defect.|
|                                    |  - Source Reference: [Clause 14.2 of Master Supply Agreement (p. 18)]                  |
|  CASE TIMELINE (Source-Linked):    |  - Status: Potential issue | Requires client verification before filing.               |
|  - 14 Jan: Goods Delivered         |                                                                                        |
|    [Source: Challan DC-1082]       |  2. PROCEDURAL / NOTICE GAPS                                                           |
|  - 28 Jan: Debit Note Raised       |  [ OPEN - MEDIUM SEVERITY ] Defect Notice Window Exceeded                              |
|    [Source: Debit Note DN-44]      |  - Explanation: Defect notice was dispatched on Day 18 after delivery.                 |
|  - 02 Feb: Notice Dispatched       |  - Source Reference: [Email from Buyer dated 28 Jan 2026]                              |
|    [Source: Speed Post POD-88]     |                                                                                        |
|                                    |  3. CONTRACTUAL / CLAUSE GAPS                                                          |
|  KEY EXTRACTED FACTS:              |  [ PARTIALLY ADDRESSED ] Arbitration Clause (DIAC) present but uninvoked               |
|  - Principal Due: ₹1,50,00,000     |  - Source Reference: [Clause 19.1 of Master Supply Agreement]                          |
|    [Source: Invoice Ledger p. 3]   |                                                                                        |
|  - Interest Claimed: 18% p.a.      |  +----------------------------------------------------------------------------------+  |
|    [Source: MSA Clause 7.4]        |  | [+ DYNAMIC ENRICHMENT: Add New Information / Document]                           |  |
|                                    |  | Paste: "Buyer sent WhatsApp admitting ₹18 Lakhs is due and asking for 45 days..."   |  |
|                                    |  | [ Process Context & Refresh Gap Analysis ]                                          |  |
|                                    |  +----------------------------------------------------------------------------------+  |
|                                    |                                                                                        |
|                                    |  >>> MEASURABLE SUMMARY & WHAT CHANGED <<<                                             |
|                                    |  Docs: 6 Reviewed | Facts: 12 Confirmed | Gaps: 2 Closed, 1 Open | Readiness: 86%       |
+------------------------------------+----------------------------------------------------------------------------------------+
```

---

## 5. Categorized Action Matrix (Tab 3)

```
+------------------------------------------------------------------------------------------------------------------+
| TAB 3: POSSIBLE COURSES OF ACTION (Categorized & Actionable)                                                     |
+------------------------------------------------------------------------------------------------------------------+
|                                                                                                                  |
|  CATEGORY A: IMMEDIATE EVIDENCE-PRESERVATION STEPS                                                               |
|  [*] Obtain Certificate under Section 63 BSA 2023 / 65B Evidence Act for email and WhatsApp ledger admissions.  |
|      Prerequisites: Original phone/laptop inspection & hash logs. [Status: Recommended First Step]               |
|                                                                                                                  |
|  CATEGORY B: PRE-LITIGATION ACTIONS                                                                              |
|  [*] Issue Final Rebuttal & Statutory Demand Notice citing MSA Clause 14.1 defect notice expiry.                 |
|      Prerequisites: Complete ledger statement of principal (₹1.50 Cr) + 18% interest. [Generate First-Draft]    |
|  [*] Invoke Section 12A Pre-Institution Mediation (Commercial Courts Act 2015 via DSLSA).                       |
|      Prerequisites: Form 1 submission & fee payment. [Generate Form 1 Checklist]                                 |
|                                                                                                                  |
|  CATEGORY C: SETTLEMENT & ADR OPTIONS                                                                            |
|  [*] Propose Without-Prejudice Settlement Conference with structured 45-day payment installment plan.            |
|      Prerequisites: Debtor corporate guarantee & post-dated cheques.                                             |
|                                                                                                                  |
|  CATEGORY D: FORMAL PROCEEDINGS                                                                                  |
|  [*] File Summary Suit under Order XXXVII CPC in Commercial Court.                                               |
|      Prerequisites: Countersigned challans & Section 12A mediation non-starter report.                            |
|  [*] Issue Notice of Invocation of Arbitration under Section 21 Arbitration Act (DIAC).                         |
|      Prerequisites: Formal dispute notice per MSA Clause 19.1. [Generate Arbitration Notice]                     |
|                                                                                                                  |
|  CATEGORY E: INTERIM RELIEF MEASURES                                                                             |
|  [*] Seek Section 9 Interim Asset Attachment / Bank Guarantee in High Court.                                     |
|      Prerequisites: Evidence of debtor asset dissipation or third-party transfer risk.                           |
+------------------------------------------------------------------------------------------------------------------+
```

---

## 6. Implementation Plan (Embedded within Epic)

### Phase 1: Frontend Workspace with Source Traceability, Categorized Actions & Gap Analysis
- **Mock Data Engine (`frontend/app/legal/mock_case_strategy_data.ts`)**:
  - 3 complete Indian commercial scenarios with source references for all facts, timeline events, and gaps.
  - Multi-category gap analyzer with severity badges (`High`, `Medium`, `Low`) and source links.
  - 5-tier Categorized Action Matrix (Evidence Preservation, Pre-Litigation, Settlement, Formal Proceedings, Interim Relief).
  - Matter Workflow Signals (Matter Status, Evidence Completeness %, Procedural Readiness).
  - Measurable Before-and-After Summary Engine (tracks diffs when dynamic enrichment occurs).
  - Professional Indian legal draft generators with mandatory human review disclaimer.
- **Component Architecture (`frontend/app/legal/CaseStrategyAnalyzer.tsx`)**:
  - Scenario Selector bar with workflow status indicators.
  - Persistent Left Panel: Document drawer, Source-linked Timeline, and Fact cards.
  - Main Area 3-Tab Suite (Source Facts, Signature Gap Analysis, Categorized Action Matrix).
  - Dynamic Enrichment modal (+ Note / + Mock Doc) with instant "What Changed" diff banner.
  - Reference Precedent Slide-Over Drawer.
  - Draft Pleadings / Notice Preview Modal.
- **Navigation Integration**:
  - `AdminSidebar.tsx`, `LegalResearchHub.tsx` left rail, `page.tsx` tabs, `route_permissions.ts`.

---

## 7. Verification & Testing Plan

1. **Source Traceability**:
   - Verify every fact, timeline item, and gap displays its exact source chip (e.g. `[Clause 7.2 MSA]`, `[Invoice INV-1042]`).
2. **Measurable Outcomes**:
   - Verify Matter Status indicators (Status, Evidence Completeness %, Readiness) display in header.
   - Verify Measurable Summary card updates when Dynamic Enrichment adds new information.
3. **Categorized Actions & Draft Generator**:
   - Verify Tab 3 separates Actions into Categories A through E.
   - Verify "Generate Draft" button outputs professional notice with human review disclaimer.
4. **Build & Type Check**:
   - Run `cd frontend && npm run build`.
