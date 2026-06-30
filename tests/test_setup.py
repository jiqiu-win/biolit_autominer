"""
Task 1 helper: verify imports, create a test database, and add sample articles.
"""

from pathlib import Path

from biolit_autominer import (
    ArticleDatabase,
    EnhancedAutoPipeline,
    IncrementalSync,
    IncrementalUpdateManager,
    PubMedScraper,
)
from biolit_autominer.config import config


SAMPLE_ARTICLES = [
    {
        "pmid": "10000001",
        "title": "Mitochondrial dysfunction in drug-induced hepatotoxicity",
        "authors": "Smith, John; Doe, Jane",
        "journal": "Journal of Hepatology",
        "pub_date": "2024-01-15",
        "abstract": "This review discusses mitochondrial mechanisms in hepatotoxicity.",
        "status": "new",
        "has_full_text": 1,
        "source": "pmc",
        "full_text_url": "https://example.org/fulltext/1",
    },
    {
        "pmid": "10000002",
        "title": "Reactive oxygen species and liver injury",
        "authors": "Lee, Amy",
        "journal": "Free Radical Biology and Medicine",
        "pub_date": "2023-11-02",
        "abstract": "ROS signaling in hepatocyte injury models.",
        "status": "new",
        "has_full_text": 0,
    },
    {
        "pmid": "10000003",
        "title": "Acetaminophen hepatotoxicity pathways",
        "authors": "Brown, Chris; Kim, Min",
        "journal": "Toxicological Sciences",
        "pub_date": "2022-08-20",
        "abstract": "Mechanistic overview of APAP-induced liver injury.",
        "status": "processed",
        "has_full_text": 1,
        "source": "elsevier",
        "full_text_url": "https://example.org/fulltext/3",
    },
    {
        "pmid": "10000004",
        "title": "Mitochondrial permeability transition in liver disease",
        "authors": "Garcia, Maria",
        "journal": "Cell Death and Disease",
        "pub_date": "2024-03-10",
        "abstract": "MPT pore activation in hepatocytes.",
        "status": "new",
        "has_full_text": 1,
        "source": "nature",
    },
    {
        "pmid": "10000005",
        "title": "Biomarkers for idiosyncratic drug-induced liver injury",
        "authors": "Patel, Ravi; Nguyen, Linh",
        "journal": "Clinical Pharmacology and Therapeutics",
        "pub_date": "2021-06-05",
        "abstract": "Candidate biomarkers for DILI prediction.",
        "status": "modified",
        "has_full_text": 0,
    },
]


def run_setup_test():
    test_dir = config.OUTPUT_DIR / "test_run"
    test_dir.mkdir(parents=True, exist_ok=True)
    db_path = test_dir / "test_articles.db"

    print("Step 1: Import check")
    modules = [
        ArticleDatabase,
        PubMedScraper,
        IncrementalSync,
        IncrementalUpdateManager,
        EnhancedAutoPipeline,
    ]
    for module in modules:
        print(f"  OK  {module.__name__}")

    print("\nStep 2: Create test database")
    db = ArticleDatabase(db_path)

    print("\nStep 3: Add 5 sample articles")
    for article in SAMPLE_ARTICLES:
        article["content_hash"] = ArticleDatabase.compute_content_hash(article)
        db.add_article(article["pmid"], article)
        print(f"  Added PMID {article['pmid']}: {article['title'][:50]}...")

    print("\nStep 4: Verify database contents")
    db.print_stats()

    excel_path = test_dir / "test_articles.xlsx"
    db.export_to_excel(excel_path)

    print("\nCreated files:")
    for path in sorted(test_dir.iterdir()):
        print(f"  - {path}")

    return test_dir


if __name__ == "__main__":
    config.setup()
    run_setup_test()
