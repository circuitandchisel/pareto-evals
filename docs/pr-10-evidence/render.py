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


text((65, 48), "PR #10  /  Preserve CRLF-streamed answers", 44, bold=True)
text((65, 117), "ACTUAL PROXY + BENCHMARK COMMAND  |  Local fixtures  |  No live model calls", 25, "#9fb3d0")
draw.rounded_rectangle((65, 175, 1535, 295), radius=18, fill="#202c40")
text((90, 195), "Same 40 synthetic tasks through each version of the real proxy", 30, bold=True)
text((90, 244), "20 LF streams + 20 CRLF streams. Every upstream answer is correct: ANSWER: 4.", 27)
for label, left, accent in (("before", 65, "#ff929b"), ("after", 825, "#73e0b1")):
    result = evidence["results"][label]
    groups = result["groups"]
    draw.rounded_rectangle((left, 330, left + 710, 725), radius=22, fill="#1b273b")
    text((left + 30, 358), f"{label.upper()}  /  {result['commit'][:7]}", 30, accent, True)
    text((left + 30, 425), f"{groups['crlf']['correct']} / {groups['crlf']['n']}", 64, accent, True)
    text((left + 30, 510), "CRLF answers recovered and correct", 29, bold=True)
    text((left + 30, 570), f"CRLF empty-response errors: {groups['crlf']['errors']}", 28)
    text((left + 30, 620), f"LF control: {groups['lf']['correct']} / {groups['lf']['n']} correct (unchanged)", 28)
    text((left + 30, 669), f"Fixture score: {result['summary']['accuracy']:.0f}%", 27)
text((65, 765), "Outcome: valid streamed answers no longer disappear because of line endings.", 29, bold=True)
text((65, 825), "Synthetic transport regression evidence, not a live Pareto accuracy improvement.", 25, "#9fb3d0")
checks = evidence["results"]["after"]["parser_split_checks"]
total = sum(result["partitions"] for result in checks.values())
text((65, 865), f"Also verified: {total} LF/CRLF parser partitions, including byte-at-a-time reads.", 25, "#9fb3d0")
image.save(OUTPUT / "before-after.png")
