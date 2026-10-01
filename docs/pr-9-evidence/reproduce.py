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
    "after": "31bc8b3479872acdea9d804008ef6151ae24c7ab",
}
calls = {"model": 0, "judge": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        judge = self.path.startswith("/judge")
        calls["judge" if judge else "model"] += 1
        response = {
            "id": "fixture", "object": "chat.completion", "created": 1,
            "model": "cost-fixture",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "YES" if judge else "ANSWER: 4"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
        if not judge and "[priced]" in request["messages"][0]["content"]:
            response["usage"]["cost"] = 0.1
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
evidence = {"scenario": "Two correct synthetic HLE tasks: one costs $0.10, one omits cost", "live_model_calls": 0, "results": {}}
try:
    for label, revision in REVISIONS.items():
        calls.update(model=0, judge=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = subprocess.check_output(["git", "archive", revision], cwd=REPOSITORY)
            subprocess.run(["tar", "-xf", "-", "-C", str(root)], input=archive, check=True)
            dataset = root / "fixture.json"
            dataset.write_text(json.dumps([
                {"id": kind, "question": f"[{kind}] What is 2 + 2?", "answer": "4"}
                for kind in ("priced", "unpriced")
            ]))
            environment = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
            environment.update({
                "MODEL_BASE_URL": base + "/model", "MODEL_API_KEY": "local-fixture",
                "MODEL_NAME": "cost-fixture", "MODEL_SEND_SAMPLING": "false", "MODEL_MAX_RETRIES": "0",
                "MODEL_TIMEOUT": "10", "HLE_FILE": str(dataset), "RESULT_NAME": "evidence", "CONC": "1",
                "JUDGE_BASE_URL": base + "/judge", "JUDGE_API_KEY": "local-fixture", "JUDGE_MODEL": "judge-fixture",
            })
            process = subprocess.run([sys.executable, "-m", "benchmarks.hle"], cwd=root, env=environment,
                                     text=True, capture_output=True, timeout=60)
            summary = json.loads((root / "results/evidence.summary.json").read_text())
            rows = [json.loads(line) for line in (root / "results/evidence.jsonl").read_text().splitlines()]
            assert process.returncode == 0, process.stderr
            assert summary["n"] == 2 and summary["resolved"] == 2 and summary["errored"] == 0
            assert summary["n_priced"] == 1 and summary["cost_usd_total"] == 0.1
            assert summary["cost_usd_per_task"] == (0.05 if label == "before" else 0.1)
            assert [row["cost_usd"] for row in rows] == [0.1, None]
            assert calls == {"model": 2, "judge": 2}
            evidence["results"][label] = {
                "commit": revision, "command": "python -m benchmarks.hle", "exit_code": process.returncode,
                "calls": dict(calls), "summary": summary, "jsonl": rows, "stdout": process.stdout, "stderr": process.stderr,
            }
            print(f"{label}: $/task={summary['cost_usd_per_task']}; coverage=1/2; all assertions passed")
finally:
    server.shutdown()
    server.server_close()
(OUTPUT / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
