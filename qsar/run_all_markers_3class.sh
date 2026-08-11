#!/usr/bin/env bash
# STEP 2 — 3-class (default) on all trainable markers, to complete the main table.
# Run from the repo root:  nohup bash qsar/run_all_markers_3class.sh > qsar/results/all3class.log 2>&1 &
set -u
DATA="auto_pipeline_output/updated/biolit_dataset_final.xlsx"
MARKERS=(
  "ALT" "AST" "steatosis" "fibrosis" "cell viability" "TNF-α" "necrosis" "apoptosis"
  "IL-6" "ROS" "MDA" "ALP" "bilirubin" "cholestasis" "LDH" "IL-1β" "albumin" "ATP"
  "inflammation" "OCR" "OXPHOS" "α-SMA" "GGT" "mtROS" "cytochrome c release" "IL-10"
  "TG" "liver injury" "hepatotoxicity" "IFN-γ" "TGF-β1" "cholesterol" "Bax" "NF-κB"
  "mPTP" "triglycerides" "Bcl-2" "TC" "caspase-3" "MCP-1" "TGF-β" "GSH" "total bilirubin"
  "IL-8" "IL-18" "triglyceride" "iNOS" "cell death" "MPO" "cell proliferation"
  "total cholesterol" "LDL" "liver weight" "oxidative stress" "TNFα" "NO" "TIMP-1"
  "creatinine" "ballooning" "HDL" "lobular inflammation" "collagen I" "PPARα" "PPARγ"
  "urea" "FAS" "IL-4" "COX-2" "TBA" "TBIL" "autophagy" "glucose" "p53" "total protein"
  "CHOP" "direct bilirubin" "hydroxyproline"
)
for M in "${MARKERS[@]}"; do
  echo "######## MARKER: $M ########"
  python qsar/qsar_marker_pipeline.py --marker "$M" --data "$DATA" --tag "FULL" \
    || echo ">>> FAIL $M"
done
echo "######## ALL 3-CLASS DONE ########"
