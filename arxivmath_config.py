"""Shared identity for reviewed ArXivMath manifests and prepared artifacts."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def configuration():
    value = json.loads((ROOT / "arxivmath.json").read_text())
    if not isinstance(value, dict) or set(value) != {"dataset", "revision", "edition", "split", "rows", "license"}:
        raise ValueError("Exact ArXivMath manifest required")
    match = re.fullmatch(r"MathArena/arxivmath-(0[1-9]|1[0-2])([0-9]{2})", str(value["dataset"]))
    if (not match or value["edition"] != f"20{match[2]}-{match[1]}"
            or not re.fullmatch(r"[a-f0-9]{40}", str(value["revision"]))
            or value["split"] != "train" or value["license"] != "cc-by-sa-4.0"
            or type(value["rows"]) is not int or not 1 <= value["rows"] <= 10000):
        raise ValueError("Invalid ArXivMath manifest")
    return value


def artifact_name(config):
    return f"arxivmath_{config['dataset'].rsplit('-', 1)[1]}_{config['revision']}.json"


def load_items(filename=None):
    config = configuration()
    target = Path(filename) if filename is not None else ROOT / "datasets" / artifact_name(config)
    if target.name != artifact_name(config):
        raise ValueError("ArXivMath artifact does not match the reviewed revision; rerun preparation")
    rows = json.loads(target.read_text())
    if (not isinstance(rows, list) or len(rows) != config["rows"]
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]
                   or any(not isinstance(row.get(field), str) or not row[field].strip()
                          for field in ("problem", "answer")) for row in rows)
            or len({row["id"] for row in rows}) != len(rows)):
        raise ValueError("Invalid prepared ArXivMath questions")
    return rows
