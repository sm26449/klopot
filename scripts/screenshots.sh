#!/usr/bin/env bash
# screenshots.sh — README screenshots of the admin UI, from synthetic data.
#
#   scripts/screenshots.sh            # build, start a throwaway install, seed, shoot, remove
#   scripts/screenshots.sh --no-build # reuse klopot:e2e from a previous run
#
# Runs scripts/e2e.sh without its tests (a clean first install: the e2e seed
# data would show), then — on that stack, before it is removed — starts a local HTTP
# sink so webhook / ntfy / Gotify deliveries succeed without leaving the
# machine, seeds a demo site through the API and writes the PNGs to
# docs/screenshots/. Nothing here touches any other container or real data.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${E2E_URL:-}" ]; then
  # Outer call: let the e2e harness start the stack and call us back inside it.
  E2E_ONLY=none E2E_AFTER="scripts/screenshots.sh" exec scripts/e2e.sh "$@"
fi

# Inner call (E2E_AFTER): the stack is up; screenshots.mjs sets the password.
SINK="${E2E_NETWORK%-net}-sink"
cleanup() { docker rm -f "$SINK" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Answers 200 {"id": …} to anything — except a path containing "flaky", which
# answers 503 so one channel shows a retry in the delivery timeline.
docker run -d --rm --name "$SINK" --network "$E2E_NETWORK" --entrypoint python "$E2E_IMAGE" -c '
import http.server, json
class H(http.server.BaseHTTPRequestHandler):
    def _answer(self):
        self.rfile.read(int(self.headers.get("content-length") or 0))
        flaky = "flaky" in self.path
        body = b"service unavailable - retry later" if flaky else json.dumps({"id": "demo", "ok": True}).encode()
        self.send_response(503 if flaky else 200)
        self.send_header("content-type", "text/plain" if flaky else "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    do_POST = do_GET = do_PUT = _answer
    def log_message(self, *args):
        pass
http.server.ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
' >/dev/null

SINK_URL="http://$SINK:8080" node scripts/screenshots.mjs
