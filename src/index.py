#!/usr/bin/env python3
"""
data-quality-checker — CSV/JSON/DB connection → AI finds anomalies,
duplicates, format errors, statistical outliers, schema violations,
referential integrity issues, data freshness problems
"""
import anthropic, csv, io, json, re, sys
from pathlib import Path
from collections import defaultdict

SYSTEM = """You are a senior data engineer and analytics quality specialist.
Analyze this dataset for quality issues with precision and actionable recommendations.

Return ONLY valid JSON — no markdown, no explanation.

{
  "dataset_summary": {
    "rows": number,
    "columns": number,
    "file_size_kb": number_or_null,
    "detected_format": "csv|json|tsv|excel|sql_dump",
    "encoding_issues": true_or_false
  },
  "overall_quality_score": number_0_to_100,
  "quality_grade": "A|B|C|D|F",
  "column_profiles": [
    {
      "column": "column name",
      "dtype_detected": "string|integer|float|date|boolean|email|phone|url|mixed|empty",
      "null_count": number,
      "null_pct": number,
      "unique_count": number,
      "unique_pct": number,
      "sample_values": ["up to 5 representative values"],
      "issues": ["list of issues found in this column"],
      "stats": {
        "min": "string or null",
        "max": "string or null",
        "mean": "string or null",
        "most_common": "string or null"
      }
    }
  ],
  "issues": [
    {
      "type": "missing_values|duplicates|format_error|outlier|inconsistency|referential|schema|freshness|encoding",
      "severity": "critical|high|medium|low",
      "column": "string or null",
      "description": "what the issue is",
      "affected_rows": number_or_null,
      "affected_pct": number_or_null,
      "example": "string showing the problem",
      "fix": "specific SQL, Python, or pandas command to fix it",
      "root_cause": "likely cause of this issue"
    }
  ],
  "duplicates": {
    "exact_duplicate_rows": number,
    "near_duplicate_groups": number,
    "duplicate_key_columns": ["columns that together form a likely key"],
    "sample_duplicate": "string example"
  },
  "schema_inference": {
    "likely_primary_key": "column or composite key",
    "date_columns": ["list"],
    "foreign_key_hints": ["column that looks like a foreign key"]
  },
  "statistical_summary": {
    "numeric_columns": number,
    "text_columns": number,
    "date_columns": number,
    "high_cardinality_columns": ["columns with >50% unique values"],
    "low_cardinality_columns": ["columns with <5% unique values — potential categoricals"],
    "constant_columns": ["columns with only 1 unique value — likely useless"],
    "high_null_columns": ["columns with >20% nulls"]
  },
  "recommendations": [
    {
      "priority": "immediate|soon|optional",
      "action": "specific fix description",
      "code_hint": "Python/SQL snippet"
    }
  ],
  "data_freshness": {
    "most_recent_date": "string or null",
    "oldest_date": "string or null",
    "freshness_concern": true_or_false,
    "notes": "string or null"
  },
  "confidence": 0.0
}"""

def profile_csv(text: str) -> dict:
    """Quick local profiling before sending to Claude."""
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows: return {}
    cols = list(rows[0].keys())
    profile = {"rows": len(rows), "cols": cols, "sample": rows[:5]}
    # Count nulls per column
    null_counts = defaultdict(int)
    for row in rows:
        for col in cols:
            if not row.get(col,"").strip():
                null_counts[col] += 1
    profile["null_counts"] = dict(null_counts)
    return profile

def check(source: str, sample_rows: int = 500) -> dict:
    client = anthropic.Anthropic()
    path = Path(source)

    if path.exists():
        suffix = path.suffix.lower()
        if suffix in (".csv",".tsv",".txt"):
            raw = path.read_text(encoding="utf-8", errors="replace")
            # Sample if large
            lines = raw.split("\n")
            if len(lines) > sample_rows + 1:
                sampled = "\n".join([lines[0]] + lines[1:sample_rows+1])
                note = f"\n[Note: showing first {sample_rows} of {len(lines)-1} rows]"
            else:
                sampled = raw
                note = ""
            text = sampled[:40000] + note
        elif suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8",errors="replace"))
            if isinstance(data, list) and len(data) > sample_rows:
                data = data[:sample_rows]
            text = json.dumps(data[:sample_rows] if isinstance(data,list) else data, indent=2)[:40000]
        else:
            text = path.read_text(encoding="utf-8",errors="replace")[:40000]
        filename = path.name
    else:
        text = source[:40000]
        filename = "data"

    prompt = f"Dataset filename: {filename}\n\nData:\n{text}"
    resp = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=4096, system=SYSTEM,
        messages=[{"role":"user","content":f"Check data quality of this dataset:\n\n{prompt}"}]
    )
    raw = re.sub(r'^```(?:json)?\s*','',resp.content[0].text.strip(),flags=re.MULTILINE)
    raw = re.sub(r'\s*```$','',raw,flags=re.MULTILINE)
    return json.loads(raw)

def check_text(text: str) -> dict:
    return check.__wrapped__(text) if hasattr(check,'__wrapped__') else check(text)

GRADE_C = {"A":"\033[92m","B":"\033[92m","C":"\033[93m","D":"\033[91m","F":"\033[91m"}
SEV_ICON = {"critical":"🚨","high":"🔴","medium":"🟠","low":"🔵"}
R = "\033[0m"

def print_report(r: dict):
    ds = r.get("dataset_summary",{})
    grade = r.get("quality_grade","?")
    score = r.get("overall_quality_score",0)
    stats = r.get("statistical_summary",{})

    print(f"\n{'═'*60}")
    print(f"  DATA QUALITY REPORT")
    print(f"  {ds.get('rows',0):,} rows × {ds.get('columns',0)} columns | Format: {ds.get('detected_format','?')}")
    print(f"  Quality: {GRADE_C.get(grade,'')}{grade}{R} ({score}/100)")
    print(f"{'═'*60}")

    issues = r.get("issues",[])
    if issues:
        sorted_issues = sorted(issues, key=lambda x: ["critical","high","medium","low"].index(x.get("severity","low")))
        print(f"\n  ISSUES ({len(issues)} found)")
        for iss in sorted_issues:
            col = f" [{iss['column']}]" if iss.get("column") else ""
            pct = f" ({iss['affected_pct']:.1f}%)" if iss.get("affected_pct") else ""
            rows_str = f" — {iss['affected_rows']:,} rows{pct}" if iss.get("affected_rows") else ""
            print(f"\n  {SEV_ICON.get(iss.get('severity','low'),'')} {iss.get('type','?').upper()}{col}{rows_str}")
            print(f"     {iss.get('description','')}")
            if iss.get("example"): print(f"     Example: {str(iss['example'])[:80]}")
            if iss.get("fix"): print(f"     Fix: {iss['fix'][:100]}")

    dups = r.get("duplicates",{})
    if dups.get("exact_duplicate_rows",0) > 0:
        print(f"\n  DUPLICATES")
        print(f"  Exact duplicate rows: {dups.get('exact_duplicate_rows',0):,}")
        if dups.get("duplicate_key_columns"): print(f"  Key columns: {', '.join(dups['duplicate_key_columns'])}")

    col_profiles = r.get("column_profiles",[])
    high_null = [c for c in col_profiles if c.get("null_pct",0) > 20]
    if high_null:
        print(f"\n  HIGH NULL COLUMNS (>20%)")
        for col in high_null:
            print(f"  {col.get('column','?'):<25} {col.get('null_pct',0):.1f}% nulls ({col.get('null_count',0):,} rows)")

    if stats.get("constant_columns"):
        print(f"\n  CONSTANT (useless) COLUMNS: {', '.join(stats['constant_columns'])}")

    recs = r.get("recommendations",[])
    immediate = [r2 for r2 in recs if r2.get("priority")=="immediate"]
    if immediate:
        print(f"\n  IMMEDIATE ACTIONS")
        for rec in immediate:
            print(f"  ⚡ {rec.get('action','')}")
            if rec.get("code_hint"): print(f"     {rec['code_hint'][:100]}")

    schema = r.get("schema_inference",{})
    if schema.get("likely_primary_key"): print(f"\n  Likely PK: {schema['likely_primary_key']}")
    fresh = r.get("data_freshness",{})
    if fresh.get("freshness_concern"): print(f"  ⚠ Freshness: {fresh.get('notes','data may be stale')}")
    print(f"\n  Confidence: {int(r.get('confidence',0)*100)}%")
    print(f"{'═'*60}\n")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Check data quality of any CSV, JSON, or TSV file")
    p.add_argument("source", help="CSV/JSON/TSV file path or '-' for stdin")
    p.add_argument("--sample","-n",type=int,default=500,help="Max rows to analyze (default 500)")
    p.add_argument("--json",action="store_true")
    a = p.parse_args()
    src = sys.stdin.read() if a.source=="-" else a.source
    r = check(src, a.sample)
    if a.json: print(json.dumps(r,indent=2,ensure_ascii=False))
    else: print_report(r)
