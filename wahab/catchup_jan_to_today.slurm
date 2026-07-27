#!/bin/bash
#SBATCH --job-name=gemini_catchup_jan2026
#SBATCH --output=catchup_jan2026_%j.out
#SBATCH --error=catchup_jan2026_%j.err
#SBATCH --time=48:00:00
#SBATCH --ntasks=1
#SBATCH --mem=2G

module load python3

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

cd "$HOME/biolit_autominer"
source .venv/bin/activate

# One-time catch-up: closes the gap between the static backlog corpus (through
# Dec 2025) and today, before the daily cron job takes over going forward.
# max_results/num_articles both sized above the confirmed real count (6,737)
# so nothing gets silently missed the way the daily job's low default would.
# -u: unbuffered stdout, so the .out log streams in real time instead of
# sitting in a block buffer -- needed to tell a slow-but-alive job apart
# from a genuinely hung one without guessing from CPU deltas alone.
python3 -u scripts/run_daily_pmc_aws.py \
  --start-date 2026/01/01 --end-date 2026/07/16 \
  --max_results 7500 --num_articles 7000 --workers 5
