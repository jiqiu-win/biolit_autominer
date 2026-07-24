"""
Build the high-confidence dataset (label supported by >= N articles) from an
already-built FULL dataset CSV.

The main pipeline also writes this file automatically now; this standalone script
lets you (re)build it from an existing dataset_<MARKER>_FULL.csv without re-running
the full pipeline (no SMILES lookup / no model training needed).

Usage:
    python qsar/build_high_confidence.py --marker ALT
    python qsar/build_high_confidence.py --marker ALT --min-support 2
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

RESULTS = Path(__file__).resolve().parent / "results"


def main():
    ap = argparse.ArgumentParser(description="Build high-confidence dataset (support >= N)")
    ap.add_argument("--marker", default="ALT")
    ap.add_argument("--min-support", type=int, default=2,
                    help="Minimum supporting articles to be 'high confidence' (default 2)")
    args = ap.parse_args()

    full_path = RESULTS / f"dataset_{args.marker}_FULL.csv"
    if not full_path.exists():
        sys.exit(f"FULL dataset not found: {full_path}\nRun the pipeline first to create it.")

    full = pd.read_csv(full_path)
    hc = full[full["support"] >= args.min_support].reset_index(drop=True)

    out = RESULTS / f"high_confidence_dataset_{args.marker}.csv"
    hc.to_csv(out, index=False)

    print(f"marker={args.marker} | high-confidence = support >= {args.min_support}")
    print(f"  FULL molecules            : {len(full)}")
    print(f"  high-confidence molecules : {len(hc)}")
    if len(hc):
        print("  label distribution:")
        print(hc["label"].value_counts().to_string())
    print(f"[saved] {out}")


if __name__ == "__main__":
    main()
