# QSAR marker pipeline

Predict a hepatotoxicity **marker's Result** (3-class: *increase / decrease / no significant change*)
from a chemical's **molecular structure**, for one marker at a time.

Mirrors Yamini's caspase notebook
(`qsar_project_dili/qsar_prediction/caspase/QSAR_Caspase_GraphTransformers.ipynb`),
adapted to our literature-extracted data:

| Difference from Yamini | Why |
|---|---|
| chemical **name → SMILES** via PubChem | her PubChem data already had SMILES |
| **3-class** + `CrossEntropyLoss` | her task was binary (Active/Inactive) |
| **class weights** (not 1:1 downsampling) | downsampling doesn't extend to 3 classes |

Models: **Graphormer + GraphGPS** (two graph transformers) **+ GraphSAGE** (a classic
message-passing GNN) **+ RandomForest + XGBoost** on Morgan fingerprints.

## Dataset built

The **FULL** set for the chosen marker. A chemical is dropped as "conflicting" if its papers
disagree — both **increase-vs-decrease** *and* **direction-vs-"no significant change"**
(per C. Zhu; the mixed cases are few, ~6% for ALT). Only chemicals with a single, unambiguous
result type are kept.

## Install (on HPC / Jupyter)

```bash
pip install rdkit pubchempy xgboost scikit-learn pandas numpy openpyxl \
            torch torch-geometric
```

## Run

```bash
python qsar/qsar_marker_pipeline.py --marker ALT      # default: all 5 models
python qsar/qsar_marker_pipeline.py --marker AST      # reuse for another marker — 1 word

# QUICK SMOKE TEST — run end-to-end on only ~300 chemicals to check the code works:
python qsar/qsar_marker_pipeline.py --marker ALT --limit 300 --tag smoketest \
       --data "/path/to/biolit_dataset (6).xlsx"

# Only (re)train specific models — updates those rows in the results table, keeps the rest:
python qsar/qsar_marker_pipeline.py --marker ALT --models GraphSAGE
python qsar/qsar_marker_pipeline.py --marker ALT --models GraphSAGE RandomForest
```

Models: `Graphormer`, `GraphGPS`, `GraphSAGE`, `RandomForest`, `XGBoost` (default = all).

## Typical workflow (command cheat-sheet)

On the HPC, add `--data "/path/to/biolit_dataset (6).xlsx"` to each command.

```bash
# 1. SMOKE TEST — confirm the code runs end-to-end (~a few min; ignore the scores):
python qsar/qsar_marker_pipeline.py --marker ALT --limit 300 --tag smoketest

# 2. FULL RUN — the real result to report (all 5 models):
python qsar/qsar_marker_pipeline.py --marker ALT

# 3. ANOTHER MARKER — one word changes:
python qsar/qsar_marker_pipeline.py --marker AST

# 4. ABLATION — investigate why the GNNs under/over-perform (compares 4 configs):
python qsar/run_gnn_ablation.py --marker ALT

# 5. HIGH-CONFIDENCE subset (support >= 2) from an existing FULL dataset:
python qsar/build_high_confidence.py --marker ALT
```

- **First run is slow**: it resolves ~600 chemical names → SMILES via PubChem (~a few minutes),
  then **caches** them to `qsar/cache/name_to_smiles.csv`. The cache is shared across markers,
  so later markers reuse it and start fast.
- Runs on **CPU** (slow for the graph transformers) or **GPU** (auto-detected — use the HPC).

## Outputs (in `qsar/results/`)

- `dataset_<MARKER>_FULL.csv` — the built dataset (chemical, canonical SMILES, label, support)
- `results_<MARKER>_FULL.csv` — metrics table for all 4 models
  (Accuracy, Macro-F1, per-class F1, Macro-AUC-ovr)
- `results_<MARKER>_FULL_confusion.json` — confusion matrix per model

## Notes

- The **high-confidence (≥2-paper) subset is not modeled here** — per marker it is too small
  (ALT = 25 chemicals, 2 classes). That comparison is being decided separately.
- To model a new marker, just change `--marker`. Everything else (splits, models, metrics) is identical.
