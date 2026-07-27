"""Import the 40K+ PMC full-text backlog into articles.db.

Scans pmc_full_text/PMC_full_text_<year>/*.txt (already-downloaded articles,
not fetched via the pipeline's own download step) and registers each one as a
row in articles.db, so run_gemini_extraction.py can pick them up directly
without re-downloading.

Safe to re-run: inserts are idempotent (pmid is the primary key).

Usage:
    python scripts/import_pmc_backlog.py
    python scripts/import_pmc_backlog.py --year-start 1995 --year-end 2005
    python scripts/import_pmc_backlog.py --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.article_database import ArticleDatabase
from biolit_autominer.config import config

FILENAME_RE = re.compile(r"^(PMC\d+)_(\d+)_(.+)\.txt$")
YEAR_DIR_RE = re.compile(r"^PMC_full_text_(\d{4})$")
ABSTRACT_ONLY_MARKER = "[NOTE: Full text not available"


def parse_article(text_path, fallback_title):
    """Read title + full-text availability. Abstract-only files (PMC license
    restriction) start with a [NOTE: ...] marker before the Title: line, so we
    scan the first few lines rather than assuming Title: is always line 1."""
    lines = text_path.read_text(encoding="utf-8", errors="replace").splitlines()
    is_abstract_only = bool(lines) and lines[0].startswith(ABSTRACT_ONLY_MARKER)

    title = fallback_title
    for line in lines[:10]:
        if line.startswith("Title:"):
            candidate = line[len("Title:") :].strip()
            if candidate:
                title = candidate
            break

    return title, is_abstract_only


def main():
    parser = argparse.ArgumentParser(description="Import PMC full-text backlog into articles.db")
    parser.add_argument(
        "--source-dir",
        default=str(ROOT / "pmc_full_text"),
        help="Directory containing PMC_full_text_<year> subfolders",
    )
    parser.add_argument("--year-start", type=int, default=None, help="Only import years >= this")
    parser.add_argument("--year-end", type=int, default=None, help="Only import years <= this")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing to the DB")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        print(f"Source directory not found: {source_dir}")
        return 1

    config.setup()
    db = ArticleDatabase(config.DATABASE_PATH)

    year_dirs = sorted(d for d in source_dir.iterdir() if d.is_dir() and YEAR_DIR_RE.match(d.name))

    imported = 0
    skipped_pattern = 0
    abstract_only_count = 0
    for year_dir in year_dirs:
        year = int(YEAR_DIR_RE.match(year_dir.name).group(1))
        if args.year_start is not None and year < args.year_start:
            continue
        if args.year_end is not None and year > args.year_end:
            continue

        txt_files = sorted(year_dir.glob("*.txt"))
        print(f"{year_dir.name}: {len(txt_files)} files")
        for txt_path in txt_files:
            match = FILENAME_RE.match(txt_path.name)
            if not match:
                skipped_pattern += 1
                continue
            pmcid, pmid, slug = match.groups()
            title, is_abstract_only = parse_article(txt_path, slug.replace("_", " "))
            if is_abstract_only:
                abstract_only_count += 1

            if not args.dry_run:
                db.add_article(
                    pmid,
                    {
                        "pmcid": pmcid,
                        "title": title,
                        "pub_date": str(year),
                        "status": "new",
                        "has_full_text": 0 if is_abstract_only else 1,
                        "source": "pmc_backlog",
                        # Relative to BASE_DIR (project root), not absolute -- so
                        # this DB works unmodified after copying the project to a
                        # different machine (e.g. Wahab), where the absolute path
                        # to the repo differs. config.resolve_project_path() joins
                        # relative paths against BASE_DIR at read time.
                        "local_file_path": str(txt_path.resolve().relative_to(ROOT)),
                        # These files pre-existed on disk -- our pipeline never
                        # downloaded them, so there's no real download event to
                        # record. "not_applicable" is honest; "ok" would imply
                        # something happened that didn't.
                        "download_status": "not_applicable",
                    },
                )
            imported += 1

    print(f"\n{'Would import' if args.dry_run else 'Imported'}: {imported} article(s)")
    print(f"  of which abstract-only (has_full_text=0, publisher restriction): {abstract_only_count}")
    if skipped_pattern:
        print(f"Skipped (filename didn't match PMC<id>_<pmid>_<title>.txt): {skipped_pattern}")
    if not args.dry_run:
        db.print_stats()
    return 0


if __name__ == "__main__":
    sys.exit(main())
