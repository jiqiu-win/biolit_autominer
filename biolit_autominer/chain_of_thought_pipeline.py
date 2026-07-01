"""
Two-tier extraction pipeline for budget-conscious NeurIPS/IEEE workflows.

Stage 1 (cheap): Qwen / DeepSeek reads paper and drafts evidence + chain-of-thought
Stage 2 (expensive): Gemini / Claude cleans final bracket extraction
"""

import json
from pathlib import Path

from .config import config


class ChainOfThoughtPipeline:
    """
    Automate:
      cheap model  -> key sentences/figures + draft chain-of-thought
      strong model -> cleaned extraction + polished chain-of-thought
    """

    def __init__(self):
        self.cheap_model = config.CHEAP_LLM_MODEL
        self.strong_model = config.STRONG_LLM_MODEL
        self.cache_dir = config.GEMINI_CACHE_DIR / "chain_of_thought"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def stage1_draft(self, text, source_file):
        prompt = (
            "You are a low-cost pre-processing assistant. Read the biomedical text and:\n"
            "1) List 3-8 key sentences that mention hepatotoxicity or mitochondrial markers.\n"
            "2) Mention any figure/table IDs tied to those sentences.\n"
            "3) Draft a short chain-of-thought explaining how evidence supports each marker result.\n"
            "Keep output concise and structured."
        )
        result = self._call_model(self.cheap_model, text, prompt)
        draft_path = self.cache_dir / f"{Path(source_file).stem}_draft.json"
        draft_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result, draft_path

    def stage2_clean(self, text, draft_result, source_file, extraction_prompt):
        draft_text = draft_result.get("raw_response", "")
        prompt = (
            f"{extraction_prompt}\n\n"
            "Use the draft evidence notes below only as hints. "
            "Return final bracket-format extractions only.\n\n"
            "Also return a separate section titled 'CHAIN_OF_THOUGHT' with 2-4 sentences "
            "explaining how you derived each evidence sentence.\n\n"
            f"DRAFT NOTES:\n{draft_text[:8000]}"
        )
        result = self._call_model(self.strong_model, text, prompt)
        clean_path = self.cache_dir / f"{Path(source_file).stem}_clean.json"
        clean_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        cot_path = self.cache_dir / f"{Path(source_file).stem}_chain_of_thought.txt"
        raw = result.get("raw_response", "")
        chain = self._split_chain_of_thought(raw)
        cot_path.write_text(chain, encoding="utf-8")
        return result, cot_path

    def run(self, text, source_file, extraction_prompt):
        draft, _ = self.stage1_draft(text, source_file)
        cleaned, cot_path = self.stage2_clean(text, draft, source_file, extraction_prompt)
        return {
            "draft": draft,
            "final": cleaned,
            "chain_of_thought_path": cot_path,
        }

    def _call_model(self, model_name, text, prompt):
        model_name = (model_name or "").lower()
        if model_name.startswith("gemini"):
            return self._call_gemini(text, prompt)
        if model_name in {"deepseek", "qwen"}:
            return self._call_openai_compatible(model_name, text, prompt)
        if model_name == "claude":
            return self._call_claude(text, prompt)
        return {"status": "error", "error": f"Unsupported model: {model_name}"}

    def _call_gemini(self, text, prompt):
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            vertexai.init(project=config.GEMINI_PROJECT_ID, location="us-central1")
            model = GenerativeModel(config.GEMINI_MODEL)
            response = model.generate_content(
                f"{prompt}\n\nTEXT:\n{text[:12000]}",
                generation_config={"temperature": config.GEMINI_TEMPERATURE},
            )
            return {"model": config.GEMINI_MODEL, "status": "success", "raw_response": response.text}
        except Exception as exc:
            return {"model": config.GEMINI_MODEL, "status": "error", "error": str(exc)}

    def _call_openai_compatible(self, model_name, text, prompt):
        api_key = config.DEEPSEEK_API_KEY if model_name == "deepseek" else config.QWEN_API_KEY
        base_url = config.DEEPSEEK_BASE_URL if model_name == "deepseek" else config.QWEN_BASE_URL
        if not api_key:
            return {
                "model": model_name,
                "status": "not_configured",
                "error": f"Set API key in .env for {model_name}",
            }
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=config.DEEPSEEK_MODEL if model_name == "deepseek" else config.QWEN_MODEL,
                messages=[
                    {"role": "system", "content": "You are a biomedical extraction assistant."},
                    {"role": "user", "content": f"{prompt}\n\nTEXT:\n{text[:12000]}"},
                ],
                temperature=0,
            )
            return {
                "model": model_name,
                "status": "success",
                "raw_response": response.choices[0].message.content,
            }
        except Exception as exc:
            return {"model": model_name, "status": "error", "error": str(exc)}

    def _call_claude(self, text, prompt):
        return {
            "model": "claude",
            "status": "not_configured",
            "error": "Set ANTHROPIC_API_KEY in .env to enable Claude cleaning.",
        }

    @staticmethod
    def _split_chain_of_thought(raw_response):
        if "CHAIN_OF_THOUGHT" in raw_response:
            return raw_response.split("CHAIN_OF_THOUGHT", 1)[1].strip()
        return raw_response.strip()
