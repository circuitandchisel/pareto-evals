"""Fetch ARC-AGI-2 public evaluation tasks -> datasets/arc-agi-2/evaluation/*.json.

Source: ARC Prize public repo (github arcprize/ARC-AGI-2). Public, no auth.
(Was a .sh originally, but datasets/*.sh is gitignored — Python keeps it tracked.)
"""
import glob
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "datasets", "arc-agi-2", "evaluation")


def main():
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/arcprize/ARC-AGI-2",
             os.path.join(tmp, "arc")],
            check=True,
        )
        src = os.path.join(tmp, "arc", "data", "evaluation")
        os.makedirs(DEST, exist_ok=True)
        n = 0
        for f in glob.glob(os.path.join(src, "*.json")):
            shutil.copy(f, DEST)
            n += 1
        print(f"ARC-AGI-2 evaluation tasks copied: {n} -> {DEST}")
        if n == 0:
            print("WARNING: no evaluation JSONs found — check the repo layout (data/evaluation/).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
