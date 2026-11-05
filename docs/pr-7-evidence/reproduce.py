import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
REVISIONS = {
    "before": "984f576dc58d41aa6dd34448b831fe2e64243c0b",
    "after": "7f6b856285aadefb95b4e0780ad01018a57a93d5",
}
evidence = {
    "scenario": "Synthetic prior run; current benchmark subprocess exits 23 before producing results",
    "sample_size": 100,
    "prior_correct": 80,
    "live_model_calls": 0,
    "results": {},
}
for label, revision in REVISIONS.items():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = subprocess.check_output(["git", "show", f"{revision}:run.py"], cwd=REPOSITORY)
        (root / "run.py").write_bytes(source)
        benchmarks = root / "benchmarks"
        benchmarks.mkdir()
        (benchmarks / "__init__.py").write_text("")
        (benchmarks / "gpqa.py").write_text("raise SystemExit(23)\n")
        results = root / "results"
        results.mkdir()
        rows = [{"id": index, "correct": index < 80, "cost_usd": 0.01} for index in range(100)]
        (results / "gpqa__pareto.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        (results / "gpqa__pareto.summary.json").write_text(json.dumps({"n": 100, "accuracy": 80.0}))
        for extension in ("md", "csv"):
            (results / f"comparison.{extension}").write_text("Previous report: 80%\n")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PARETO_BASE_URL": "http://unused.invalid/v1",
            "PARETO_MODEL": "synthetic-fixture",
            "PARETO_LABEL": "Synthetic fixture",
        }
        process = subprocess.run(
            [sys.executable, "run.py", "--benchmarks", "gpqa", "--slice", "100", "--models", "pareto"],
            cwd=root, env=environment, text=True, capture_output=True,
        )
        markdown = results / "comparison.md"
        csv = results / "comparison.csv"
        observation = {
            "commit": revision,
            "exit_code": process.returncode,
            "markdown_report_exists": markdown.exists(),
            "csv_report_exists": csv.exists(),
            "old_jsonl_exists": (results / "gpqa__pareto.jsonl").exists(),
            "old_summary_exists": (results / "gpqa__pareto.summary.json").exists(),
            "report": markdown.read_text() if markdown.exists() else None,
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        if label == "before":
            assert process.returncode == 0
            assert "80.0%" in observation["report"]
            assert observation["csv_report_exists"]
        else:
            assert process.returncode != 0
            assert "exited 23; results will not be aggregated" in process.stderr
            assert not any(observation[key] for key in (
                "markdown_report_exists", "csv_report_exists", "old_jsonl_exists", "old_summary_exists",
            ))
        evidence["results"][label] = observation
        print(f"{label}: CLI exit={process.returncode}, report exists={markdown.exists()}")
(OUTPUT / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
print("PASS: real subprocess failure reproduced against both exact commits")
