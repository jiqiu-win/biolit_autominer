#!/bin/bash
#SBATCH --job-name=gemini_connectivity_test
#SBATCH --output=connectivity_test_%j.out
#SBATCH --error=connectivity_test_%j.err
#SBATCH --time=00:05:00
#SBATCH --ntasks=1
#SBATCH --mem=1G

module load python3

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

cd "$HOME/biolit_autominer"
source .venv/bin/activate
python3 wahab/connectivity_test.py
