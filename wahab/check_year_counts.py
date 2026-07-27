"""Show article counts per year -- use this to decide date ranges for batching.

Usage: .venv/bin/python3 wahab/check_year_counts.py
"""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db_path = ROOT / "auto_pipeline_output" / "articles.db"

conn = sqlite3.connect(db_path)
rows = conn.execute(
    """
    SELECT pub_date,
           COUNT(*) AS total,
           SUM(CASE WHEN gemini_processed = 1 THEN 1 ELSE 0 END) AS done,
           SUM(CASE WHEN has_full_text = 1 THEN 1 ELSE 0 END) AS full_text
    FROM articles
    WHERE source = 'pmc_backlog'
    GROUP BY pub_date
    ORDER BY pub_date
    """
).fetchall()
conn.close()

print(f"{'Year':<8}{'Total':>8}{'Done':>8}{'Full-text':>12}")
grand_total = grand_done = 0
for pub_date, total, done, full_text in rows:
    print(f"{pub_date:<8}{total:>8}{done:>8}{full_text:>12}")
    grand_total += total
    grand_done += done

print("-" * 36)
print(f"{'TOTAL':<8}{grand_total:>8}{grand_done:>8}")
