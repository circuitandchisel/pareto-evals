"""Prepare MMMU-Pro (standard, 10-option) -> datasets/mmmu_pro.json.

Source: HF `MMMU/MMMU-Pro`. Encodes any images to base64 PNG for the multimodal message.
MMMU-Pro configs vary ("standard (10 options)" / "standard (4 options)" / "vision"); we try
the 10-option standard first and print available configs on failure.
"""
import ast
import base64
import io
import json
import os

from datasets import get_dataset_config_names, load_dataset

OUT = os.path.join(os.path.dirname(__file__), "mmmu_pro.json")
REPO = "MMMU/MMMU-Pro"
PREFERRED = ["standard (10 options)", "standard", "standard (4 options)"]


def _b64(img):
    img = img.convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main():
    tok = os.environ.get("HF_TOKEN")
    try:
        configs = get_dataset_config_names(REPO, token=tok)
        print("available configs:", configs)
    except Exception as e:
        print("config list failed:", str(e)[:200])
        configs = PREFERRED
    cfg = next((c for c in PREFERRED if c in configs), configs[0])
    print("using config:", cfg)
    ds = load_dataset(REPO, cfg, split="test", token=tok)
    print("row schema:", list(ds[0].keys()))
    items = []
    for i, ex in enumerate(ds):
        opts = ex.get("options")
        if isinstance(opts, str):
            try:
                opts = ast.literal_eval(opts)
            except Exception:
                opts = [opts]
        imgs = []
        for k in list(ex.keys()):
            if k.startswith("image") and ex[k] is not None and hasattr(ex[k], "convert"):
                imgs.append(_b64(ex[k]))
        items.append({"id": ex.get("id", str(i)), "question": ex.get("question"),
                      "options": opts, "answer": ex.get("answer"), "images": imgs})
    json.dump(items, open(OUT, "w"))
    print(f"wrote {len(items)} MMMU-Pro items -> {OUT}")


if __name__ == "__main__":
    main()
