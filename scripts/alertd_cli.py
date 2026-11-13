"""alertd CLI — config export / import / validate from the shell.

Usage::

    export ALERTD_URL=http://localhost:5090
    export ALERTD_API_KEY=alertd_xxx

    python -m scripts.alertd_cli export > config.yaml
    python -m scripts.alertd_cli export --mask-secrets > shareable.yaml
    python -m scripts.alertd_cli validate config.yaml
    python -m scripts.alertd_cli import config.yaml          # dry-run
    python -m scripts.alertd_cli import config.yaml --apply  # commit

The script uses only stdlib + httpx (already a runtime dep). Runnable
inside or outside the container.

Exit codes:
- 0 on success
- 1 on connection / HTTP error
- 2 on validation errors (import/validate)
- 3 on missing env / bad usage
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx


def _env_required(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"error: ${name} not set", file=sys.stderr)
        sys.exit(3)
    return val


def _client() -> httpx.Client:
    base_url = os.environ.get("ALERTD_URL", "http://localhost:5090")
    api_key = _env_required("ALERTD_API_KEY")
    return httpx.Client(
        base_url=base_url,
        headers={"X-API-Key": api_key},
        timeout=30.0,
    )


def cmd_export(args: argparse.Namespace) -> int:
    with _client() as client:
        params = {"mask_secrets": "true"} if args.mask_secrets else {}
        try:
            r = client.get("/v1/config/export", params=params)
        except httpx.HTTPError as e:
            print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
    if r.status_code != 200:
        print(f"error: HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(r.text, encoding="utf-8")
        print(f"Wrote {len(r.text)} bytes to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(r.text)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    body = _read_input(args.file)
    if body is None:
        return 3
    with _client() as client:
        try:
            r = client.post(
                "/v1/config/validate",
                content=body,
                headers={"Content-Type": "application/yaml"},
            )
        except httpx.HTTPError as e:
            print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
    return _print_plan_result(r)


def cmd_import(args: argparse.Namespace) -> int:
    body = _read_input(args.file)
    if body is None:
        return 3
    with _client() as client:
        try:
            r = client.post(
                "/v1/config/import",
                content=body,
                params={"apply": "true" if args.apply else "false"},
                headers={"Content-Type": "application/yaml"},
            )
        except httpx.HTTPError as e:
            print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
    rc = _print_plan_result(r)
    if rc == 0 and not args.apply:
        print("\n(dry-run — re-run with --apply to commit)", file=sys.stderr)
    return rc


def _read_input(path: str | None) -> str | None:
    if path == "-" or not path:
        if sys.stdin.isatty():
            print("error: no file given and stdin is a TTY", file=sys.stderr)
            return None
        return sys.stdin.read()
    p = Path(path)
    if not p.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return None
    return p.read_text(encoding="utf-8")


def _print_plan_result(r: httpx.Response) -> int:
    if r.status_code != 200:
        print(f"error: HTTP {r.status_code}: {r.text[:300]}", file=sys.stderr)
        return 1
    try:
        data = r.json()
    except json.JSONDecodeError:
        print(f"error: non-JSON response: {r.text[:200]}", file=sys.stderr)
        return 1

    ok = bool(data.get("ok"))
    creates: dict[str, list[str]] = data.get("creates", {})
    updates: dict[str, list[str]] = data.get("updates", {})
    errors = data.get("errors", [])
    warnings = data.get("warnings", [])

    print(f"  Status: {'ok' if ok else 'errors'}")
    print(f"  Created: {data.get('creates_total', 0)}")
    for section, items in creates.items():
        for name in items:
            print(f"    + {section:12} {name}")
    print(f"  Updated: {data.get('updates_total', 0)}")
    for section, items in updates.items():
        for name in items:
            print(f"    ~ {section:12} {name}")
    if warnings:
        print("  Warnings:")
        for w in warnings:
            print(f"    ! {w}")
    if errors:
        print("  Errors:")
        for e in errors:
            print(f"    ✗ {e}")
        return 2
    if data.get("applied"):
        print("\nApplied successfully.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alertd-cli",
        description="alertd configuration export / import / validate.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export", help="Dump full config as YAML")
    p_exp.add_argument(
        "--mask-secrets", action="store_true",
        help="Rewrite literal-looking secrets as env:UNKNOWN_* placeholders",
    )
    p_exp.add_argument("--output", "-o", help="Write to file instead of stdout")
    p_exp.set_defaults(func=cmd_export)

    p_val = sub.add_parser("validate", help="Validate a YAML file")
    p_val.add_argument("file", nargs="?", default="-", help="YAML file (or - for stdin)")
    p_val.set_defaults(func=cmd_validate)

    p_imp = sub.add_parser("import", help="Apply or dry-run a YAML file")
    p_imp.add_argument("file", nargs="?", default="-", help="YAML file (or - for stdin)")
    p_imp.add_argument(
        "--apply", action="store_true",
        help="Actually commit (default is dry-run)",
    )
    p_imp.set_defaults(func=cmd_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
