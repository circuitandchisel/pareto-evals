import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT = Path(__file__).resolve().parent
evidence = json.loads((OUTPUT / "evidence.json").read_text())
image = Image.new("RGB", (1600, 920), "#101827")
draw = ImageDraw.Draw(image)


def text(position, value, size=28, color="#e9eef7", bold=False):
    name = "Arial Bold.ttf" if bold else "Arial.ttf"
    candidates = [Path("/System/Library/Fonts/Supplemental") / name,
                  Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")]
    font = ImageFont.truetype(str(next(path for path in candidates if path.exists())), size)
    draw.text(position, value, font=font, fill=color)


text((65, 48), "PR #8  /  Blank answers must not earn credit", 44, bold=True)
text((65, 117), "ACTUAL BENCHMARK COMMAND  |  Controlled local endpoints  |  No live model calls", 25, "#9fb3d0")
draw.rounded_rectangle((65, 175, 1535, 295), radius=18, fill="#202c40")
text((90, 195), "Same 40 synthetic tasks in each version and condition", 30, bold=True)
text((90, 244), "20 blank + 10 correct + 10 wrong; judge absent, then judge returning HTTP 503.", 27)
for label, left, accent in (("before", 65, "#ff929b"), ("after", 825, "#73e0b1")):
    result = evidence["results"][label]
    absent = result["conditions"]["no_judge"]
    outage = result["conditions"]["judge_outage_http_503"]
    draw.rounded_rectangle((left, 330, left + 710, 725), radius=22, fill="#1b273b")
    text((left + 30, 358), f"{label.upper()}  /  {result['commit'][:7]}", 30, accent, True)
    text((left + 30, 425), f"{absent['blanks_credited']} / 20", 64, accent, True)
    text((left + 30, 510), "Blank answers wrongly credited", 29, bold=True)
    text((left + 30, 570), f"Reported score: {absent['summary']['accuracy']:.0f}%", 29)
    text((left + 30, 620), f"Same result during judge outage: {outage['blanks_credited']} / 20", 27)
    text((left + 30, 669), f"Outage judge requests (incl. retries): {outage['calls']['judge']}", 25)
text((65, 765), "Outcome: blanks are incorrect; the 10 genuinely correct fixture answers still pass.", 29, bold=True)
text((65, 825), "Synthetic regression evidence, not a Pareto accuracy benchmark or model improvement.", 25, "#9fb3d0")
text((65, 865), "Source: exact commit snapshots + python -m benchmarks.hle; all assertions passed.", 25, "#9fb3d0")
image.save(OUTPUT / "before-after.png")
