"""Run Gemini 2.5 extraction on downloaded PMC full-text files."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.article_database import ArticleDatabase
from biolit_autominer.config import config
from biolit_autominer.gemini_extraction_runner import GeminiExtractionRunner


def main():
    parser = argparse.ArgumentParser(description="Run Gemini extraction on downloaded articles")
    parser.add_argument("--pmids", nargs="+", default=[], help="Specific PMIDs to extract")
    parser.add_argument(
        "--all-unprocessed",
        action="store_true",
        help="Extract all PMC full-text articles not yet processed by Gemini",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Re-extract even if already done")
    args = parser.parse_args()

    config.setup()
    db = ArticleDatabase(config.DATABASE_PATH)
    runner = GeminiExtractionRunner(db)

    pmids = args.pmids
    if args.all_unprocessed:
        pmids = db.get_unprocessed_full_text_pmids(limit=args.limit)
    elif not pmids:
        pmids = db.get_unprocessed_full_text_pmids(limit=args.limit or 10)

    if not pmids:
        print("No articles pending Gemini extraction.")
        return 0

    print(f"Gemini 2.5 extraction for {len(pmids)} article(s)...")
    result = runner.run(pmids=pmids, force=args.force, limit=args.limit)
    print(f"Done: {len(result['processed'])} ok, {len(result['errors'])} errors")
    print(f"Output: {config.UPDATED_EXTRACTION_XLSX}")
    for err in result["errors"]:
        print(f"  ERROR PMID {err.get('pmid')}: {err.get('error')}")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
