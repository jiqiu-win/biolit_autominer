"""
Biolit AutoMiner - Automated Biomedical Literature Mining Pipeline
"""

__version__ = "1.0.0"
__author__ = "Ji Qiu"
__license__ = "MIT"

from .article_database import ArticleDatabase
from .pubmed_scraper import PubMedScraper, FullTextDownloader
from .incremental_sync import IncrementalSync
from .enhanced_auto_pipeline import EnhancedAutoPipeline

__all__ = [
    "ArticleDatabase",
    "PubMedScraper",
    "FullTextDownloader",
    "IncrementalSync",
    "EnhancedAutoPipeline",
]

print(f"✓ Biolit AutoMiner v{__version__} loaded")
