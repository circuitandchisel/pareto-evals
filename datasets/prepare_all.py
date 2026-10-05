"""Prepare all six non-agentic datasets, or a selected subset; stop on failure."""
import argparse
from pathlib import Path
import subprocess
import sys

SCRIPTS = {
    "hle": "prepare_hle.py",
    "arxiv_math": "prepare_arxiv_math.py",
    "hmmt_2026": "prepare_hmmt_2026.py",
    "mmmu_pro": "prepare_mmmu_pro.py",
    "gpqa": "prepare_gpqa.py",
    "arc_agi_2": "prepare_arc_agi_2.py",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmarks", nargs="+", choices=list(SCRIPTS), default=list(SCRIPTS))
    args = parser.parse_args()
    for name in args.benchmarks:
        print(f"Preparing {name}...", flush=True)
        result = subprocess.run([sys.executable, str(Path(__file__).parent / SCRIPTS[name])])
        if result.returncode:
            raise SystemExit(f"Preparation failed for {name}; remaining datasets were not run.")
    print("Dataset preparation complete.")


if __name__ == "__main__":
    main()
