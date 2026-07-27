#!/bin/bash
#SBATCH --job-name=gemini_extract_2024_2025_resume
#SBATCH --output=extract_2024_2025_resume_%j.out
#SBATCH --error=extract_2024_2025_resume_%j.err
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --mem=2G

module load python3

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

cd "$HOME/biolit_autominer"
source .venv/bin/activate

# Resumable: --all-unprocessed only pulls gemini_processed=0 rows, so this
# automatically skips everything the first (sequential) job already finished.
# --workers 5 is a conservative starting point -- we don't know Vertex AI's
# real per-project rate limit yet, so watch for 429/rate-limit errors in the
# output and adjust up or down for the next batch based on what's observed.
python3 scripts/run_gemini_extraction.py --all-unprocessed --year-start 2024 --year-end 2025 --workers 5
