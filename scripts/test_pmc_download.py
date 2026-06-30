"""Re-download one PMC article to verify HTML/PDF fallback."""

import argparse

from biolit_autominer.config import config
from biolit_autominer.incremental_sync import IncrementalSync
from biolit_autominer.pubmed_scraper import FullTextDownloader


def main():
    parser = argparse.ArgumentParser(description="Test PMC full-text fallback download")
    parser.add_argument("--pmid", default="39301884")
    parser.add_argument("--pmcid", default="PMC11559786")
    args = parser.parse_args()

    config.setup()
    sync = IncrementalSync()
    downloader = FullTextDownloader()

    metadata = sync.fetch_metadata(args.pmid)
    result = downloader.download_article(args.pmid, args.pmcid, metadata)

    print("Saved:", result.get("saved"))
    print("Source:", result.get("content_source"))
    print("Path:", result.get("path"))
    if result.get("path"):
        text = result["path"].read_text(encoding="utf-8")
        print("Preview:")
        print(text[:500])
        print("...")
        print("Word count:", len(text.split()))


if __name__ == "__main__":
    main()
