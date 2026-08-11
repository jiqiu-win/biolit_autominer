#!/usr/bin/env bash
# STEP 1 — learning curve: same 3-class setting, vary the training-set size.
# Shows that more data -> better models (big-data vs small-data, per C. Zhu).
# Run from the repo root:  nohup bash qsar/run_learning_curve.sh > qsar/results/lc.log 2>&1 &
set -u
DATA="auto_pipeline_output/updated/biolit_dataset_final.xlsx"
for M in "ALT" "steatosis"; do
  for N in 100 300 600 1000; do
    echo "######## $M | train-size $N ########"
    python qsar/qsar_marker_pipeline.py --marker "$M" --data "$DATA" --train-size "$N" --tag "LC$N" \
      || echo ">>> FAIL $M $N"
  done
  echo "######## $M | FULL ########"
  python qsar/qsar_marker_pipeline.py --marker "$M" --data "$DATA" --tag "LCall" \
    || echo ">>> FAIL $M full"
done
echo "######## LEARNING CURVE DONE ########"
