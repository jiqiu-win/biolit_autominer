#!/bin/bash
#SBATCH --job-name=gemini_extract_2019_2021
#SBATCH --output=extract_2019_2021_%j.out
#SBATCH --error=extract_2019_2021_%j.err
#SBATCH --time=48:00:00
#SBATCH --ntasks=1
#SBATCH --mem=4G

module load python3

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

cd "$HOME/biolit_autominer"
source .venv/bin/activate

# Batch 3 of 4: ~11,379 articles -- the largest batch.
python3 -u scripts/run_gemini_extraction.py --all-unprocessed --year-start 2019 --year-end 2021 --workers 5
