"""Rebuild full_text_extraction.xlsx from whatever's already in articles.db.

For catching up a spreadsheet after a job was killed before its own export
ran (or before it hit a checkpoint) -- reads gemini_result straight from the
DB (already saved per-article, incrementally, regardless of which run did the
work) and regenerates rows from that. Safe to run anytime, including while
another job is still running, and safe to re-run repeatedly (the underlying
export dedups on chemical+marker+result+evidence).

Usage: .venv/bin/python3 wahab/rebuild_workbook.py
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.config import config
from biolit_autominer.extraction_exporter import export_extraction_workbook, rows_from_gemini_text

conn = sqlite3.connect(config.DATABASE_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.execute(
    """
    SELECT pmid, pmcid, title, gemini_result
    FROM articles
    WHERE gemini_processed = 1
      AND source LIKE 'pmc%'
      AND gemini_result IS NOT NULL
    ORDER BY pmid
    """
)
rows = cursor.fetchall()
conn.close()

print(f"Found {len(rows)} processed article(s) with a cached Gemini result.")

all_extraction_rows = []
for row in rows:
    source_file = config.pmc_filename(row["pmid"], row["pmcid"], row["title"] or "")
    all_extraction_rows.extend(rows_from_gemini_text(source_file, row["gemini_result"]))

print(f"Parsed {len(all_extraction_rows)} extraction row(s) across those articles.")
export_extraction_workbook(all_extraction_rows)
