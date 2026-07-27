#!/bin/bash
# Daily new-article pipeline, run via scrontab on Wahab.
# Uses Vertex AI (an API service), so this stays on the "main" partition,
# not "gpu" -- matching RCC's own guidance for API-based LLM usage.

set -e

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/biolit_autominer/credentials/application_default_credentials.json"

module load python3
cd "$HOME/biolit_autominer"
source .venv/bin/activate

python3 scripts/run_daily_pmc_aws.py >> "$HOME/biolit_autominer/logs/daily_pipeline.log" 2>&1
