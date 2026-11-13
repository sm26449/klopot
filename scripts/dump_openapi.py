#!/usr/bin/env python3
"""Dump the canonical OpenAPI spec to openapi/v1.json.

Deterministic: sorted keys, 2-space indent, trailing newline. CI regenerates
this and fails if it drifts from the committed file, so the snapshot (the input
for generated SDKs and the oasdiff breaking-change gate) stays in lockstep with
the code. Run after any change to the /v1 surface:

    .venv/bin/python scripts/dump_openapi.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Schema generation only introspects the routes; no DB connection is made.
os.environ.setdefault("ALERTD_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ALERTD_MQTT_HOST", "")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app

OUT = Path(__file__).resolve().parent.parent / "openapi" / "v1.json"


def main() -> None:
    spec = create_app().openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        json.dump(spec, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {OUT} ({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
