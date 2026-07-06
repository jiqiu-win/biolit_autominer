"""
Build or refresh the conference dataset from articles.db + Gemini cache.

Run manually anytime:
  python scripts/build_dataset.py

This is also called automatically at the end of each daily PMC run.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.article_database import ArticleDatabase
from biolit_autominer.config import config
from biolit_autominer.dataset_database import DatasetDatabase


def main():
    parser = argparse.ArgumentParser(description="Build Biolit conference dataset")
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Print dataset stats without rebuilding",
    )
    args = parser.parse_args()

    config.setup()
    article_db = ArticleDatabase(config.DATABASE_PATH)
    dataset_db = DatasetDatabase()

    if args.stats_only:
        stats = dataset_db.get_stats()
        print("Dataset stats:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return

    summary = dataset_db.sync_from_article_db(article_db)
    print("\nConference dataset ready:")
    print(f"  SQLite:  {summary['dataset_db']}")
    print(f"  Excel:   {summary['dataset_xlsx']}")
    print(f"  CSV:     {summary['findings_csv']}")
    print(f"           {summary['articles_csv']}")
    print(f"  Articles: {summary['article_count']}")
    print(f"  Findings: {summary['finding_count']}")


if __name__ == "__main__":
    main()
