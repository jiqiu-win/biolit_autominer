# QSAR experiment log

A dated record of what was run, the result, and any decision — for writing the
paper's Methods and for reproducibility. Add a new entry per experiment.

## Environment (update whenever it changes)

- Machine: ______ (Mac base conda / ODU HPC)
- Python: ______ (`python --version`)
- Key packages: torch ___, torch-geometric ___, rdkit ___
  (get with: `pip freeze | grep -Ei "torch|rdkit|xgboost|scikit"`)
- Dataset file: `biolit_dataset (6).xlsx`
- Dataset checksum: ______ (`shasum "biolit_dataset (6).xlsx"`)
- Random seed: 42 (fixed in the pipeline)

## Labeling / data rules (decided with C. Zhu)

- Predict the **Result** per marker, 3 classes: increase / decrease / no significant change.
- Drop a chemical as "conflicting" if its papers disagree (increase-vs-decrease OR
  direction-vs-no-change).
- Combinations "A + B" are ignored (not single molecules) unless modeling combined toxicity.
- Noisy Result values are normalized to the 3 canonical classes; others dropped.

## Log

### 2026-07-24 — ALT, large dataset (baseline)
- Command: `python qsar/qsar_marker_pipeline.py --marker ALT`
- Data: biolit_dataset (6).xlsx → ALT = 5,649 chemicals (decrease 2811 / increase 1609 / no-change 1229)
- Result: ______ (fill after the full HPC run)
- Notes / decisions: moved from the small 604-chemical set to this ~5,649 set;
  earlier GNN vs classic gap was a small-data effect (see ablation below).

### 2026-07-__ — ALT GNN ablation
- Command: `python qsar/run_gnn_ablation.py --marker ALT`
- Finding: removing class weight + smaller GNN closed most of the gap on the small set
  (GraphSAGE no_weight ≈ RandomForest). Re-check on the large dataset.
- Notes:

### YYYY-MM-DD — <title>
- Command:
- Result:
- Notes:
