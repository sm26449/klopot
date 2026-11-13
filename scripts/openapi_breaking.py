#!/usr/bin/env python3
"""Conservative OpenAPI breaking-change check.

Compares an OLD spec against a NEW one and exits non-zero if the new spec
*removes* surface the old one promised: a path, an operation (method) on a
path, or a documented response status code. These are the breaking changes a
snapshot diff can hide behind reordering. Additions are fine.

    python scripts/openapi_breaking.py OLD.json NEW.json

This is intentionally small — not a full oasdiff. It guards the /v1 contract
without pulling an external, version-pinned tool into CI.
"""
from __future__ import annotations

import json
import sys


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def breaking_changes(old: dict, new: dict) -> list[str]:
    out: list[str] = []
    old_paths = old.get("paths", {})
    new_paths = new.get("paths", {})
    methods = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}

    for path, old_item in old_paths.items():
        if path not in new_paths:
            out.append(f"removed path: {path}")
            continue
        new_item = new_paths[path]
        for method, old_op in old_item.items():
            if method.lower() not in methods:
                continue
            if method not in new_item:
                out.append(f"removed operation: {method.upper()} {path}")
                continue
            old_codes = set((old_op.get("responses") or {}).keys())
            new_codes = set((new_item[method].get("responses") or {}).keys())
            for code in old_codes - new_codes:
                out.append(f"removed response {code}: {method.upper()} {path}")
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    changes = breaking_changes(_load(sys.argv[1]), _load(sys.argv[2]))
    if changes:
        print("BREAKING OpenAPI changes:")
        for c in changes:
            print(f"  - {c}")
        return 1
    print("no breaking OpenAPI changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
