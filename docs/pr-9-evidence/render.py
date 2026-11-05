import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT = Path(__file__).resolve().parent
evidence = json.loads((OUTPUT / "evidence.json").read_text())
image = Image.new("RGB", (1600, 920), "#101827")
draw = ImageDraw.Draw(image)


def text(position, value, size=28, color="#e9eef7", bold=False):
    candidates = [Path("/System/Library/Fonts/Supplemental") / ("Arial Bold.ttf" if bold else "Arial.ttf"),
                  Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")]
    font = ImageFont.truetype(str(next(path for path in candidates if path.exists())), size)
    draw.text(position, value, font=font, fill=color)


text((65, 48), "PR #9  /  An unknown cost is not a free task", 44, bold=True)
text((65, 117), "ACTUAL BENCHMARK COMMAND  |  Controlled local endpoints  |  No live model calls", 25, "#9fb3d0")
draw.rounded_rectangle((65, 175, 1535, 295), radius=18, fill="#202c40")
text((90, 195), "Same two correct synthetic tasks in both versions", 30, bold=True)
text((90, 244), "Task 1 reports $0.10. Task 2 has no cost data. Known subtotal stays $0.10.", 28)
for label, left, accent in (("before", 65, "#ff929b"), ("after", 825, "#73e0b1")):
    result = evidence["results"][label]
    summary = result["summary"]
    draw.rounded_rectangle((left, 330, left + 710, 725), radius=22, fill="#1b273b")
    text((left + 30, 358), f"{label.upper()}  /  {result['commit'][:7]}", 30, accent, True)
    text((left + 30, 425), f"${summary['cost_usd_per_task']:.2f} / task", 64, accent, True)
    text((left + 30, 510), "Divides by all tasks" if label == "before" else "Divides by known-cost tasks", 29, bold=True)
    text((left + 30, 570), "$0.10 / 2 tasks" if label == "before" else "$0.10 / 1 priced task", 29)
    text((left + 30, 620), f"Cost coverage: {summary['n_priced']} / {summary['n']}", 28)
    text((left + 30, 669), f"Correct answers: {summary['resolved']} / {summary['n']} (unchanged)", 27)
text((65, 765), "Outcome: missing prices no longer artificially lower the known-cost average.", 30, bold=True)
text((65, 825), "Partial coverage is not a full-run spend estimate. These are synthetic fixture prices.", 25, "#9fb3d0")
text((65, 865), "Source: exact commit snapshots + python -m benchmarks.hle; all assertions passed.", 25, "#9fb3d0")
image.save(OUTPUT / "before-after.png")
