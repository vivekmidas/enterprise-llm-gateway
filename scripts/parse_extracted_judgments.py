import json
import os
import re
from pathlib import Path

def extract_statutes(text: str) -> list[dict]:
    """Extract Acts, Codes, and Sections cited in the judgment text"""
    statutes = []
    
    # Pattern 1: Section X of Act Name
    pattern_sec_of = r"(?:Section|Sec\.)\s+([\d\w\s,\(\)]+?)\s+(?:of\s+the\s+)?([A-Z][A-Za-z0-9\s,\.\(\)]+?(?:Act|Code|Constitution)[^,\n]*)"
    for m in re.finditer(pattern_sec_of, text, re.IGNORECASE):
        sec_num = m.group(1).strip()
        act_name = m.group(2).strip()
        statutes.append({"section": sec_num, "act": act_name, "raw_citation": m.group(0)})

    # Pattern 2: Act abbreviations like IPC, CrPC, CPC, Article 226
    pattern_abbr = r"(?:Section|Sec\.)\s+([\d\w\s,\(\)]+?)\s+(IPC|CrPC|CPC|Indian Penal Code|Code of Criminal Procedure|Code of Civil Procedure)"
    for m in re.finditer(pattern_abbr, text, re.IGNORECASE):
        statutes.append({"section": m.group(1).strip(), "act": m.group(2).strip(), "raw_citation": m.group(0)})
        
    pattern_art = r"(?:Article)\s+([\d\w\s,\(\)]+?)\s+(?:of\s+the\s+)?(Constitution(?:\s+of\s+India)?)"
    for m in re.finditer(pattern_art, text, re.IGNORECASE):
        statutes.append({"section": m.group(1).strip(), "act": m.group(2).strip(), "raw_citation": m.group(0)})
        
    # Deduplicate
    seen = set()
    unique_statutes = []
    for s in statutes:
        key = (s["section"], s["act"])
        if key not in seen:
            seen.add(key)
            unique_statutes.append(s)
            
    return unique_statutes

def extract_precedents(text: str) -> list[str]:
    """Extract case precedents cited in the judgment"""
    pattern = r"([A-Z][A-Za-z0-9\.\s&]+?\s+v(?:s)?\.\s+[A-Z][A-Za-z0-9\.\s&]+?(?:,\s*\(\d{4}\)\s*\d+\s*[A-Z\s\d]+)?)"
    matches = re.findall(pattern, text)
    cleaned = [m.strip() for m in matches if len(m.strip()) > 10 and not m.lower().startswith("state")]
    return list(dict.fromkeys(cleaned))

def extract_parties_and_counsel(text: str) -> dict:
    """Extract Petitioners, Respondents, and Counsel details"""
    petitioners = []
    respondents = []
    counsel = {"petitioner_counsel": [], "respondent_counsel": []}
    
    # Extract Petitioner vs Respondent block
    pet_match = re.search(r"([A-Z0-9\.\s&\(\)]+?)\s+\.\.\.\.\.?(?:Petitioner|Appellant)", text, re.IGNORECASE)
    if pet_match:
        petitioners.append(pet_match.group(1).strip())
        
    resp_match = re.search(r"versus\s*\n\s*([A-Z0-9\.\s&\(\)]+?)\s+\.\.\.\.\.?(?:Respondent|Opponent)", text, re.IGNORECASE)
    if resp_match:
        respondents.append(resp_match.group(1).strip())
        
    # Extract Advocates/Through lines
    through_matches = re.finditer(r"Through:\s*([^\n]+(?:\n[^\n]+)?)", text)
    for i, m in enumerate(through_matches):
        counsel_str = m.group(1).replace("\n", " ").strip()
        if i == 0:
            counsel["petitioner_counsel"].append(counsel_str)
        else:
            counsel["respondent_counsel"].append(counsel_str)
            
    return {
        "petitioners": petitioners,
        "respondents": respondents,
        "counsel": counsel
    }

def extract_disposition_and_holding(text: str) -> dict:
    """Extract legal disposition, holding, and key orders"""
    disposition = "PENDING / OTHER"
    if re.search(r"dismissed\s+as\s+withdrawn", text, re.IGNORECASE):
        disposition = "DISMISSED AS WITHDRAWN"
    elif re.search(r"allowed|quashed", text, re.IGNORECASE):
        disposition = "ALLOWED / QUASHED"
    elif re.search(r"dismissed", text, re.IGNORECASE):
        disposition = "DISMISSED"
        
    # Extract numbered order paragraphs
    paragraphs = re.findall(r"(\n\d+\.\s+[^\n]+(?:\n(?!\d+\.)[^\n]+)*)", text)
    order_points = [p.strip() for p in paragraphs]
    
    return {
        "disposition": disposition,
        "key_order_points": order_points,
        "total_order_paragraphs": len(order_points)
    }

def parse_full_judgment(item: dict) -> dict:
    """Parse complete judgment text into structured Domain Schema format"""
    raw_text = item.get("full_text", "")
    
    parties_info = extract_parties_and_counsel(raw_text)
    statutes_info = extract_statutes(raw_text)
    precedents_info = extract_precedents(raw_text)
    decision_info = extract_disposition_and_holding(raw_text)
    
    parsed_record = {
        "case_identity": {
            "cnr": item.get("cnr"),
            "case_title": item.get("title"),
            "court": item.get("court"),
            "bench_judge": item.get("judge"),
            "decision_date": item.get("decision_date"),
            "pdf_filename": item.get("pdf_filename"),
            "character_count": item.get("character_count"),
            "page_count": item.get("page_count")
        },
        "parties": {
            "petitioners": parties_info["petitioners"],
            "respondents": parties_info["respondents"],
            "counsel": parties_info["counsel"]
        },
        "legal_substance": {
            "statutes_and_sections_cited": statutes_info,
            "precedents_cited": precedents_info,
        },
        "decision_and_holding": {
            "disposition": decision_info["disposition"],
            "total_paragraphs": decision_info["total_order_paragraphs"],
            "order_summary_points": decision_info["key_order_points"]
        },
        "full_text_snippet": raw_text[:1000]
    }
    return parsed_record

def main():
    input_files = [
        "data/extracted_judgments/extracted_7_26_2026_2026-07-31.json",
        "data/extracted_judgments/delhi_hc_2026_07_31_sample.json"
    ]
    
    target_file = None
    for f in input_files:
        if os.path.exists(f):
            target_file = f
            break
            
    if not target_file:
        print("No extracted judgment JSON file found.")
        return
        
    print(f"Loading extracted judgments from: {target_file}")
    with open(target_file, "r", encoding="utf-8") as f:
        judgments = json.load(f)
        
    print(f"Parsing {len(judgments)} judgment full texts...")
    parsed_judgments = [parse_full_judgment(j) for j in judgments]
    
    out_file = "data/extracted_judgments/parsed_legal_analysis_2026_07_31.json"
    with open(out_file, "w", encoding="utf-8") as f_out:
        json.dump(parsed_judgments, f_out, indent=2, ensure_ascii=False)
        
    print(f"✓ Parsed complete legal case details for {len(parsed_judgments)} judgments.")
    print(f"✓ Output saved to: {out_file}")

if __name__ == "__main__":
    main()
