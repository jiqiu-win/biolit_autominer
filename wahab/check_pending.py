"""Show details of any articles still pending (gemini_processed=0) in the
2024-2025 batch -- useful for seeing exactly what's stuck and why.

Usage: .venv/bin/python3 wahab/check_pending.py
"""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db_path = ROOT / "auto_pipeline_output" / "articles.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT pmid, pmcid, title, local_file_path, error_message, updated_at
    FROM articles
    WHERE pub_date IN ('2024', '2025')
      AND (gemini_processed IS NULL OR gemini_processed = 0)
    """
).fetchall()
conn.close()

for row in rows:
    print(f"PMID:      {row['pmid']}")
    print(f"PMCID:     {row['pmcid']}")
    print(f"Title:     {row['title']}")
    print(f"File:      {row['local_file_path']}")
    print(f"Error:     {row['error_message']}")
    print(f"Updated:   {row['updated_at']}")
    print(f"File exists: {(ROOT / (row['local_file_path'] or '')).is_file()}")
    print("---")

if not rows:
    print("Nothing pending.")
