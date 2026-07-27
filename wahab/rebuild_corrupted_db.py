"""Rebuild a clean database from a corrupted one, by reading out everything
still readable and writing it into a brand-new file with the same schema.

Row-by-row, not one bulk query -- a single "SELECT * FROM articles" hits the
corrupted pages and fails entirely. Fetching one row at a time means a single
damaged row can be skipped without losing everything else around it.

Does not touch the corrupted original -- writes to a new file, verified with
an integrity check before you swap it in.

Usage: .venv/bin/python3 wahab/rebuild_corrupted_db.py
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.article_database import ArticleDatabase

CORRUPTED_PATH = ROOT / "auto_pipeline_output" / "articles.db"
REBUILT_PATH = ROOT / "auto_pipeline_output" / "articles_rebuilt.db"

if REBUILT_PATH.exists():
    REBUILT_PATH.unlink()

print(f"Reading from: {CORRUPTED_PATH}")
print(f"Writing to:   {REBUILT_PATH}")

src = sqlite3.connect(CORRUPTED_PATH)
src.row_factory = sqlite3.Row

dst_db = ArticleDatabase(REBUILT_PATH)
dst = sqlite3.connect(REBUILT_PATH)

articles_cols = [row[1] for row in src.execute("PRAGMA table_info(articles)")]
findings_cols = [row[1] for row in src.execute("PRAGMA table_info(findings)")]
findings_cols_no_id = [c for c in findings_cols if c != "id"]

# --- Step 1: get the list of PMIDs. If even this fails, corruption is severe
# enough that we'd need a different recovery strategy entirely. ---
try:
    pmids = [row[0] for row in src.execute("SELECT pmid FROM articles ORDER BY pmid")]
    print(f"PMID list readable: {len(pmids)} articles to attempt")
except Exception as exc:
    print(f"FATAL: even the pmid list is unreadable: {exc}")
    sys.exit(1)

# --- Step 2: fetch + copy each article one at a time ---
placeholders = ",".join("?" for _ in articles_cols)
copied = skipped = 0
skipped_pmids = []
for i, pmid in enumerate(pmids):
    try:
        row = src.execute(
            f"SELECT {','.join(articles_cols)} FROM articles WHERE pmid = ?", (pmid,)
        ).fetchone()
        if row is None:
            continue
        dst.execute(
            f"INSERT OR REPLACE INTO articles ({','.join(articles_cols)}) VALUES ({placeholders})",
            tuple(row),
        )
        copied += 1
    except Exception as exc:
        skipped += 1
        skipped_pmids.append(pmid)
        if skipped <= 20:
            print(f"  skipped article pmid={pmid}: {exc}")
    if (i + 1) % 5000 == 0:
        dst.commit()
        print(f"  ...{i + 1}/{len(pmids)} attempted so far ({copied} copied, {skipped} skipped)")

dst.commit()
print(f"\nArticles: {copied} copied, {skipped} skipped")
if skipped_pmids:
    print(f"Skipped PMIDs (first 20 shown above), full list has {len(skipped_pmids)} entries")

# --- Step 3: findings, same row-by-row approach ---
try:
    finding_ids = [row[0] for row in src.execute("SELECT id FROM findings ORDER BY id")]
    print(f"\nFinding ID list readable: {len(finding_ids)} findings to attempt")
except Exception as exc:
    print(f"Findings id list unreadable: {exc}")
    finding_ids = []

placeholders2 = ",".join("?" for _ in findings_cols_no_id)
copied_f = skipped_f = 0
for fid in finding_ids:
    try:
        row = src.execute(
            f"SELECT {','.join(findings_cols_no_id)} FROM findings WHERE id = ?", (fid,)
        ).fetchone()
        if row is None:
            continue
        dst.execute(
            f"INSERT OR REPLACE INTO findings ({','.join(findings_cols_no_id)}) VALUES ({placeholders2})",
            tuple(row),
        )
        copied_f += 1
    except Exception as exc:
        skipped_f += 1
        if skipped_f <= 20:
            print(f"  skipped finding id={fid}: {exc}")

dst.commit()
print(f"Findings: {copied_f} copied, {skipped_f} skipped")

src.close()
dst.close()

check_conn = sqlite3.connect(REBUILT_PATH)
result = check_conn.execute("PRAGMA integrity_check;").fetchall()
check_conn.close()
print("\nIntegrity check on rebuilt file:")
for row in result:
    print(" ", row[0][:200])

print(f"\nDone. Rebuilt file: {REBUILT_PATH}")
