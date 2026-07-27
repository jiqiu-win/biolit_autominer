"""
GNN small-data investigation (ablation).

Tests the two hypotheses about WHY the graph models underperform the classic ML
models on the small ALT dataset:

  H1. Class weighting is over-correcting on tiny data  -> try WITHOUT class weight.
  H2. The GNN is too big/deep for ~130 training molecules -> try a SMALLER, SHALLOWER GNN.

It runs the graph models (Graphormer, GraphGPS, GraphSAGE) under 4 configs and
prints one side-by-side comparison so you can see which change (if any) closes the
gap with RandomForest / XGBoost.

    baseline        : class weight ON,  hidden 128, layers 3   (current setup)
    no_weight       : class weight OFF, hidden 128, layers 3   (tests H1)
    small           : class weight ON,  hidden 64,  layers 2   (tests H2)
    small_no_weight : class weight OFF, hidden 64,  layers 2   (H1 + H2)

Each config writes results_<marker>_<tag>.csv; this script then combines them.

Usage:
    python qsar/run_gnn_ablation.py --marker ALT
"""

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
PIPELINE = HERE / "qsar_marker_pipeline.py"

# (tag, extra CLI args)
CONFIGS = [
    ("baseline",        []),
    ("no_weight",       ["--no-class-weight"]),
    ("small",           ["--gt-hidden", "64", "--gt-layers", "2"]),
    ("small_no_weight", ["--no-class-weight", "--gt-hidden", "64", "--gt-layers", "2"]),
]
GRAPH_MODELS = ["Graphormer", "GraphGPS", "GraphSAGE"]


def main():
    ap = argparse.ArgumentParser(description="GNN small-data ablation")
    ap.add_argument("--marker", default="ALT")
    ap.add_argument("--data", default=None, help="Dataset xlsx path (passed to the pipeline)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Quick smoke test: N random chemicals only (e.g. --limit 300)")
    args = ap.parse_args()

    passthrough = []
    if args.data:
        passthrough += ["--data", args.data]
    if args.limit:
        passthrough += ["--limit", str(args.limit)]

    combined = []
    for tag, extra in CONFIGS:
        print("\n" + "#" * 70)
        print(f"# CONFIG: {tag}   {' '.join(extra) or '(defaults)'}")
        print("#" * 70)
        cmd = [sys.executable, str(PIPELINE), "--marker", args.marker,
               "--tag", tag, "--models", *GRAPH_MODELS, *passthrough, *extra]
        subprocess.run(cmd, check=True)

        res_path = RESULTS / f"results_{args.marker}_{tag}.csv"
        if res_path.exists():
            df = pd.read_csv(res_path)
            df.insert(0, "Config", tag)
            combined.append(df[["Config", "Model", "Accuracy", "Macro-F1", "Macro-AUC(ovr)"]])

    if not combined:
        print("No results produced."); return

    table = pd.concat(combined, ignore_index=True)
    out = RESULTS / f"gnn_ablation_{args.marker}.csv"
    table.to_csv(out, index=False)

    print("\n" + "=" * 70)
    print(f"GNN ABLATION SUMMARY — marker={args.marker}")
    print("(compare against your RandomForest baseline: Acc 60.6 / Macro-F1 0.42)")
    print("=" * 70)
    # pivot so each config is a column block — easier to compare
    for model in GRAPH_MODELS:
        sub = table[table["Model"] == model]
        print(f"\n{model}:")
        print(sub[["Config", "Accuracy", "Macro-F1", "Macro-AUC(ovr)"]].to_string(index=False))
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
