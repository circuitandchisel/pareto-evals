#!/usr/bin/env python3
"""OpenAI-compatible reverse proxy that strips non-default sampling params.

Why this exists
---------------
The agentic wrappers in this directory drive your model through external agent
harnesses (mini-swe-agent, terminus-2, OpenHands) that hard-code sampling
parameters — typically `temperature=0`, and often a `stop` sequence. Some
OpenAI-compatible endpoints (notably the Pareto gpu-router) reject any
NON-DEFAULT sampler with HTTP 400: they accept only `temperature=1`, `top_p=1`,
etc., plus an empty/absent `stop`. Against such an endpoint every agent call
fails on the first request.

This proxy sits between the harness and the endpoint, removes the offending keys
from each JSON request body (so the endpoint falls back to its own defaults), and
forwards everything else unchanged — path, auth headers, and streaming responses.
Point the harness's MODEL_BASE_URL at this proxy instead of the raw endpoint.

If your endpoint accepts standard sampling params, you do not need this proxy.

Usage
-----
    UPSTREAM=https://your-endpoint/v1 PORT=8900 BIND=0.0.0.0 python3 strip_proxy.py

Then run a wrapper with MODEL_BASE_URL pointing at the proxy. Use the Docker
gateway address for harnesses whose agent runs in a container:

    MODEL_BASE_URL=http://172.17.0.1:8900/v1 ./run_tb.sh

DeepSWE (pier) note: pier isolates the agent behind a squid egress proxy that
only permits ports 80 and 443. Run a second instance of THIS proxy on a safe
port for that harness:

    sudo env UPSTREAM=https://your-endpoint/v1 PORT=80 BIND=0.0.0.0 python3 strip_proxy.py
    MODEL_BASE_URL=http://172.17.0.1/v1 ./run_deepswe.sh

Env vars: UPSTREAM (required, /v1 base), PORT (default 8900), BIND (default
0.0.0.0 so containers can reach it via the Docker gateway), STRIP_PARAMS
(comma-separated override of the stripped keys).
"""
import os
import sys
import json
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ["UPSTREAM"].rstrip("/")
PORT = int(os.environ.get("PORT", "8900"))
BIND = os.environ.get("BIND", "0.0.0.0")
_DEFAULT_STRIP = "temperature,top_p,top_k,min_p,frequency_penalty,presence_penalty,repetition_penalty,stop"
STRIP = {k.strip() for k in os.environ.get("STRIP_PARAMS", _DEFAULT_STRIP).split(",") if k.strip()}


def _log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass  # silence default per-request access logging; we log our own below

    def _proxy(self, method):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""

        stripped = []
        if body:
            try:
                obj = json.loads(body)
                if isinstance(obj, dict):
                    for k in list(obj):
                        if k in STRIP:
                            obj.pop(k)
                            stripped.append(k)
                    if stripped:
                        body = json.dumps(obj).encode()
            except (ValueError, TypeError):
                pass  # not JSON — forward untouched

        # Map /v1/... onto the UPSTREAM base (which already ends in /v1).
        path = self.path[len("/v1"):] if self.path.startswith("/v1") else self.path
        url = UPSTREAM + path
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length", "accept-encoding")}
        headers["Content-Length"] = str(len(body))
        if stripped:
            _log(f"[strip] {method} {self.path} removed {stripped}")

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            up = urllib.request.urlopen(req, timeout=1800)
        except urllib.error.HTTPError as e:
            data = e.read()
            _log(f"[upstream {e.code}] {method} {self.path}: {data[:200]!r}")
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        except Exception as e:  # noqa: BLE001 — surface any transport error to the client
            msg = json.dumps({"error": {"message": f"proxy: {e}", "type": "proxy_error"}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        ctype = up.headers.get("Content-Type", "application/json")
        self.send_response(up.status)
        self.send_header("Content-Type", ctype)
        if "event-stream" in ctype:  # stream SSE straight through, chunked
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            while True:
                chunk = up.read(4096)
                if not chunk:
                    break
                self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        else:
            data = up.read()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def do_POST(self):
        self._proxy("POST")

    def do_GET(self):
        self._proxy("GET")


if __name__ == "__main__":
    _log(f"strip-proxy: {BIND}:{PORT} -> {UPSTREAM} (stripping {sorted(STRIP)})")
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
