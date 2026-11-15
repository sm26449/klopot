"""Generate a Markdown catalog from a rules-pack / exported-config YAML.

The output is a human-friendly catalog of every notification template
+ rule in the YAML, including:

  - title / icon / severity / cooldown
  - trigger summary + full markdown logic block
  - which channels each template routes to
  - which schedules dispatch the template

Run::

    python scripts/generate_rules_doc.py \\
        --input exported-config.yaml \\
        --output RULES.md

Idempotent: re-running with the same input produces the same output
(no random IDs, no timestamps in body — only the deterministic source).

Why a generator and not a hand-written doc?
  Rules drift. Operators tune ``thresh.*`` constants in production via
  PATCH /v1/variables/{name}. Whenever they re-export the running
  config (``scripts/alertd_cli.py export``) they can run this generator
  over the exported YAML and refresh the catalog to match reality. The
  repository itself ships no generated catalog.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
SEVERITY_BADGE = {
    "info": "🟢 info",
    "warning": "🟡 warning",
    "critical": "🔴 critical",
}


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        sys.exit(f"input not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        sys.exit("input YAML must be a mapping at top level")
    return data


def render(data: dict[str, Any], source_note: str | None = None) -> str:
    templates: list[dict] = data.get("templates") or []
    rules: list[dict] = data.get("rules") or []
    routes: list[dict] = data.get("routes") or []
    schedules: list[dict] = data.get("schedules") or []
    variables: list[dict] = data.get("variables") or []

    # Index helpers
    rules_by_template: dict[str, list[dict]] = defaultdict(list)
    for r in rules:
        rules_by_template[r.get("template_type", "")].append(r)

    routes_by_template: dict[str, list[dict]] = defaultdict(list)
    for r in routes:
        routes_by_template[r.get("template", "")].append(r)

    schedules_by_template: dict[str, list[dict]] = defaultdict(list)
    for s in schedules:
        schedules_by_template[s.get("template_type", "")].append(s)

    # Sort: severity (critical→warning→info) then alphabetical type
    def sort_key(t: dict) -> tuple[int, str]:
        sev = t.get("severity", "info")
        return (-SEVERITY_ORDER.get(sev, 0), t.get("type", ""))

    sorted_templates = sorted(templates, key=sort_key)

    out: list[str] = []
    out.append("# Notification Rules Catalog")
    out.append("")
    out.append(
        f"> Auto-generated from `{source_note or 'docs/standard_rules_pack.yaml'}` by "
        "`scripts/generate_rules_doc.py`. Do not edit by hand — "
        "regenerate after the source changes."
    )
    out.append("")
    out.append("This document describes every alert this deployment can fire,")
    out.append("how it's triggered, what it says, and where it goes.")
    out.append("")

    # ── Summary table ────────────────────────────────────────────
    out.append("## Summary")
    out.append("")
    out.append("| Type | Severity | Cooldown | Channels | Trigger |")
    out.append("|------|----------|----------|----------|---------|")

    for t in sorted_templates:
        ttype = t.get("type", "")
        sev = SEVERITY_BADGE.get(t.get("severity", "info"), t.get("severity", ""))
        cd = t.get("min_repeat_min")
        cd_str = "—" if not cd else _fmt_duration_min(cd)
        channels = sorted({r.get("channel", "") for r in routes_by_template[ttype]})
        ch_str = ", ".join(channels) if channels else "—"
        rule_match = rules_by_template.get(ttype, [])
        if schedules_by_template.get(ttype):
            trig = "scheduled (cron)"
        elif rule_match and any(r.get("enabled", True) for r in rule_match):
            trig = next(
                (r.get("trigger_summary") for r in rule_match if r.get("trigger_summary")),
                "(see rule)",
            )
        elif rule_match:
            trig = "_disabled_ — manual fire only"
        else:
            trig = "manual fire only (POST /v1/fire)"
        out.append(f"| `{ttype}` | {sev} | {cd_str} | {ch_str} | {trig} |")

    out.append("")
    out.append(f"**Total templates:** {len(templates)}  ·  ")
    out.append(f"**Total rules:** {len(rules)}  ·  ")
    out.append(f"**Total schedules:** {len(schedules)}  ·  ")
    out.append(f"**Total variables:** {len(variables)}")
    out.append("")

    # ── Per-template detail ──────────────────────────────────────
    out.append("## Details")
    out.append("")

    for t in sorted_templates:
        ttype = t.get("type", "")
        sev = t.get("severity", "info")

        out.append(f"### {t.get('icon', '')} `{ttype}`")
        out.append("")
        out.append(f"- **Severity:** {SEVERITY_BADGE.get(sev, sev)}")
        cd = t.get("min_repeat_min")
        out.append(f"- **Cooldown:** {_fmt_duration_min(cd) if cd else 'no throttle'}")

        title_tpl = t.get("title_template") or ""
        msg_tpl = t.get("message_template") or ""
        if title_tpl:
            out.append(f"- **Title:** `{title_tpl}`")
        if msg_tpl:
            out.append(f"- **Message:** `{msg_tpl}`")
        if t.get("description"):
            out.append(f"- **Description:** {t['description']}")
        if not t.get("enabled", True):
            out.append("- **Status:** ⏸️ disabled in pack")
        out.append("")

        # Rules → trigger logic
        for r in rules_by_template.get(ttype, []):
            ena = "" if r.get("enabled", True) else " _(disabled)_"
            out.append(f"#### Rule: `{r.get('name', '?')}`{ena}")
            out.append("")
            if r.get("trigger_summary"):
                out.append(f"_{r['trigger_summary']}_")
                out.append("")
            cond = r.get("condition_expr") or ""
            if cond and cond.strip().lower() != "false":
                out.append("**Expression:**")
                out.append("")
                out.append("```python")
                out.append(cond.strip())
                out.append("```")
                out.append("")
            persist = r.get("persist_n", 1)
            interval = r.get("eval_interval_sec", 30)
            sustain = persist * interval
            out.append(
                f"**Persistence:** {persist} consecutive ticks × "
                f"{interval}s eval = sustained for {_fmt_duration_sec(sustain)}"
            )
            out.append("")
            extracted = r.get("vars_extract") or []
            if extracted:
                out.append("**Variables consumed:** "
                          + ", ".join(f"`{v}`" for v in extracted))
                out.append("")
            inhibitors = r.get("inhibited_by") or []
            if inhibitors:
                out.append("**Inhibited by:** "
                          + ", ".join(f"`{v}`" for v in inhibitors)
                          + " _(suppressed while any of these is active)_")
                out.append("")
            logic = r.get("trigger_logic_md") or ""
            if logic.strip():
                out.append(logic.rstrip())
                out.append("")

        # Schedules
        for s in schedules_by_template.get(ttype, []):
            out.append(f"#### Schedule: `{s.get('name', '?')}`")
            out.append("")
            out.append(f"Cron: `{s.get('cron_expr', '?')}`")
            ena = s.get("enabled", True)
            out.append(f"Enabled: **{'yes' if ena else 'no'}**")
            out.append("")

        # Routes
        rts = routes_by_template.get(ttype, [])
        if rts:
            out.append("**Routes:**")
            out.append("")
            for r in rts:
                sev_min = r.get("severity_min", "info")
                out.append(f"- `{r.get('channel', '?')}` (severity ≥ {sev_min})")
            out.append("")

        out.append("---")
        out.append("")

    # ── Variables appendix ───────────────────────────────────────
    out.append("## Variables")
    out.append("")
    out.append(
        "Tunable thresholds and live data sources. Constants can be "
        "adjusted at runtime via `PATCH /v1/variables/{name}`."
    )
    out.append("")
    out.append("| Name | Source | Description | Stale after |")
    out.append("|------|--------|-------------|-------------|")
    for v in sorted(variables, key=lambda x: x.get("name", "")):
        name = v.get("name", "")
        src = v.get("source", "")
        desc = (v.get("description") or "").replace("|", "\\|")
        stale = (v.get("config") or {}).get("stale_after_sec")
        stale_str = f"{stale}s" if stale else "—"
        out.append(f"| `{name}` | {src} | {desc} | {stale_str} |")
    out.append("")

    # ── Footer ───────────────────────────────────────────────────
    out.append("## Adjusting at runtime")
    out.append("")
    out.append("```bash")
    out.append("# Change a threshold")
    out.append("curl -X PATCH http://alertd:5090/v1/variables/thresh.soc_low_pct \\")
    out.append("  -H 'X-API-Key: $ALERTD_KEY' -H 'Content-Type: application/json' \\")
    out.append("  -d '{\"config\": {\"value\": 25}}'")
    out.append("")
    out.append("# Disable a rule")
    out.append("curl -X PATCH http://alertd:5090/v1/rules/{id} \\")
    out.append("  -H 'X-API-Key: $ALERTD_KEY' -H 'Content-Type: application/json' \\")
    out.append("  -d '{\"enabled\": false}'")
    out.append("")
    out.append("# Snooze a template type for 1h")
    out.append("curl -X POST http://alertd:5090/v1/snooze \\")
    out.append("  -H 'X-API-Key: $ALERTD_KEY' -H 'Content-Type: application/json' \\")
    out.append("  -d '{\"scope\": \"type\", \"target\": \"disk_full\", "
               "\"until\": \"2026-07-06T21:00:00Z\", \"reason\": \"maintenance\"}'")
    out.append("")
    out.append("# Manually fire (e.g. for testing or for state-transition templates)")
    out.append("curl -X POST http://alertd:5090/v1/fire \\")
    out.append("  -H 'X-API-Key: $ALERTD_KEY' -H 'Content-Type: application/json' \\")
    out.append("  -d '{\"type\": \"daily_summary\", \"context\": {\"alerts_today\": 12}}'")
    out.append("```")
    out.append("")

    return "\n".join(out) + "\n"


def _fmt_duration_min(minutes: int | float) -> str:
    if minutes >= 1440:
        return f"{minutes // 1440}d"
    if minutes >= 60:
        return f"{minutes // 60}h"
    return f"{minutes}min"


def _fmt_duration_sec(seconds: int | float) -> str:
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60}m"
    if seconds >= 60:
        return f"{seconds // 60}m{seconds % 60}s" if seconds % 60 else f"{seconds // 60}m"
    return f"{seconds}s"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument(
        "--input", "-i", type=Path, required=True,
        help="path to YAML pack (e.g. docs/standard_rules_pack.yaml), '-' = stdin",
    )
    parser.add_argument(
        "--output", "-o", type=Path, required=True,
        help="path to write the markdown doc to",
    )
    parser.add_argument(
        "--source-note", default=None,
        help="source description for the doc header "
             "(default: docs/standard_rules_pack.yaml)",
    )
    args = parser.parse_args()

    if str(args.input) == "-":
        data = yaml.safe_load(sys.stdin) or {}
        if not isinstance(data, dict):
            sys.exit("input YAML must be a mapping at top level")
    else:
        data = load(args.input)
    md = render(data, source_note=args.source_note)
    args.output.write_text(md, encoding="utf-8")
    print(f"wrote {args.output} ({len(md)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
