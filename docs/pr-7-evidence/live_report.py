import argparse
import hashlib
import json
from pathlib import Path
import statistics


OUTPUT = Path(__file__).resolve().parent
FIELDS = (
    "id", "correct", "cost_usd", "started_at", "finished_at", "latency_s", "retries",
)


def summarize(evidence):
    summary = {}
    indexed = {}
    for arm in ("before", "after"):
        rows = evidence["rows"][arm]
        indexed[arm] = {row["id"]: row for row in rows}
        assert len(rows) == len(indexed[arm]) == 100
        costs = [row["cost_usd"] for row in rows if row["cost_usd"] is not None]
        latencies = [row["finished_at"] - row["started_at"] for row in rows]
        summary[arm] = {
            "tasks": len(rows),
            "correct": sum(row["correct"] for row in rows),
            "priced_tasks": len(costs),
            "response_cost_usd": sum(costs),
            "mean_response_cost_usd": statistics.mean(costs) if costs else None,
            "median_wall_latency_s": statistics.median(latencies),
            "mean_wall_latency_s": statistics.mean(latencies),
            "retries_reported": sum(row["retries"] or 0 for row in rows),
        }
    assert indexed["before"].keys() == indexed["after"].keys()
    differences = [
        int(indexed["after"][item_id]["correct"]) - int(row["correct"])
        for item_id, row in indexed["before"].items()
    ]
    delta = 100 * statistics.mean(differences)
    uncertainty = 1.96 * 100 * statistics.stdev(differences) / len(differences) ** 0.5
    summary["paired"] = {
        "delta_percentage_points": delta,
        "approximate_95_percent_ci": [delta - uncertainty, delta + uncertainty],
        "improved": differences.count(1),
        "regressed": differences.count(-1),
        "unchanged": differences.count(0),
    }
    return summary


def export(source):
    manifest = json.loads((source / "manifest.json").read_text())
    evidence = {
        "benchmark": manifest["benchmark"],
        "requested_model": manifest["model"],
        "before_commit": manifest["before"],
        "after_commit": manifest["after"],
        "source_sha256": manifest["source_sha256"],
        "seed": manifest["seed"],
        "sample_size_per_arm": manifest["sample_size_per_arm"],
        "max_tokens": manifest["max_tokens"],
        "concurrency": manifest["concurrency"],
        "sampling_parameters": manifest["sampling_parameters"],
        "batch_order": manifest["order"],
        "rows": {},
        "batches": {},
        "limitations": [
            "100 matched questions per arm; not the full 198-question dataset or verification of advertised scores.",
            "Provider sampling is nondeterministic; differences cannot be attributed to this PR alone.",
            "Approximate paired normal 95% interval; no prespecified noninferiority margin or power calculation.",
            "HTTP-attempt logs are unavailable; returned model identity and complete retry billing are unverified.",
            "Costs are response-reported, not independently reconciled charges; interrupted requests may cost extra.",
            "The run was interrupted after six completed batches per arm and resumed with the same settings.",
            "Only PR #7 nonstreaming GPQA; no HLE, streaming, or agentic benchmark validation.",
        ],
    }
    for arm in ("before", "after"):
        exported = []
        batches = []
        for batch in range(10):
            folder = source / "runs" / f"{batch:02d}-{arm}"
            completion = json.loads((folder / "complete.json").read_text())
            execution = json.loads((folder / "execution.json").read_text())
            assert completion == {"tasks": 10, "errors": 0}
            assert execution["exit_code"] == 0
            raw = (folder / "gpqa__pareto.jsonl").read_bytes()
            rows = [json.loads(line) for line in raw.splitlines()]
            items = [json.loads(line) for line in (source / f"batch-{batch:02d}.jsonl").read_text().splitlines()]
            answers = {item["id"]: item["answer"] for item in items}
            assert len(rows) == 10 and {row["id"] for row in rows} == answers.keys()
            for row in rows:
                assert not row.get("error")
                assert isinstance(row["correct"], bool)
                assert row["correct"] == (row.get("pred") == answers[row["id"]])
                assert row["finished_at"] >= row["started_at"]
                exported.append({key: row.get(key) for key in FIELDS})
            batches.append({
                "batch": batch, "artifact_sha256": hashlib.sha256(raw).hexdigest(),
                "started_at": execution["started_at"], "finished_at": execution["finished_at"],
                "exit_code": execution["exit_code"], "tasks": len(rows), "errors": 0,
            })
        evidence["rows"][arm] = exported
        evidence["batches"][arm] = batches
    evidence["summary"] = summarize(evidence)
    (OUTPUT / "live-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def render(evidence):
    from PIL import Image, ImageDraw, ImageFont

    summary = summarize(evidence)
    assert summary == evidence["summary"]
    image = Image.new("RGB", (1600, 1100), "#101827")
    draw = ImageDraw.Draw(image)
    fonts = Path("/System/Library/Fonts/Supplemental")

    def text(position, value, size=28, color="#e9eef7", bold=False):
        font = ImageFont.truetype(str(fonts / ("Arial Bold.ttf" if bold else "Arial.ttf")), size)
        draw.text(position, value, font=font, fill=color)

    text((65, 45), "PR #7 / Live GPQA-Diamond before vs after", 43, bold=True)
    text((65, 115), "100 identical questions per arm | Requested: pareto-26.10-preview", 29, "#9fb3d0")
    text((65, 162), "Real API calls, exact commit snapshots, alternating 10-question batches", 26)
    for arm, left, accent in (("before", 65, "#9dbdff"), ("after", 825, "#73e0b1")):
        metrics = summary[arm]
        draw.rounded_rectangle((left, 225, left + 710, 645), radius=22, fill="#1b273b")
        text((left + 30, 255), arm.upper() + " / " + evidence[f"{arm}_commit"][:7], 29, accent, True)
        text((left + 30, 315), f"{metrics['correct']} / 100 correct", 49, accent, True)
        text((left + 30, 400), "Task errors: 0", 28)
        mean_cost = metrics["mean_response_cost_usd"]
        text((left + 30, 451), f"Response cost / priced task: ${mean_cost:.5f}", 27)
        text((left + 30, 502), f"Priced tasks: {metrics['priced_tasks']} / 100", 27)
        text((left + 30, 553), f"Median task wall time: {metrics['median_wall_latency_s']:.2f}s", 27)
    paired = summary["paired"]
    lower, upper = paired["approximate_95_percent_ci"]
    text((65, 687), f"Accuracy change: {paired['delta_percentage_points']:+.1f} percentage points", 34, bold=True)
    text((65, 744), f"Approximate paired 95% interval: {lower:+.1f} to {upper:+.1f} points", 29)
    text((65, 795), f"Improved: {paired['improved']} | Regressed: {paired['regressed']} | Unchanged: {paired['unchanged']}", 27)
    text((65, 862), "A measured comparison, not proof of no regression or advertised-score parity.", 28, "#ffd28e", True)
    text((65, 919), "Nondeterministic responses; interrupted after 60/arm, resumed with unchanged settings.", 25, "#9fb3d0")
    text((65, 962), "Response-reported costs only; full billing and returned model identity unverified.", 25, "#9fb3d0")
    text((65, 1005), "Scope: PR #7, nonstreaming GPQA only. Source: live-evidence.json (no question text).", 25, "#9fb3d0")
    image.save(OUTPUT / "live-before-after.png")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, help="Export completed local audit batches before rendering")
    arguments = parser.parse_args()
    evidence = export(arguments.source) if arguments.source else json.loads((OUTPUT / "live-evidence.json").read_text())
    render(evidence)
