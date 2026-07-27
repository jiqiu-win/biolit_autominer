"""Check Gemini extraction progress for the 2024-2025 backlog batch.

Usage: .venv/bin/python3 wahab/check_progress.py
"""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db_path = ROOT / "auto_pipeline_output" / "articles.db"

conn = sqlite3.connect(db_path)
rows = conn.execute(
    """
    SELECT gemini_processed, COUNT(*)
    FROM articles
    WHERE pub_date IN ('2024', '2025')
    GROUP BY gemini_processed
    """
).fetchall()
conn.close()

done = next((count for flag, count in rows if flag == 1), 0)
pending = next((count for flag, count in rows if flag in (0, None)), 0)
total = done + pending

print(f"Done:    {done}")
print(f"Pending: {pending}")
print(f"Total:   {total}")
if total:
    print(f"Progress: {100 * done / total:.1f}%")
