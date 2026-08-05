import argparse
import glob
import json
import os
import sys
import tarfile
from pathlib import Path
import pandas as pd
import pypdf
import subprocess

def download_s3_tar_archive(year: int, court_code: str, output_dir: Path) -> list[Path]:
    """Download tar archives for specific court and year from S3"""
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
    print(f"[1/4] Syncing PDF tar archives from {s3_path}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error syncing S3 tars: {res.stderr}")
        return []
    
    tar_files = list(tar_dir.rglob("*.tar"))
    print(f"Found {len(tar_files)} tar archives in {tar_dir}")
    return tar_files

def extract_pdf_text_from_stream(stream) -> str:
    """Extract plain text from a PDF file stream"""
    try:
        reader = pypdf.PdfReader(stream)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text.strip()
    except Exception as e:
        return f"ERROR_EXTRACTING_TEXT: {str(e)}"

def process_judgments(court_code: str, year: int, target_date: str = None, max_files: int = 20, output_dir: str = "data/extracted_judgments"):
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    # 1. Load Parquet metadata
    meta_path_glob = f"data/high_court_metadata/year={year}/court={court_code}/**/*.parquet"
    parquet_files = glob.glob(meta_path_glob, recursive=True)
    
    if not parquet_files:
        # Fallback to local 2025/2026 directory
        meta_path_glob = f"data/high_court_metadata/**/court={court_code}/**/*.parquet"
        parquet_files = glob.glob(meta_path_glob, recursive=True)
        
    if not parquet_files:
        print(f"No local metadata parquet found for court={court_code}, year={year}. Please run metadata download first.")
        return

    print(f"[Metadata] Loading {len(parquet_files)} parquet file(s)...")
    dfs = [pd.read_parquet(f) for f in parquet_files]
    df = pd.concat(dfs, ignore_index=True)
    
    # Filter by target date if specified
    if target_date:
        df['decision_date_str'] = df['decision_date'].dt.strftime('%Y-%m-%d')
        df = df[df['decision_date_str'] == target_date]
        print(f"[Filter] Records matching date '{target_date}': {len(df)}")
    
    if df.empty:
        print("No metadata records found matching criteria.")
        return
        
    target_records = df.head(max_files).to_dict(orient="records")
    target_pdf_links = set(r.get("pdf_link", "") for r in target_records if r.get("pdf_link"))
    target_filenames = set(os.path.basename(link) for link in target_pdf_links if link)
    
    print(f"[Filter] Targeting up to {len(target_records)} case(s)...")
    
    # 2. Sync PDF tars from S3
    tar_files = download_s3_tar_archive(year, court_code, out_path)
    if not tar_files:
        print("No tar archives downloaded.")
        return
        
    # 3. Extract target PDFs from tar files
    print("[2/4] Extracting PDF texts from tar archives...")
    extracted_results = []
    found_count = 0
    
    for tar_path in tar_files:
        try:
            with tarfile.open(tar_path, "r") as tar:
                for member in tar.getmembers():
                    pdf_name = os.path.basename(member.name)
                    if pdf_name in target_filenames:
                        # Extract PDF stream
                        f_stream = tar.extractfile(member)
                        if f_stream:
                            pdf_text = extract_pdf_text_from_stream(f_stream)
                            
                            # Match metadata record
                            rec = next((r for r in target_records if os.path.basename(r.get("pdf_link", "")) == pdf_name), {})
                            
                            res_item = {
                                "cnr": rec.get("cnr"),
                                "title": rec.get("title"),
                                "court": rec.get("court"),
                                "court_code": court_code,
                                "decision_date": str(rec.get("decision_date")),
                                "judge": rec.get("judge"),
                                "pdf_filename": pdf_name,
                                "character_count": len(pdf_text),
                                "full_text": pdf_text
                            }
                            extracted_results.append(res_item)
                            found_count += 1
                            print(f"  ✓ Extracted [{found_count}/{len(target_filenames)}]: {pdf_name} ({len(pdf_text)} chars)")
                            
                            if found_count >= max_files:
                                break
        except Exception as e:
            print(f"Error processing tar {tar_path}: {e}")
            
        if found_count >= max_files:
            break
            
    # 4. Save structured results
    date_suffix = f"_{target_date}" if target_date else ""
    save_file = out_path / f"extracted_{court_code}_{year}{date_suffix}.json"
    with open(save_file, "w", encoding="utf-8") as f_out:
        json.dump(extracted_results, f_out, indent=2, ensure_ascii=False)
        
    print(f"\n[3/4] Done! Successfully extracted {len(extracted_results)} full judgment texts.")
    print(f"[4/4] Saved results to: {save_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract full text from Indian High Court Judgment PDFs")
    parser.add_argument("--court_code", type=str, default="7_26", help="Court code (e.g. 7_26 for Delhi HC)")
    parser.add_argument("--year", type=int, default=2026, help="Year (e.g. 2026)")
    parser.add_argument("--date", type=str, default=None, help="Target decision date (YYYY-MM-DD)")
    parser.add_argument("--max_files", type=int, default=5, help="Maximum files to extract")
    parser.add_argument("--output_dir", type=str, default="data/extracted_judgments", help="Output directory")
    
    args = parser.parse_args()
    process_judgments(
        court_code=args.court_code,
        year=args.year,
        target_date=args.date,
        max_files=args.max_files,
        output_dir=args.output_dir
    )
