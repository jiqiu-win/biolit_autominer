"""
End-to-end demo: PMC AWS Cloud Service (TXT) → Gemini 2.5 extraction.

Success criteria:
  1. Download full text from s3://pmc-oa-opendata as .txt
  2. Save to downloaded/pmc_full_text/
  3. Gemini 2.5 extracts bracket-format key info (not "No results")

Usage:
  python scripts/demo_aws_gemini.py
  python scripts/demo_aws_gemini.py --pmcid PMC13114090 --pmid 42072677
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.config import config
from biolit_autominer.file_formatter import format_pmc_fulltext_file
from biolit_autominer.multi_llm_extractor import MultiLLMExtractor
from biolit_autominer.pmc_aws_fetcher import PMCAwsFetcher, S3_HTTPS_BASE
from biolit_autominer.prompts import build_prompt
from biolit_autominer.pubmed_scraper import FullTextDownloader


def download_pmc_txt_from_aws(pmcid, pmid, title=""):
    """
    Download PMC full text TXT directly from AWS Cloud Service.

    Flow (per https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/):
      metadata/{PMCID}.{version}.json  →  text_url  →  HTTPS GET  →  .txt body
    """
    fetcher = PMCAwsFetcher(parse_pmc_xml=FullTextDownloader()._parse_pmc_xml)
    pmcid = config.format_pmcid(pmcid)

    versions = fetcher.list_article_versions(pmcid)
    if not versions:
        raise RuntimeError(f"{pmcid} not found in AWS bucket pmc-oa-opendata")

    version = versions[-1]
    metadata = fetcher.fetch_metadata(pmcid, version)
    if not metadata:
        raise RuntimeError(f"No metadata for {pmcid}.{version}")

    text_url = fetcher._s3_url_to_https(metadata.get("text_url"))
    if not text_url:
        raise RuntimeError(f"No text_url in metadata for {pmcid}.{version}")

    txt_bytes = fetcher._get_bytes(text_url)
    if not txt_bytes:
        raise RuntimeError(f"Failed to download TXT from {text_url}")

    body = fetcher.extract_body_from_aws_txt(txt_bytes)
    word_count = len(body.split())
    if word_count < fetcher.MIN_FULLTEXT_WORDS:
        raise RuntimeError(f"TXT too short ({word_count} words) — not full text")

    resolved_title = title or metadata.get("title") or "Untitled"
    out_path = config.pmc_staging_path(pmid, pmcid, resolved_title)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        format_pmc_fulltext_file(resolved_title, body),
        encoding="utf-8",
    )

    return {
        "pmcid": pmcid,
        "pmid": pmid,
        "version": version,
        "license": metadata.get("license_code"),
        "source_method": "pmc_aws_txt",
        "text_url": text_url,
        "s3_prefix": f"{S3_HTTPS_BASE}/{pmcid}.{version}/",
        "path": out_path,
        "word_count": word_count,
        "title": resolved_title,
        "body": body,
    }


def extract_with_gemini(title, text):
    """Run Gemini 2.5 via Vertex AI using notebook-standard build_prompt()."""
    extractor = MultiLLMExtractor()
    prompt = build_prompt(text[: config.GEMINI_MAX_TEXT_CHARS], title)
    return extractor.extract_full_prompt(prompt)


def main():
    parser = argparse.ArgumentParser(description="Demo: AWS PMC TXT download + Gemini extraction")
    parser.add_argument("--pmcid", default="PMC13114090")
    parser.add_argument("--pmid", default="42072677")
    parser.add_argument("--title", default="")
    parser.add_argument("--skip-gemini", action="store_true")
    args = parser.parse_args()

    config.setup()

    print("=" * 60)
    print("STEP 1: Download PMC full text TXT from AWS Cloud Service")
    print("=" * 60)
    download = download_pmc_txt_from_aws(args.pmcid, args.pmid, args.title)
    print(f"  PMCID:         {download['pmcid']}")
    print(f"  Version:       {download['version']}")
    print(f"  License:       {download['license']}")
    print(f"  Source:        {download['source_method']}")
    print(f"  S3 prefix:     {download['s3_prefix']}")
    print(f"  TXT URL:       {download['text_url']}")
    print(f"  Saved to:      {download['path']}")
    print(f"  Word count:    {download['word_count']}")
    print("  ✓ AWS TXT download OK")

    if args.skip_gemini:
        return

    print()
    print("=" * 60)
    print("STEP 2: Gemini 2.5 extraction")
    print("=" * 60)
    result = extract_with_gemini(download["title"], download["body"])
    if result.get("status") != "success":
        print(f"  ✗ Gemini failed: {result.get('error')}")
        sys.exit(1)

    raw = result.get("raw_response", "").strip()
    print(f"  Model:         {result.get('model')}")
    print(f"  Response preview:")
    print("-" * 40)
    print(raw[:1500])
    if len(raw) > 1500:
        print("...")
    print("-" * 40)

    if raw.lower() == "no results" or not raw.startswith("["):
        print("  ✗ Extraction did not return bracket-format key info")
        sys.exit(1)

    print("  ✓ Gemini extraction OK (bracket-format rows returned)")
    print()
    print("SUCCESS: AWS Cloud Service TXT download + Gemini extraction both passed.")


if __name__ == "__main__":
    main()
