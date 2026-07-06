"""
Daily PMC full-text download via AWS Cloud Service.

Saves new files to:
  auto_pipeline_output/updated/PMC_full_text_updated/txt/   (visible immediately)

After PMC_STAGING_AGE_DAYS (default 1), moves them to:
  downloaded/pmc_full_text/txt/

Also writes:
  auto_pipeline_output/updated/YYYY-MM-DD_summary.json
  auto_pipeline_output/articles_database.xlsx

Schedule on macOS (cron — fixed daily time, default 9:00 AM):
  crontab -e
  0 9 * * * cd /Users/qiuji/Downloads/biolit_autominer && /usr/bin/python3 scripts/run_daily_pmc_aws.py >> logs/daily_pmc_aws.log 2>&1

Or run manually anytime (no need to wait until tomorrow):
  python scripts/run_daily_pmc_aws.py
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
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="Skip Gemini 2.5 extraction after download",
    )
    parser.add_argument(
        "--gemini-force",
        action="store_true",
        help="Re-run Gemini even if already processed",
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
        run_gemini=not args.no_gemini,
        gemini_force=args.gemini_force,
    )

    diagnosis = summary.get("diagnosis", {})
    timing = summary.get("timing", {})

    print("\n" + "=" * 60)
    print("DAILY RUN SUMMARY")
    print("=" * 60)
    print(f"Status:          {diagnosis.get('status')}")
    print(f"Responsibility:  {diagnosis.get('responsibility')}")
    print(f"Message:         {diagnosis.get('user_message')}")
    print()
    print(f"Scheduled time:  {timing.get('scheduled_run_time')} (if cron is configured)")
    print(f"Staging folder:  {summary['staging_dir']}  ← new files appear HERE immediately")
    print(f"Archive folder:  {summary['archive_dir']}  ← after {timing.get('archive_after_days')} day(s)")
    print(f"Downloaded:      {summary['downloaded_count']}")
    if summary.get("target_count"):
        print(f"Target:          {summary['target_count']}")
    print(f"Skipped (exist): {summary.get('skipped_already_downloaded_count', 0)}")
    print(f"Archived:        {summary['archive']['moved_count']}")
    print(f"Summary JSON:    {summary.get('summary_json_path')}")
    print(f"Excel database:  {summary.get('excel_path')}")
    print(f"Extraction xlsx: {summary.get('extraction_xlsx_path')}")
    print(f"Dataset xlsx:    {summary.get('dataset_xlsx_path')}")
    gemini = summary.get("gemini_extraction", {})
    if gemini:
        print(
            f"Gemini:          {len(gemini.get('processed', []))} extracted, "
            f"{len(gemini.get('errors', []))} errors"
        )

    if summary["downloaded"]:
        print("\nLatest downloads:")
        for item in summary["downloaded"][:5]:
            print(f"  PMID {item['pmid']} ({item.get('source_method')}) → {item['path']}")

    if summary.get("abstract_only"):
        print("\nAbstract-only (PMC license limitation, not our code):")
        for item in summary["abstract_only"][:3]:
            print(f"  PMID {item['pmid']}: {item.get('diagnosis_code')}")


if __name__ == "__main__":
    main()
