"""
Multi-LLM biomedical extraction (IEEE paper module).

Currently supports Gemini via Vertex AI. GPT-4 and Claude hooks are included
so you can plug in API keys later without changing the pipeline structure.
"""

import json
from pathlib import Path

from .config import config


class MultiLLMExtractor:
    SUPPORTED_MODELS = ("gemini", "gpt4", "claude")

    def __init__(self, cache_dir=None):
        self.cache_dir = Path(cache_dir or config.GEMINI_CACHE)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def extract_full_prompt(self, complete_prompt, model="gemini"):
        """Send a fully assembled prompt string (as in Auto_pipeline_complete.ipynb)."""
        if model == "gemini":
            return self._extract_gemini_content(complete_prompt)
        raise ValueError(f"Unsupported model: {model}")

    def extract(self, text, model="gemini", prompt=None):
        prompt = prompt or self.default_prompt()
        if model == "gemini":
            return self._extract_gemini(text, prompt)
        if model == "gpt4":
            return self._extract_gpt4(text, prompt)
        if model == "claude":
            return self._extract_claude(text, prompt)
        raise ValueError(f"Unsupported model: {model}")

    def compare_models(self, text, models=None):
        models = models or ["gemini"]
        results = {}
        for model in models:
            results[model] = self.extract(text, model=model)
        return results

    def default_prompt(self):
        return (
            "Extract hepatotoxicity and mitochondrial findings from this biomedical text. "
            "Return JSON with keys: compound, mechanism, organ, confidence."
        )

    def _extract_gemini_content(self, content):
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            vertexai.init(project=config.GEMINI_PROJECT_ID, location="us-central1")
            model = GenerativeModel(config.GEMINI_MODEL)
            response = model.generate_content(
                content,
                generation_config={"temperature": config.GEMINI_TEMPERATURE},
            )
            return {
                "model": config.GEMINI_MODEL,
                "status": "success",
                "raw_response": response.text,
            }
        except Exception as exc:
            return {"model": config.GEMINI_MODEL, "status": "error", "error": str(exc)}

    def _extract_gemini(self, text, prompt):
        # Legacy path: prompt template with optional placeholder
        content = prompt if "{{{TEXT}}}" not in prompt else prompt.replace(
            "{{{TEXT}}}", text[: config.GEMINI_MAX_TEXT_CHARS]
        )
        return self._extract_gemini_content(content)

    def _extract_gpt4(self, text, prompt):
        return {
            "model": "gpt-4",
            "status": "not_configured",
            "error": "Set OPENAI_API_KEY in .env to enable GPT-4 extraction.",
        }

    def _extract_claude(self, text, prompt):
        return {
            "model": "claude",
            "status": "not_configured",
            "error": "Set ANTHROPIC_API_KEY in .env to enable Claude extraction.",
        }

    def save_result(self, pmid, result, source_type="pmc", pmcid=None, title=""):
        """
        Save Gemini 2.5 bracket extractions as .txt in gemini_raw_cache/.
        Uses the same filename pattern as downloads/.
        """
        text = result.get("raw_response") if isinstance(result, dict) else str(result)
        if not text:
            text = json.dumps(result, indent=2)

        if source_type == "pubmed_abstract":
            path = config.abstract_gemini_path(pmid)
        else:
            if not pmcid:
                raise ValueError("pmcid is required when source_type is 'pmc'")
            path = config.pmc_gemini_path(pmid, pmcid, title)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.strip() + "\n", encoding="utf-8")
        return path
