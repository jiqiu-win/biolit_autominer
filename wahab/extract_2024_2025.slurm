#!/bin/bash
#SBATCH --job-name=gemini_extract_2024_2025
#SBATCH --output=extract_2024_2025_%j.out
#SBATCH --error=extract_2024_2025_%j.err
#SBATCH --time=16:00:00
#SBATCH --ntasks=1
#SBATCH --mem=2G

module load python3

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

cd "$HOME/biolit_autominer"
source .venv/bin/activate

# gemini_processed flag makes this resumable: if the job is killed/times out,
# resubmitting the same command picks up wherever it left off.
python3 scripts/run_gemini_extraction.py --all-unprocessed --year-start 2024 --year-end 2025
