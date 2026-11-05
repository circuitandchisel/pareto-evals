import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
REVISIONS = {
    "before": "984f576dc58d41aa6dd34448b831fe2e64243c0b",
    "after": "090a3e78305b0ef1a3af1a24ea9347425212db4c",
}
calls = {"model": 0, "judge": 0}
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        judge = self.path.startswith("/judge")
        with lock:
            calls["judge" if judge else "model"] += 1
        if judge:
            response = {"error": {"message": "Controlled judge outage", "type": "server_error"}}
        else:
            question = request["messages"][0]["content"]
            answer = "" if "[blank]" in question else ("4" if "[correct]" in question else "9")
            response = {
                "id": "fixture", "object": "chat.completion", "created": 1,
                "model": "controlled-fixture",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": f"ANSWER: {answer}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        body = json.dumps(response).encode()
        self.send_response(503 if judge else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
items = [
    {"id": f"{kind}-{index}", "question": f"[{kind}] What is 2 + 2?", "answer": "4"}
    for kind, count in (("blank", 20), ("correct", 10), ("wrong", 10))
    for index in range(count)
]
evidence = {
    "scenario": "40 synthetic tasks per version per condition: 20 blank, 10 correct, 10 wrong",
    "conditions": ["no_judge", "judge_outage_http_503"],
    "live_model_calls": 0,
    "results": {},
}
try:
    for label, revision in REVISIONS.items():
        evidence["results"][label] = {"commit": revision, "conditions": {}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = subprocess.check_output(["git", "archive", revision], cwd=REPOSITORY)
            subprocess.run(["tar", "-xf", "-", "-C", str(root)], input=archive, check=True)
            dataset = root / "fixture.json"
            dataset.write_text(json.dumps(items))
            for condition in evidence["conditions"]:
                calls.update(model=0, judge=0)
                environment = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
                environment.update({
                    "MODEL_BASE_URL": base + "/model", "MODEL_API_KEY": "local-fixture",
                    "MODEL_NAME": "controlled-fixture", "MODEL_SEND_SAMPLING": "false",
                    "MODEL_MAX_RETRIES": "0", "MODEL_TIMEOUT": "10", "HLE_FILE": str(dataset),
                    "RESULT_NAME": "evidence", "CONC": "4", "JUDGE_TIMEOUT": "10",
                })
                if condition != "no_judge":
                    environment.update(JUDGE_BASE_URL=base + "/judge", JUDGE_API_KEY="local-fixture", JUDGE_MODEL="unavailable-fixture")
                process = subprocess.run(
                    [sys.executable, "-m", "benchmarks.hle"], cwd=root, env=environment,
                    text=True, capture_output=True, timeout=180,
                )
                summary = json.loads((root / "results/evidence.summary.json").read_text())
                rows = [json.loads(line) for line in (root / "results/evidence.jsonl").read_text().splitlines()]
                blanks_credited = sum(row["correct"] for row in rows if row["id"].startswith("blank-"))
                assert process.returncode == 0, process.stderr
                assert summary["n"] == 40 and summary["errored"] == 0
                assert blanks_credited == (20 if label == "before" else 0)
                assert summary["resolved"] == (30 if label == "before" else 10)
                assert calls["model"] == 40
                assert calls["judge"] == (0 if condition == "no_judge" else (120 if label == "before" else 60)), calls
                evidence["results"][label]["conditions"][condition] = {
                    "command": "python -m benchmarks.hle", "exit_code": process.returncode,
                    "calls": dict(calls), "blanks_credited": blanks_credited,
                    "summary": summary, "rows": rows, "stdout": process.stdout, "stderr": process.stderr,
                }
                print(f"{label} / {condition}: {blanks_credited}/20 blanks credited; {summary['accuracy']}% score; calls={calls}", flush=True)
finally:
    server.shutdown()
    server.server_close()
(OUTPUT / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
