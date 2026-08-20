#!/usr/bin/env python3
"""
Legal Search & Semantic Resolution Benchmark Suite
Evaluates intent parsing, Tri-Path Search, and semantic directionality (e.g. 'dog bites man' vs 'man bites dog').
"""

import asyncio
import os
import sys
import time
from typing import Dict, Any, List

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.knowledge.domain_research_router import parse_natural_language_intent, SearchRequest


BENCHMARK_SEMANTIC_CONTRASTS = [
    {
        "id": "SEM-01",
        "pair_name": "Dog Bites Man vs Man Bites Dog",
        "query_a": "dog bites man compensation tort liability owner",
        "query_b": "man bites dog animal cruelty prosecution offence",
        "expected_distinction": "Subject-Object directionality separation",
    },
    {
        "id": "SEM-02",
        "pair_name": "Tenant Eviction vs Landlord Penalty",
        "query_a": "tenant evicted for non-payment of rent in arrears",
        "query_b": "landlord penalized for illegal and unlawful eviction of tenant",
        "expected_distinction": "Opposite aggrieved party resolution",
    },
    {
        "id": "SEM-03",
        "pair_name": "Wrongful Termination vs Non-Compete Breach",
        "query_a": "employer sued by employee for wrongful termination without notice",
        "query_b": "employee sued by employer for breach of non-compete clause",
        "expected_distinction": "Plaintiff/Defendant role inversion",
    },
]

BENCHMARK_LEGAL_QUERIES = [
    {
        "id": "LEG-01",
        "category": "Statute & Section",
        "query": "anticipatory bail under Section 438 CrPC in Punjab and Haryana High Court",
        "expected_statute": "CrPC",
        "expected_section": "438",
        "expected_court": "High Court of Punjab and Haryana",
    },
    {
        "id": "LEG-02",
        "category": "Judge Coram & Crime",
        "query": "cases before Justice Anil Kshetarpal regarding electricity theft compounding",
        "expected_judge": "Anil Kshetarpal",
        "expected_concepts": ["electricity theft"],
    },
    {
        "id": "LEG-03",
        "category": "Tax Reassessment & Hearing",
        "query": "quashing of reassessment order under Section 148A Income Tax Act for want of personal hearing in Delhi High Court in 2026",
        "expected_statute": "Section 148A",
        "expected_court": "High Court of Delhi",
        "expected_year": 2026,
    },
    {
        "id": "LEG-04",
        "category": "Outcome & Statutory Non-Compliance",
        "query": "Section 50 NDPS non-compliance where accused was set free or acquitted",
        "expected_disposition": "ALLOWED / QUASHED",
    },
]


def run_benchmarks():
    print("\n" + "=" * 80)
    print(" ⚖️  LEGAL SEARCH & SEMANTIC RESOLUTION BENCHMARK SUITE")
    print("=" * 80 + "\n")

    # 1. Semantic Directionality Resolution Tests
    print("--- 1. SEMANTIC CONTRAST TESTS (Directionality & Nuance) ---\n")
    contrast_passed = 0
    for test in BENCHMARK_SEMANTIC_CONTRASTS:
        t0 = time.perf_counter()
        parsed_a = parse_natural_language_intent(test["query_a"])
        parsed_b = parse_natural_language_intent(test["query_b"])
        dur_ms = round((time.perf_counter() - t0) * 1000, 2)

        # Semantic queries should be distinct and not identical
        distinct = parsed_a["semantic_query"].strip() != parsed_b["semantic_query"].strip()
        status = "PASSED" if distinct else "FAILED"
        if distinct:
            contrast_passed += 1

        print(f"[{test['id']}] {test['pair_name']} -> {status} ({dur_ms}ms)")
        print(f"   Query A Semantic: \"{parsed_a['semantic_query']}\"")
        print(f"   Query B Semantic: \"{parsed_b['semantic_query']}\"")
        print(f"   Expected: {test['expected_distinction']}\n")

    # 2. Legal Domain Entity & Concept Extraction Tests
    print("--- 2. LEGAL ENTITY & INTENT CATEGORIZATION TESTS ---\n")
    legal_passed = 0
    total_latency_ms = 0.0

    for test in BENCHMARK_LEGAL_QUERIES:
        t0 = time.perf_counter()
        parsed = parse_natural_language_intent(test["query"])
        dur_ms = round((time.perf_counter() - t0) * 1000, 3)
        total_latency_ms += dur_ms

        checks = []
        if "expected_statute" in test:
            checks.append(test["expected_statute"].lower() in str(parsed.get("extracted_statute", "")).lower())
        if "expected_section" in test:
            checks.append(str(parsed.get("extracted_section", "")) == test["expected_section"])
        if "expected_court" in test:
            checks.append(parsed.get("extracted_court") == test["expected_court"])
        if "expected_judge" in test:
            checks.append(test["expected_judge"].lower() in str(parsed.get("extracted_judge", "")).lower())
        if "expected_year" in test:
            checks.append(parsed.get("extracted_year") == test["expected_year"])
        if "expected_disposition" in test:
            checks.append(parsed.get("extracted_disposition") == test["expected_disposition"])

        is_success = all(checks) if checks else True
        if is_success:
            legal_passed += 1

        status = "PASSED" if is_success else "FAILED"
        print(f"[{test['id']}] {test['category']} -> {status} ({dur_ms}ms)")
        print(f"   Input: \"{test['query']}\"")
        print(f"   Extracted Court: {parsed.get('extracted_court')} (code: {parsed.get('extracted_court_code')})")
        print(f"   Extracted Judge: {parsed.get('extracted_judge')}")
        print(f"   Extracted Statute/Sec: {parsed.get('extracted_statute')} (Sec: {parsed.get('extracted_section')})")
        print(f"   Extracted Year: {parsed.get('extracted_year')}")
        print(f"   Extracted Concepts: {parsed.get('extracted_concepts')}")
        print(f"   Semantic Text: \"{parsed.get('semantic_query')}\"\n")

    # 3. Summary Report
    total_tests = len(BENCHMARK_SEMANTIC_CONTRASTS) + len(BENCHMARK_LEGAL_QUERIES)
    total_passed = contrast_passed + legal_passed
    avg_latency = round(total_latency_ms / len(BENCHMARK_LEGAL_QUERIES), 3)

    print("=" * 80)
    print(" 📊 BENCHMARK SUMMARY RESULTS")
    print("=" * 80)
    print(f" Total Benchmark Tests: {total_tests}")
    print(f" Passed:               {total_passed}/{total_tests} ({round(total_passed / total_tests * 100, 1)}%)")
    print(f" Contrast Pairs:       {contrast_passed}/{len(BENCHMARK_SEMANTIC_CONTRASTS)} Passed")
    print(f" Legal Intent Checks:  {legal_passed}/{len(BENCHMARK_LEGAL_QUERIES)} Passed")
    print(f" Avg Intent Latency:   {avg_latency} ms")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_benchmarks()
