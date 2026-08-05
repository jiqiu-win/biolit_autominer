"""
Compile all per-marker QSAR result tables into one shareable Excel workbook.

Reads every qsar/results/results_<marker>_<tag>.csv (the per-model metrics table
each run produces) and writes results_summary.xlsx with:
  - Summary  : best model per (marker, setting)
  - one sheet per setting (FULL / BIN / HC / BINHC): full per-model tables, all markers
  - About    : what each setting means (incl. how 'no significant change' is handled)

Usage (on the HPC, from ~/biolit_autominer):
    python qsar/build_results_excel.py
Optional: pass a results directory as the first argument (for local testing).
"""
import glob
import sys
from pathlib import Path

import pandas as pd

RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("qsar/results")
OUT = RESULTS / "results_summary.xlsx"

TAG_LABEL = {
    "FULL": "3-class, full data (increase / decrease / no significant change)",
    "BIN": "Binary, 2-class (increase vs decrease; 'no significant change' dropped)",
    "HC": "High-confidence, 3-class (only chemicals with >= 2 supporting papers)",
    "BINHC": "Binary + High-confidence",
}
TAG_ORDER = ["FULL", "BIN", "HC", "BINHC"]


def parse(path):
    stem = Path(path).name[len("results_"):-len(".csv")]
    marker, tag = stem.rsplit("_", 1)
    return marker, tag


def n_molecules(marker, tag):
    dsf = RESULTS / f"dataset_{marker}_{tag}.csv"
    if dsf.exists():
        return sum(1 for _ in open(dsf)) - 1   # minus header
    return None


detail = {}   # tag -> list of per-marker dataframes
summary_rows = []

for f in sorted(glob.glob(str(RESULTS / "results_*.csv"))):
    marker, tag = parse(f)
    if tag == "smoketest":
        continue
    df = pd.read_csv(f)
    n = n_molecules(marker, tag)
    df.insert(0, "Marker", marker)
    df.insert(1, "N", n)
    detail.setdefault(tag, []).append(df)

    best = df.loc[df["Macro-F1"].idxmax()]
    summary_rows.append({
        "Marker": marker,
        "Setting": tag,
        "N": n,
        "Best model": best["Model"],
        "Macro-F1": best["Macro-F1"],
        "Accuracy": best["Accuracy"],
        "Macro-AUC(ovr)": best.get("Macro-AUC(ovr)"),
    })

if not summary_rows:
    sys.exit(f"No results_*.csv found in {RESULTS}")

summary = pd.DataFrame(summary_rows)
order = {t: i for i, t in enumerate(TAG_ORDER)}
summary = summary.sort_values(
    ["Marker", "Setting"], key=lambda s: s.map(order) if s.name == "Setting" else s
).reset_index(drop=True)

about = pd.DataFrame({"Notes on settings and metrics": [
    "Each 'setting' sheet lists every model's metrics for every marker.",
    "",
    "Settings:",
    "  FULL  = " + TAG_LABEL["FULL"],
    "  BIN   = " + TAG_LABEL["BIN"],
    "  HC    = " + TAG_LABEL["HC"],
    "  BINHC = " + TAG_LABEL["BINHC"],
    "",
    "How 'no significant change' is handled in the binary settings:",
    "  Chemicals whose consensus label is 'no significant change' are DROPPED entirely",
    "  (not merged into another class, not reassigned). The 2-class task keeps only",
    "  chemicals labelled increase or decrease.",
    "",
    "Columns:",
    "  N              = number of chemicals used (after SMILES resolution + filtering).",
    "  Accuracy       = % of test chemicals classified correctly.",
    "  Macro-F1       = unweighted mean of per-class F1 (main metric).",
    "                   Random baseline ~0.33 (3-class), ~0.50 (binary).",
    "  Weighted-F1    = per-class F1 weighted by class size.",
    "  Macro-AUC(ovr) = one-vs-rest AUC, averaged over classes (0.5 = chance, 1 = perfect).",
    "  F1[<class>]    = F1 for that single class.",
]})

with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
    summary.to_excel(writer, sheet_name="Summary", index=False)
    for tag in TAG_ORDER:
        if tag in detail:
            pd.concat(detail[tag], ignore_index=True).to_excel(
                writer, sheet_name=tag, index=False)
    about.to_excel(writer, sheet_name="About", index=False)

print(f"[saved] {OUT}")
print(f"  settings: {[t for t in TAG_ORDER if t in detail]}")
print(f"  markers : {summary['Marker'].nunique()}")
print(f"  rows    : {len(summary)} (marker x setting)")
