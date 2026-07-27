#!/bin/bash
#SBATCH --job-name=gemini_extract_2022_2023
#SBATCH --output=extract_2022_2023_%j.out
#SBATCH --error=extract_2022_2023_%j.err
#SBATCH --time=48:00:00
#SBATCH --ntasks=1
#SBATCH --mem=4G

module load python3

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

cd "$HOME/biolit_autominer"
source .venv/bin/activate

# Batch 4 of 4: ~9,432 articles.
python3 -u scripts/run_gemini_extraction.py --all-unprocessed --year-start 2022 --year-end 2023 --workers 5
