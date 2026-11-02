"""Discover official editions and propose a pinned manifest without model calls."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "arxivmath.json"
PATTERN = re.compile(r"MathArena/arxivmath-(0[1-9]|1[0-2])([0-9]{2})")
API = "https://huggingface.co/api/datasets"
ANCHOR = date(2026, 11, 2)


def edition(identifier):
    match = PATTERN.fullmatch(identifier) if isinstance(identifier, str) else None
    if not match:
        raise ValueError("Not an official dated ArXivMath question dataset")
    return date(2000 + int(match[2]), int(match[1]), 1)


def due(today):
    return (today - ANCHOR).days >= 0 and (today - ANCHOR).days % 14 == 0


def fetch(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "huggingface.co"
            or not parsed.path.startswith("/api/datasets") or parsed.fragment):
        raise ValueError("Unexpected discovery URL")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("Discovery redirects rejected")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=30) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("Unexpected discovery response")
        body = response.read(2_000_001)
        links = response.headers.get("Link", "")
    if len(body) > 2_000_000:
        raise ValueError("Discovery response too large")
    return json.loads(body), links


def discover(read=fetch):
    url = API + "?author=MathArena&search=arxivmath&limit=100"
    found = set()
    visited = set()
    for _ in range(20):
        if url in visited:
            raise ValueError("Repeated catalog page")
        visited.add(url)
        rows, links = read(url)
        if not isinstance(rows, list):
            raise ValueError("Invalid dataset listing")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid dataset entry")
            identifier = row.get("id")
            if isinstance(identifier, str) and PATTERN.fullmatch(identifier):
                found.add(identifier)
        following = re.findall(r'<([^>]+)>;\s*rel="next"', links)
        if not following:
            return sorted(found, key=edition)
        if len(following) != 1:
            raise ValueError("Ambiguous catalog pagination")
        url = following[0]
    raise ValueError("Dataset listing exceeded page limit")


def validated_metadata(identifier, data):
    month = edition(identifier)
    if (not isinstance(data, dict) or data.get("id") != identifier
            or data.get("private") is not False or data.get("gated") is not False
            or data.get("disabled") is not False
            or not re.fullmatch(r"[a-f0-9]{40}", str(data.get("sha", "")))):
        raise ValueError("Edition must be public, available and revision-pinned")
    card = data.get("cardData", {})
    if card.get("license") != "cc-by-sa-4.0":
        raise ValueError("License changed; manual review required")
    info = card.get("dataset_info", {})
    if not isinstance(info, dict):
        raise ValueError("Single dataset configuration required")
    fields = {field["name"]: field for field in info.get("features", [])}
    for name in ("problem", "answer"):
        if fields.get(name, {}).get("dtype") not in ("string", "large_string"):
            raise ValueError("Required text field missing")
    if fields.get("problem_idx", {}).get("dtype") not in ("int64", "string", "large_string"):
        raise ValueError("Required question ID missing")
    splits = info.get("splits", [])
    train = [split for split in splits if split.get("name") == "train"]
    if len(train) != 1 or type(train[0].get("num_examples")) is not int or not 1 <= train[0]["num_examples"] <= 10000:
        raise ValueError("Invalid train split count")
    return {"dataset": identifier, "revision": data["sha"], "edition": month.strftime("%Y-%m"),
            "split": "train", "rows": train[0]["num_examples"], "license": card["license"]}


def candidate(current, today, read=fetch):
    available = [identifier for identifier in discover(read) if edition(identifier) <= today]
    if not available:
        raise ValueError("No official dated editions discovered")
    identifier = available[-1]
    if edition(identifier) < edition(current["dataset"]):
        raise ValueError("Discovery would downgrade the current edition")
    metadata, _ = read(API + "/" + identifier)
    proposed = validated_metadata(identifier, metadata)
    pinned, _ = read(API + "/" + identifier + "/revision/" + proposed["revision"])
    if validated_metadata(identifier, pinned) != proposed:
        raise ValueError("Pinned metadata differs from discovered metadata")
    return proposed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-due", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.check_due:
        print("true" if due(date.today()) else "false")
        return
    current = json.loads(MANIFEST.read_text())
    proposed = candidate(current, date.today())
    if proposed == current:
        print("ArXivMath pin is current")
        return
    print(json.dumps({"previous": current, "proposed": proposed}, indent=2))
    if args.write:
        MANIFEST.write_text(json.dumps(proposed, indent=2) + "\n")


if __name__ == "__main__":
    main()
