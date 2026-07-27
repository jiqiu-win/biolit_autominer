#!/bin/bash
#SBATCH --job-name=gemini_extract_2015_2018
#SBATCH --output=extract_2015_2018_%j.out
#SBATCH --error=extract_2015_2018_%j.err
#SBATCH --time=48:00:00
#SBATCH --ntasks=1
#SBATCH --mem=2G

module load python3

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

cd "$HOME/biolit_autominer"
source .venv/bin/activate

# Batch 2 of 4: ~9,974 articles.
python3 -u scripts/run_gemini_extraction.py --all-unprocessed --year-start 2015 --year-end 2018 --workers 5
