import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
REVISIONS = {
    "before": "984f576dc58d41aa6dd34448b831fe2e64243c0b",
    "after": "e059b89c7652d8447780e0bcdbe716c1f3bc5518",
}
calls = {"lf": 0, "crlf": 0, "judge": 0}
lock = threading.Lock()
frames = [
    {"id": "fixture", "model": "stream-fixture", "created": 1,
     "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ANSWER: "}}]},
    {"choices": [{"index": 0, "delta": {"content": "4"}, "finish_reason": "stop"}]},
    {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}},
]


def stream_bytes(ending):
    return b"".join(b"data: " + json.dumps(frame).encode() + ending * 2 for frame in frames) + b"data: [DONE]" + ending * 2


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        judge = self.path.startswith("/judge")
        kind = "judge" if judge else ("crlf" if "[crlf]" in request["messages"][0]["content"] else "lf")
        with lock:
            calls[kind] += 1
        if judge:
            body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "YES"}}]}).encode()
        else:
            assert request["stream"] is True
            assert request["stream_options"]["include_usage"] is True
            body = stream_bytes(b"\r\n" if kind == "crlf" else b"\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if judge else "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Chunks:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def read(self, size):
        return next(self.chunks, b"")


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
evidence = {
    "scenario": "40 synthetic HLE tasks per version through the actual proxy: 20 LF, 20 CRLF; all upstream answers are correct",
    "live_model_calls": 0, "results": {},
}
try:
    for label, revision in REVISIONS.items():
        calls.update(lf=0, crlf=0, judge=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = subprocess.check_output(["git", "archive", revision], cwd=REPOSITORY)
            subprocess.run(["tar", "-xf", "-", "-C", str(root)], input=archive, check=True)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            environment = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
            environment.update(UPSTREAM=base + "/v1", UPSTREAM_STREAM="1", BIND="127.0.0.1", PORT=str(port))
            proxy_log = root / "proxy.log"
            with proxy_log.open("w") as log:
                proxy = subprocess.Popen([sys.executable, "agentic/strip_proxy.py"], cwd=root, env=environment, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        assert proxy.poll() is None, proxy_log.read_text()
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                                break
                        except OSError:
                            if time.monotonic() > deadline:
                                raise TimeoutError("Proxy did not start")
                            time.sleep(0.05)
                    dataset = root / "fixture.json"
                    dataset.write_text(json.dumps([
                        {"id": f"{kind}-{index}", "question": f"[{kind}] What is 2 + 2?", "answer": "4"}
                        for kind in ("lf", "crlf") for index in range(20)
                    ]))
                    environment.update({
                        "MODEL_BASE_URL": f"http://127.0.0.1:{port}/v1", "MODEL_API_KEY": "local-fixture",
                        "MODEL_NAME": "stream-fixture", "MODEL_SEND_SAMPLING": "false", "MODEL_MAX_RETRIES": "0",
                        "MODEL_TIMEOUT": "10", "HLE_FILE": str(dataset), "RESULT_NAME": "evidence", "CONC": "4",
                        "JUDGE_BASE_URL": base + "/judge", "JUDGE_API_KEY": "local-fixture", "JUDGE_MODEL": "judge-fixture",
                    })
                    process = subprocess.run([sys.executable, "-m", "benchmarks.hle"], cwd=root, env=environment,
                                             text=True, capture_output=True, timeout=90)
                finally:
                    proxy.terminate()
                    try:
                        proxy.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proxy.kill()
                        proxy.wait()
            summary = json.loads((root / "results/evidence.summary.json").read_text())
            rows = [json.loads(line) for line in (root / "results/evidence.jsonl").read_text().splitlines()]
            groups = {}
            for kind in ("lf", "crlf"):
                subset = [row for row in rows if row["id"].startswith(kind + "-")]
                groups[kind] = {"n": len(subset), "correct": sum(row["correct"] for row in subset),
                                "errors": sum(bool(row.get("error")) for row in subset),
                                "with_usage": sum(bool(row.get("usage")) for row in subset)}
            assert process.returncode == 0, process.stderr
            assert groups["lf"] == {"n": 20, "correct": 20, "errors": 0, "with_usage": 20}
            assert groups["crlf"] == ({"n": 20, "correct": 0, "errors": 20, "with_usage": 0} if label == "before"
                                      else {"n": 20, "correct": 20, "errors": 0, "with_usage": 20})
            assert summary["accuracy"] == (50.0 if label == "before" else 100.0)
            assert calls == {"lf": 20, "crlf": 20, "judge": 20 if label == "before" else 40}
            for row in rows:
                if row.get("error"):
                    assert "EmptyResponseError" in row["error"]
                else:
                    assert row["pred"] == "4" and row["usage"]["total"] == 12 and row["finish"] == "stop"
            os.environ["UPSTREAM"] = base + "/v1"
            spec = importlib.util.spec_from_file_location("proxy_fixture", root / "agentic/strip_proxy.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            split_checks = {}
            for kind, ending in (("lf", b"\n"), ("crlf", b"\r\n")):
                payload = stream_bytes(ending)
                partitions = [[payload[:offset], payload[offset:]] for offset in range(1, len(payload))]
                partitions.append([payload[index:index + 1] for index in range(len(payload))])
                recovered = 0
                for chunks in partitions:
                    response = json.loads(module._reassemble_chat_completion(Chunks(chunks)))
                    if response["choices"]:
                        assert response["choices"][0]["message"]["content"] == "ANSWER: 4"
                        assert response["usage"]["total_tokens"] == 12
                        recovered += 1
                assert recovered == (0 if kind == "crlf" and label == "before" else len(partitions))
                split_checks[kind] = {"partitions": len(partitions), "recovered": recovered}
            evidence["results"][label] = {
                "commit": revision, "proxy_command": "UPSTREAM_STREAM=1 python agentic/strip_proxy.py",
                "benchmark_command": "python -m benchmarks.hle", "exit_code": process.returncode,
                "calls": dict(calls), "groups": groups, "summary": summary, "rows": rows,
                "stdout": process.stdout, "stderr": process.stderr, "proxy_log": proxy_log.read_text(),
                "parser_split_checks": split_checks,
            }
            print(f"{label}: {groups}; parser splits={split_checks}; all assertions passed", flush=True)
finally:
    server.shutdown()
    server.server_close()
(OUTPUT / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
