import os
from pathlib import Path

class Config:
    NCBI_EMAIL = os.getenv("NCBI_EMAIL", "jq2430@columbia.edu")
    NCBI_API_KEY = os.getenv("NCBI_API_KEY", None)
    NCBI_SLEEP_TIME = 0.1 if NCBI_API_KEY else 0.34
    
    GEMINI_PROJECT_ID = os.getenv("GEMINI_PROJECT_ID", "rs-vertexai-czhu")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TEMPERATURE = 0.0
    
    BASE_DIR = Path(__file__).parent.parent.parent
    OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "auto_pipeline_output")))
    
    DATABASE_PATH = OUTPUT_DIR / "articles.db"
    EXCEL_OUTPUT = OUTPUT_DIR / "articles_database.xlsx"
    RAW_TEXT_CACHE = OUTPUT_DIR / "raw_text_cache"
    GEMINI_CACHE = OUTPUT_DIR / "gemini_raw_cache"
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def setup(cls):
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cls.RAW_TEXT_CACHE.mkdir(parents=True, exist_ok=True)
        cls.GEMINI_CACHE.mkdir(parents=True, exist_ok=True)
        print("✓ Configuration validated")

config = Config
