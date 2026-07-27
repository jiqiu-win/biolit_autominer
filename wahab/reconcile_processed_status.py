"""After a database rebuild + re-import, some articles may show
gemini_processed=0 even though they were actually already extracted --
if the corruption wiped their articles row but their findings survived.
This finds any article that has real findings but is marked unprocessed,
and corrects gemini_processed back to 1 so it doesn't get needlessly
(and expensively) re-sent to Gemini.

Usage: .venv/bin/python3 wahab/reconcile_processed_status.py
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.config import config

conn = sqlite3.connect(config.DATABASE_PATH)

mismatched = conn.execute(
    """
    SELECT DISTINCT a.pmid
    FROM articles a
    JOIN findings f ON f.pmid = a.pmid
    WHERE a.gemini_processed = 0 OR a.gemini_processed IS NULL
    """
).fetchall()

print(f"Found {len(mismatched)} article(s) with real findings but marked unprocessed.")

if mismatched:
    pmids = [row[0] for row in mismatched]
    conn.executemany(
        "UPDATE articles SET gemini_processed = 1 WHERE pmid = ?",
        [(p,) for p in pmids],
    )
    conn.commit()
    print(f"Corrected gemini_processed=1 for {len(pmids)} article(s).")
    print("Sample corrected PMIDs:", pmids[:10])
else:
    print("Nothing to reconcile -- all findings already correctly linked to processed articles.")

conn.close()
