"""
Daily PMC full-text download via AWS Cloud Service.

Saves new files to:
  auto_pipeline_output/updated/PMC_full_text_updated/txt/

After PMC_STAGING_AGE_DAYS (default 1), moves them to:
  downloaded/pmc_full_text/txt/

Schedule on macOS (cron example — runs every day at 9:00 AM):
  crontab -e
  0 9 * * * cd /Users/qiuji/Downloads/biolit_autominer && /usr/bin/python3 scripts/run_daily_pmc_aws.py >> logs/daily_pmc_aws.log 2>&1

Or run manually:
  python scripts/run_daily_pmc_aws.py
  python scripts/run_daily_pmc_aws.py --num_articles 20
  python scripts/run_daily_pmc_aws.py --archive-only
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.config import config
from biolit_autominer.pmc_daily_aws_downloader import PmcDailyAwsDownloader
from biolit_autominer.pmc_staging_manager import PmcStagingManager


def main():
    parser = argparse.ArgumentParser(
        description="Daily AWS PMC full-text download with staging → archive workflow"
    )
    parser.add_argument(
        "--query",
        default=None,
        help="PubMed search query (default: SEARCH_QUERY from prompts.py)",
    )
    parser.add_argument(
        "--num_articles",
        type=int,
        default=50,
        help="Max new/modified PMC articles to download per run",
    )
    parser.add_argument(
        "--max_results",
        type=int,
        default=200,
        help="Max PubMed IDs to inspect per search",
    )
    parser.add_argument(
        "--include_pmids",
        nargs="+",
        default=[],
        help="PMIDs to always include this run",
    )
    parser.add_argument(
        "--archive-only",
        action="store_true",
        help="Only move staged files older than PMC_STAGING_AGE_DAYS to archive",
    )
    parser.add_argument(
        "--staging-age-days",
        type=int,
        default=None,
        help="Days to keep files in staging before archive (default: env or 1)",
    )
    args = parser.parse_args()

    config.setup()

    from biolit_autominer.article_database import ArticleDatabase

    db = ArticleDatabase(config.DATABASE_PATH)
    staging = PmcStagingManager(age_days=args.staging_age_days)

    if args.archive_only:
        PmcStagingManager.migrate_flat_downloads_to_txt_subfolder()
        summary = staging.archive_staged_files(db=db)
        print(f"Archive-only run: moved {summary['moved_count']} file(s)")
        return

    downloader = PmcDailyAwsDownloader(db=db, staging=staging)
    summary = downloader.run_daily(
        search_query=args.query or config.DEFAULT_SEARCH_QUERY,
        max_results=args.max_results,
        process_limit=args.num_articles,
        include_pmids=args.include_pmids,
    )

    print("\nStaging folder:", summary["staging_dir"])
    print("Archive folder: ", summary["archive_dir"])
    print(f"Downloaded:      {summary['downloaded_count']}")
    print(f"Archived:        {summary['archive']['moved_count']}")
    if summary["downloaded"]:
        print("\nLatest downloads:")
        for item in summary["downloaded"][:5]:
            print(f"  PMID {item['pmid']} ({item.get('source_method')}) → {item['path']}")


if __name__ == "__main__":
    main()
