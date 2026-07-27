"""Export the consolidated database (articles + findings) to one spreadsheet.

Usage: python3 scripts/export_dataset.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.article_database import ArticleDatabase
from biolit_autominer.config import config
from biolit_autominer.dataset_export import export_dataset

if __name__ == "__main__":
    db = ArticleDatabase(config.DATABASE_PATH)
    export_dataset(db, config.OUTPUT_DIR / "biolit_dataset.xlsx")
