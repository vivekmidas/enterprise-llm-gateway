import argparse
import glob
import json
import os
import re
import sys
import tarfile
import subprocess
from pathlib import Path
import pandas as pd
import pypdf

# Add backend directory to sys.path to import app modules if available
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

def download_s3_tar_archive(year: int, court_code: str, output_dir: Path) -> list[Path]:
    """Sync target tar archives from S3 Open Data bucket"""
    s3_path = f"s3://indian-high-court-judgments/data/tar/year={year}/court={court_code}/"
    tar_dir = output_dir / "tars" / f"year={year}" / f"court={court_code}"
    tar_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "aws", "s3", "sync",
        s3_path,
        str(tar_dir),
        "--no-sign-request",
        "--include", "*.tar",
        "--exclude", "*.json"
    ]
    print(f"[1/4] Syncing PDF tar archives from S3: {s3_path}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    tar_files = list(tar_dir.rglob("*.tar"))
    print(f"  ✓ Available tar archives: {len(tar_files)}")
    return tar_files

def extract_pdf_text_from_stream(stream) -> str:
    """Extract digital text from PDF stream"""
    try:
        reader = pypdf.PdfReader(stream)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text.strip()
    except Exception as e:
        return f"ERROR: {e}"

def extract_legal_knowledge_graph(item: dict) -> dict:
    """
    Extract Legal Strategy Knowledge Graph (Nodes + Edges) for Lawyer Path Analysis
    """
    text = item.get("full_text", "")
    cnr = item.get("cnr", "UNKNOWN_CNR")
    title = item.get("title", "")
    court = item.get("court", "")
    date = str(item.get("decision_date", ""))
    if "00:00:00" in date:
        date = date.split()[0]
    judge = item.get("judge", "")
    
    # 1. Primary Case Node
    case_node_id = f"CASE:{cnr}"
    nodes = [{
        "id": case_node_id,
        "type": "Case",
        "label": title,
        "cnr": cnr,
        "court": court,
        "judge": judge,
        "decision_date": date
    }]
    edges = []
    
    # 2. Extract Statutory Provisions (Section + Act)
    statutes_pattern = r"(?:Section|Sec\.)\s+([\d\w\s,\(\)]+?)\s+(?:of\s+the\s+)?([A-Z][A-Za-z0-9\s,\.\(\)]+?(?:Act|Code|Constitution)[^,\n]*)"
    found_statutes = set()
    for m in re.finditer(statutes_pattern, text):
        sec = m.group(1).strip()
        act = m.group(2).strip()
        if len(sec) < 30 and len(act) < 60:
            stat_id = f"STATUTE:{act}::Sec_{sec}"
            if stat_id not in found_statutes:
                found_statutes.add(stat_id)
                nodes.append({
                    "id": stat_id,
                    "type": "StatuteProvision",
                    "act": act,
                    "section": sec,
                    "label": f"{act} - Section {sec}"
                })
                edges.append({
                    "source": case_node_id,
                    "target": stat_id,
                    "relation": "INTERPRETS_STATUTE"
                })

    # 3. Extract Precedents Cited (Case Law Nodes)
    precedents_pattern = r"([A-Z][A-Za-z0-9\.\s&]+?\s+v(?:s)?\.\s+[A-Z][A-Za-z0-9\.\s&]+?)(?:,|\s|\n|\()"
    found_precedents = set()
    for m in re.finditer(precedents_pattern, text):
        case_cite = m.group(1).strip()
        if 10 < len(case_cite) < 80 and not case_cite.lower().startswith("state"):
            prec_id = f"PRECEDENT:{case_cite}"
            if prec_id not in found_precedents:
                found_precedents.add(prec_id)
                nodes.append({
                    "id": prec_id,
                    "type": "Precedent",
                    "label": case_cite
                })
                edges.append({
                    "source": case_node_id,
                    "target": prec_id,
                    "relation": "CITES_PRECEDENT"
                })

    # 4. Extract Legal Disposition & Strategy Path Outcome
    disposition = "PENDING / OTHER"
    outcome_status = "UNKNOWN"
    if re.search(r"dismissed\s+as\s+withdrawn", text, re.IGNORECASE):
        disposition = "DISMISSED AS WITHDRAWN"
        outcome_status = "WITHDRAWN"
    elif re.search(r"allowed|quashed|set\s+aside", text, re.IGNORECASE):
        disposition = "ALLOWED / QUASHED"
        outcome_status = "SUCCESSFUL_FOR_PETITIONER"
    elif re.search(r"dismissed", text, re.IGNORECASE):
        disposition = "DISMISSED"
        outcome_status = "FAILED_FOR_PETITIONER"

    outcome_node_id = f"OUTCOME:{cnr}"
    nodes.append({
        "id": outcome_node_id,
        "type": "Outcome",
        "disposition": disposition,
        "status": outcome_status,
        "label": f"Outcome: {disposition}"
    })
    edges.append({
        "source": case_node_id,
        "target": outcome_node_id,
        "relation": "RESULTED_IN"
    })
    
    # Connect precedents and statutes to outcome for strategy recommendations
    for stat_id in found_statutes:
        edges.append({
            "source": stat_id,
            "target": outcome_node_id,
            "relation": "STRATEGY_PATH_RESULT",
            "outcome_status": outcome_status
        })

    # 5. Extract Key Legal Issues / Rulings (Ratio)
    paragraphs = re.findall(r"(\n\d+\.\s+[^\n]+(?:\n(?!\d+\.)[^\n]+)*)", text)
    ratio_points = [p.strip() for p in paragraphs[:5]]
    
    ratio_node_id = f"RATIO:{cnr}"
    nodes.append({
        "id": ratio_node_id,
        "type": "JudicialRatio",
        "label": f"Ratio Decidendi ({cnr})",
        "ratio_summary": ratio_points
    })
    edges.append({
        "source": case_node_id,
        "target": ratio_node_id,
        "relation": "ARTICULATES_RATIO"
    })

    return {
        "cnr": cnr,
        "case_title": title,
        "court": court,
        "decision_date": date,
        "disposition": disposition,
        "knowledge_graph": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges
        }
    }

def main():
    parser = argparse.ArgumentParser(description="Ingest High Court Judgments into Legal Strategy Knowledge Graph")
    parser.add_argument("--court_code", type=str, default="7_26", help="Court code (e.g. 7_26 for Delhi HC)")
    parser.add_argument("--year", type=int, default=2026, help="Year (e.g. 2026)")
    parser.add_argument("--date", type=str, default="2026-07-31", help="Target date YYYY-MM-DD")
    parser.add_argument("--max_cases", type=int, default=5, help="Limit number of cases for demo")
    parser.add_argument("--output_dir", type=str, default="data/extracted_judgments", help="Output directory")
    
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load Parquet metadata
    meta_files = glob.glob(f"data/high_court_metadata/**/court={args.court_code}/**/*.parquet", recursive=True)
    if not meta_files:
        print(f"No metadata parquet found for court={args.court_code}")
        return

    dfs = [pd.read_parquet(f) for f in meta_files]
    df = pd.concat(dfs, ignore_index=True)
    df['date_str'] = df['decision_date'].dt.strftime('%Y-%m-%d')
    
    filtered_df = df[df['date_str'] == args.date].head(args.max_cases)
    print(f"[Filter] Selected {len(filtered_df)} case(s) for court={args.court_code}, date={args.date}...")

    # 2. Sync PDF tars from S3
    tar_files = download_s3_tar_archive(args.year, args.court_code, out_dir)
    target_links = set(filtered_df['pdf_link'].dropna().apply(os.path.basename))
    
    # 3. Extract text & build Knowledge Graph
    kg_results = []
    found_count = 0
    for tf in tar_files:
        try:
            with tarfile.open(tf, "r") as tar:
                for member in tar.getmembers():
                    fname = os.path.basename(member.name)
                    if fname in target_links:
                        fstream = tar.extractfile(member)
                        text = extract_pdf_text_from_stream(fstream)
                        rec = filtered_df[filtered_df['pdf_link'].str.endswith(fname)].iloc[0].to_dict()
                        rec["full_text"] = text
                        
                        kg_item = extract_legal_knowledge_graph(rec)
                        kg_results.append(kg_item)
                        found_count += 1
                        print(f"  ✓ Processed KG [{found_count}/{len(target_links)}]: {fname} ({kg_item['knowledge_graph']['node_count']} nodes, {kg_item['knowledge_graph']['edge_count']} edges)")
                        
                        if found_count >= args.max_cases:
                            break
        except Exception as e:
            print(f"Error reading tar {tf}: {e}")
        if found_count >= args.max_cases:
            break

    # 4. Save Knowledge Graph JSON
    save_file = out_dir / f"legal_strategy_kg_{args.court_code}_{args.date}.json"
    with open(save_file, "w", encoding="utf-8") as f:
        json.dump(kg_results, f, indent=2, ensure_ascii=False)

    print(f"\n[Done] Successfully built Legal Strategy Knowledge Graph for {len(kg_results)} cases.")
    print(f"[Saved] Output JSON: {save_file}")

if __name__ == "__main__":
    main()
