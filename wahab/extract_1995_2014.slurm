#!/bin/bash
#SBATCH --job-name=gemini_extract_1995_2014
#SBATCH --output=extract_1995_2014_%j.out
#SBATCH --error=extract_1995_2014_%j.err
#SBATCH --time=48:00:00
#SBATCH --ntasks=1
#SBATCH --mem=2G

module load python3

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

cd "$HOME/biolit_autominer"
source .venv/bin/activate

# Batch 1 of 4: ~9,868 articles. Resumable -- safe to resubmit unchanged if
# this hits the walltime limit; already-processed articles get skipped.
python3 -u scripts/run_gemini_extraction.py --all-unprocessed --year-start 1995 --year-end 2014 --workers 5
