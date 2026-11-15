#!/usr/bin/env bash
# generate_sdks.sh — regenerate the client SDKs from openapi/v1.json.
#
#   scripts/generate_sdks.sh            # write sdk/python/ and sdk/typescript/src/schema.d.ts
#   scripts/generate_sdks.sh --check    # regenerate into a temp dir and fail on drift
#
# Python: openapi-python-client (pinned in pyproject [dev]) → sdk/python (package klopot_client).
# TypeScript: openapi-typescript (pinned in package.json) → sdk/typescript/src/schema.d.ts; the
# fetch wrapper sdk/typescript/src/index.js is hand-written and not touched here.
# Never edit the generated files by hand. Endpoints whose body is YAML
# (/v1/config/validate, /import, /import/preview) are not generated — call them with plain HTTP.
set -euo pipefail
cd "$(dirname "$0")/.."

# The project virtualenv locally; CI installs into the runner's Python (on PATH).
OPC=""
for c in .venv/bin/openapi-python-client venv/bin/openapi-python-client; do
  [ -x "$c" ] && { OPC="$PWD/$c"; break; }
done
[ -n "$OPC" ] || OPC="$(command -v openapi-python-client)" \
  || { echo "openapi-python-client not found (pip install -e '.[dev]')" >&2; exit 1; }
SPEC=openapi/v1.json
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1

out="$(mktemp -d)"; trap 'rm -rf "$out"' EXIT
( cd "$out" && "$OPC" generate --path "$OLDPWD/$SPEC" \
    --config "$OLDPWD/sdk/python-client.yaml" --meta pdm --output-path python >/dev/null 2>&1 ) \
  || { echo "openapi-python-client failed" >&2; exit 1; }
npx --no-install openapi-typescript "$SPEC" --output "$out/schema.d.ts" >/dev/null 2>&1 \
  || { echo "openapi-typescript failed (run npm ci)" >&2; exit 1; }

if [ "$CHECK" = 1 ]; then
  rc=0
  diff -rq -x __pycache__ "$out/python" sdk/python >/dev/null || { echo "sdk/python is out of date — run scripts/generate_sdks.sh"; rc=1; }
  cmp -s "$out/schema.d.ts" sdk/typescript/src/schema.d.ts || { echo "sdk/typescript/src/schema.d.ts is out of date — run scripts/generate_sdks.sh"; rc=1; }
  [ "$rc" = 0 ] && echo "SDKs match openapi/v1.json"
  exit "$rc"
fi
rm -rf sdk/python && cp -r "$out/python" sdk/python
cp "$out/schema.d.ts" sdk/typescript/src/schema.d.ts
echo "wrote sdk/python ($(find sdk/python -name '*.py' | wc -l) files) and sdk/typescript/src/schema.d.ts"
