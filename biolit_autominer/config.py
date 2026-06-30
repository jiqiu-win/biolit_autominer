import os
from pathlib import Path

from dotenv import load_dotenv

# Project root: biolit_autominer/ (one level above this package folder)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    NCBI_EMAIL = os.getenv("NCBI_EMAIL", "jq2430@columbia.edu")
    NCBI_API_KEY = os.getenv("NCBI_API_KEY")
    NCBI_SLEEP_TIME = 0.1 if NCBI_API_KEY else 0.34

    GEMINI_PROJECT_ID = os.getenv("GEMINI_PROJECT_ID", "rs-vertexai-czhu")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TEMPERATURE = 0.0

    # Pipeline outputs (inside auto_pipeline_output/)
    OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "auto_pipeline_output")))
    UPDATED_DIR = OUTPUT_DIR / "updated"
    UPDATED_PMC = UPDATED_DIR / "PMC_full_text_updated"
    UPDATED_ABSTRACTS = UPDATED_DIR / "Pubmed_abstracts_updated"

    DATABASE_PATH = OUTPUT_DIR / "articles.db"
    EXCEL_OUTPUT = OUTPUT_DIR / "articles_database.xlsx"
    SYNC_HISTORY_PATH = OUTPUT_DIR / "sync_history.json"

    # Raw downloads (outside auto_pipeline_output/, project root)
    DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", str(BASE_DIR / "downloads")))
    DOWNLOADS_PMC = DOWNLOADS_DIR / "PMC_full_text"
    DOWNLOADS_ABSTRACTS = DOWNLOADS_DIR / "Pubmed_abstracts"

    # Gemini 2.5 extractions (outside auto_pipeline_output/, project root)
    GEMINI_CACHE_DIR = Path(os.getenv("GEMINI_CACHE_DIR", str(BASE_DIR / "gemini_raw_cache")))
    GEMINI_CACHE_PMC = GEMINI_CACHE_DIR / "PMC_full_text"
    GEMINI_CACHE_ABSTRACTS = GEMINI_CACHE_DIR / "Pubmed_abstracts"

    UPDATE_FREQUENCY = os.getenv("UPDATE_FREQUENCY", "daily")

    # Legacy aliases
    RAW_TEXT_CACHE = DOWNLOADS_DIR
    GEMINI_CACHE = GEMINI_CACHE_DIR

    DEFAULT_SEARCH_QUERY = "hepatotoxicity AND mitochondrial"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def setup(cls):
        folders = [
            cls.OUTPUT_DIR,
            cls.UPDATED_PMC,
            cls.UPDATED_ABSTRACTS,
            cls.DOWNLOADS_PMC,
            cls.DOWNLOADS_ABSTRACTS,
            cls.GEMINI_CACHE_PMC,
            cls.GEMINI_CACHE_ABSTRACTS,
        ]
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
        print("Configuration validated")

    @staticmethod
    def format_pmcid(pmcid):
        pmcid = str(pmcid).strip()
        if not pmcid:
            return pmcid
        return pmcid if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"

    @classmethod
    def pmc_filename(cls, pmid, pmcid):
        return f"{cls.format_pmcid(pmcid)}_{pmid}.txt"

    @classmethod
    def abstract_filename(cls, pmid):
        return f"PM{pmid}_abstract.txt"

    @classmethod
    def pmc_download_path(cls, pmid, pmcid):
        return cls.DOWNLOADS_PMC / cls.pmc_filename(pmid, pmcid)

    @classmethod
    def abstract_download_path(cls, pmid):
        return cls.DOWNLOADS_ABSTRACTS / cls.abstract_filename(pmid)

    @classmethod
    def pmc_gemini_path(cls, pmid, pmcid):
        return cls.GEMINI_CACHE_PMC / cls.pmc_filename(pmid, pmcid)

    @classmethod
    def abstract_gemini_path(cls, pmid):
        return cls.GEMINI_CACHE_ABSTRACTS / cls.abstract_filename(pmid)

    @classmethod
    def updated_pmc_path(cls, pmid, pmcid):
        return cls.UPDATED_PMC / cls.pmc_filename(pmid, pmcid)

    @classmethod
    def updated_abstract_path(cls, pmid):
        return cls.UPDATED_ABSTRACTS / cls.abstract_filename(pmid)


config = Config
