import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT = Path(__file__).resolve().parent
evidence = json.loads((OUTPUT / "evidence.json").read_text())
image = Image.new("RGB", (1600, 1000), "#101827")
draw = ImageDraw.Draw(image)
fonts = Path("/System/Library/Fonts/Supplemental")


def text(position, value, size=28, color="#e9eef7", bold=False):
    font = ImageFont.truetype(str(fonts / ("Arial Bold.ttf" if bold else "Arial.ttf")), size)
    draw.text(position, value, font=font, fill=color)


text((65, 48), "PR #7  /  Failed runs must not publish old scores", 44, bold=True)
text((65, 120), "CONTROLLED FAILURE TEST  |  100 synthetic saved results  |  No live model calls", 25, "#9fb3d0")
draw.rounded_rectangle((65, 185, 1535, 305), radius=18, fill="#202c40")
text((90, 205), "Identical setup for both versions", 28, bold=True)
text((90, 250), "Prior run: 80 / 100 correct. Next benchmark exits 23 before writing any results.", 28)

for label, left, accent, title in (
    ("before", 65, "#ff929b", "BEFORE  /  main"),
    ("after", 825, "#73e0b1", "AFTER  /  PR #7"),
):
    result = evidence["results"][label]
    draw.rounded_rectangle((left, 340, left + 710, 790), radius=22, fill="#1b273b")
    text((left + 30, 370), title, 30, accent, True)
    text((left + 30, 422), result["commit"][:7], 23, "#9fb3d0")
    text((left + 30, 477), "80.0%" if result["report"] else "NO SCORE", 64, accent, True)
    text((left + 30, 563), "Old score reported as current" if result["report"] else "Failed run rejected", 29, bold=True)
    text((left + 30, 625), f"CLI exit code: {result['exit_code']}" + (" (success)" if result["exit_code"] == 0 else " (failure)"), 27)
    text((left + 30, 673), "Markdown + CSV: " + ("published" if result["markdown_report_exists"] else "not published"), 27)
    text((left + 30, 721), "Previous results: " + ("reused" if result["old_jsonl_exists"] else "cleared before run"), 27)

text((65, 833), "Outcome: a failed benchmark can no longer look like a successful scored run.", 30, bold=True)
text((65, 895), "Synthetic regression evidence, not a Pareto accuracy benchmark or model improvement.", 25, "#9fb3d0")
text((65, 940), "Source: exact commit snapshots + real CLI subprocess execution; assertions passed.", 24, "#9fb3d0")
image.save(OUTPUT / "before-after.png")
