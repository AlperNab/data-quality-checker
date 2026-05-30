# data-quality-checker

> **Any CSV, JSON, or TSV → AI data quality report.** Missing values, duplicates, format errors, outliers, schema violations, constant columns, freshness issues — with fix code snippets.

[![PyPI](https://img.shields.io/pypi/v/data-quality-checker?style=flat)](https://pypi.org/project/data-quality-checker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Quickstart

```bash
pip install data-quality-checker
python -m data_quality_checker data.csv
python -m data_quality_checker transactions.json --json
cat data.tsv | python -m data_quality_checker -
```

## What it detects

- **Missing values** — null %, pattern (random or systematic)
- **Duplicates** — exact rows + near-duplicates + likely primary key
- **Format errors** — emails that aren't emails, dates in wrong format
- **Outliers** — statistical anomalies in numeric columns
- **Constant columns** — single-value columns that add no information
- **High cardinality** — columns that probably shouldn't be free text
- **Schema inference** — likely PK, FK hints, date columns
- **Data freshness** — most recent date, staleness flags
- Every issue includes a **Python/SQL fix snippet**

## License
MIT © [Alper Nabil Gabra Zakher](https://github.com/AlperNab)
