#!/usr/bin/env python3
"""Tiny webhook sink for the demo — records POSTs, exposes GET /count."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

count = 0


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        global count
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", "replace")
        count += 1
        print(f"notification #{count}: {body}", flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"count": count}).encode())

    def log_message(self, *args: object) -> None:
        pass  # quiet


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
