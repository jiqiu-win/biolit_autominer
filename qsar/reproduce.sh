#!/usr/bin/env bash
# Reproduce the QSAR/GNN results for the paper.
#
# Usage:
#   1. Edit DATA below to point at the dataset file (on the HPC = the uploaded xlsx).
#   2. Run:  bash qsar/reproduce.sh
#
# This regenerates everything in qsar/results/. Random seed is fixed (SEED=42 in the
# pipeline), so results are deterministic given the same code + data + package versions.

set -euo pipefail

# --- edit these two ---------------------------------------------------------
DATA="/Users/qiuji/Downloads/biolit_dataset (6).xlsx"   # dataset file
MARKER="ALT"                                             # marker to model
# ---------------------------------------------------------------------------

echo "=================================================================="
echo " Reproducing QSAR results | marker=$MARKER"
echo " data: $DATA"
echo "=================================================================="

echo; echo "== 1. Main run — all 5 models =="
python qsar/qsar_marker_pipeline.py --marker "$MARKER" --data "$DATA"

echo; echo "== 2. GNN ablation — small-data investigation (4 configs) =="
python qsar/run_gnn_ablation.py --marker "$MARKER" --data "$DATA"

echo; echo "== 3. High-confidence subset (support >= 2) =="
python qsar/build_high_confidence.py --marker "$MARKER"

echo; echo "Done. All outputs are in qsar/results/"
