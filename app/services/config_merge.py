"""Selective export and item-by-item import with conflict choices.

Built on top of :mod:`config_io` — the YAML pack format, validation, cross-
reference checks and the transactional upsert are all reused:

- :func:`export_selection` — a pack with only some sections, filtered by
  template category and/or identifiers, optionally with the templates and
  variables the selected rules need.
- :func:`preview_import` — every item in a pack classified as ``new``,
  ``identical`` or ``differs`` (with the changed fields) against the live
  configuration, plus the usual validation errors / warnings.
- :func:`apply_import` — turns per-item decisions into a pack (identical and
  skipped items removed, copies renamed) and hands it to
  ``config_io.import_config`` in one transaction.

Comparison happens on the *normalised* item: import fills an omitted field
with its default (``locale`` → ``en``, ``persist_n`` → 1 …), so a field the
file leaves out can still change the row on overwrite — the diff shows it.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ..channels import sms_config
from . import config_io
from .references import expression_vars, vars_read

Action = Literal["overwrite", "skip", "copy"]
Status = Literal["new", "identical", "differs"]

# Sections in dependency order, and the field naming an item in each.
SECTIONS: dict[str, str] = {
    "inputs": "name",
    "templates": "type",
    "channels": "name",
    "variables": "name",
    "rules": "name",
    "routes": "",          # keyed by template→channel
    "schedules": "name",
}
COPYABLE = {"inputs", "templates", "channels", "variables", "rules", "schedules"}

# What import writes for a field the item leaves out (mirrors config_io._import_*).
_DEFAULTS: dict[str, dict[str, Any]] = {
    "templates": {
        "icon": None, "category": None, "message_template": None, "runbook_url": None,
        "description": None, "locale": "en", "min_repeat_min": 30, "gate_variable": None, "gate_min": None,
        "quiet_hours": None, "enabled": True,
    },
    "rules": {
        "incident_enabled": False, "recovery_expr": None, "recovery_persist_n": 1,
        "resolved_template_type": None, "persist_n": 1, "eval_interval_sec": 10,
        "vars_extract": [], "inhibited_by": [], "trigger_summary": None,
        "trigger_logic_md": None, "enabled": True, "sort_order": 100,
    },
    "variables": {"input": None, "config": {}, "description": None, "enabled": True},
    "inputs": {"config": {}, "enabled": True},
    "channels": {"config": {}, "enabled": True, "rate_limit_per_min": 30, "quiet_hours": None},
    "routes": {"severity_min": "info", "enabled": True, "channel_overrides": None},
    "schedules": {"enabled": True},
}


def item_key(section: str, item: dict[str, Any]) -> str:
    if section == "routes":
        return f"{item.get('template')}→{item.get('channel')}"
    return str(item.get(SECTIONS[section]))


def _normalise(section: str, item: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    """The item as import would store it, on the keys export emits."""
    if section == "templates":
        item, _ = config_io.legacy_template_gate(item)
    if section == "channels" and item.get("kind") == "sms" and isinstance(item.get("config"), dict):
        item = {**item, "config": sms_config.upgrade_legacy(item["config"])}
    keys = set(item) | set(_DEFAULTS.get(section, {})) | set(current or {})
    out: dict[str, Any] = {}
    for k in keys:
        out[k] = item[k] if k in item else _DEFAULTS.get(section, {}).get(k, (current or {}).get(k))
    if "enabled" in out:
        out["enabled"] = config_io._coerce_bool(out["enabled"], True)
    # Secrets / URLs from a masked export: compare what import would actually
    # store (it keeps the live value for a placeholder or a redacted URL echo).
    for f in _SANITIZED.get(section, ()):
        if isinstance(out.get(f), dict):
            out[f], _ = config_io._sanitize_imported_config(out[f], (current or {}).get(f))
    return out


_SANITIZED = {"inputs": ("config",), "channels": ("config",), "routes": ("channel_overrides",)}


def _masked_equal(incoming: Any, current: Any) -> bool:
    """Equality that treats a masked-secret placeholder as "unchanged"
    (import keeps the live secret for those)."""
    if config_io._is_mask_placeholder(incoming):
        return True
    if isinstance(incoming, dict) and isinstance(current, dict):
        # Import replaces a config mapping whole: same keys, equal values.
        return set(incoming) == set(current) and all(
            _masked_equal(v, current[k]) for k, v in incoming.items())
    return bool(incoming == current)


def _diff(section: str, item: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    new = _normalise(section, item, current)
    changes = []
    for k in sorted(new):
        if k in ("name", "type", "template", "channel"):
            continue
        if not _masked_equal(new.get(k), current.get(k)):
            changes.append({"field": k, "current": current.get(k), "incoming": new.get(k)})
    return changes


# ── Export ─────────────────────────────────────────────────────────


async def export_selection(
    session: AsyncSession,
    *,
    sections: list[str] | None = None,
    category: str | None = None,
    names: list[str] | None = None,
    with_dependencies: bool = False,
    mask_secrets: bool = True,
) -> dict[str, Any]:
    """A pack holding only ``sections`` (all when None).

    - ``category`` keeps templates of that category (case-insensitive,
      ``__none__`` = uncategorized) and rules whose template is in it.
    - ``names`` keeps only items whose identifier is listed (template type,
      rule / variable / input / channel / schedule name).
    - Templates bring their routes along. ``with_dependencies`` closes the
      selection over everything it needs (docs/PACKS.md, "Exporting"): rules →
      templates, variables, inhibiting rules; variables → input, variables a
      formula reads; templates → gate variable; schedules → template; routes →
      channel. Repeated until nothing new is added.
    """
    full = await config_io.export_config(session, mask_secrets=mask_secrets)
    wanted = [s for s in SECTIONS if sections is None or s in sections]
    tmpl_category = {t["type"]: t.get("category") for t in full["templates"]}
    name_set = set(names) if names else None

    def in_category(template_type: str | None) -> bool:
        if category is None:
            return True
        c = tmpl_category.get(template_type or "")
        if category == "__none__":
            return not c
        return c is not None and c.lower() == category.lower()

    def keep(section: str, item: dict[str, Any]) -> bool:
        if name_set is not None and item_key(section, item) not in name_set:
            return False
        if section == "templates":
            return in_category(item["type"])
        if section == "rules":
            return in_category(item.get("template_type"))
        return True

    out: dict[str, Any] = {"version": full.get("version", "1.0")}
    for section in wanted:
        if section == "routes":
            continue
        out[section] = [i for i in full.get(section) or [] if keep(section, i)]

    if with_dependencies:
        _close_over_dependencies(out, full)

    if "templates" in out:
        types = {t["type"] for t in out["templates"]}
        out["routes"] = [r for r in full["routes"] if r["template"] in types]
        if with_dependencies:
            have_channels = {c["name"] for c in out.get("channels", [])}
            need_channels = {r["channel"] for r in out["routes"]} - have_channels
            out.setdefault("channels", []).extend(c for c in full["channels"] if c["name"] in need_channels)
    # Dependency order (as a full export), and drop empty sections so the file
    # only says what it carries.
    order = ["version", *SECTIONS]
    return {k: out[k] for k in order if k in out and (k == "version" or out[k])}


def _close_over_dependencies(out: dict[str, Any], full: dict[str, Any]) -> None:
    """Add to ``out`` (in place) every item its items need, transitively."""
    by_key = {sec: {item_key(sec, i): i for i in full.get(sec) or []} for sec in COPYABLE}

    def needs(section: str, item: dict[str, Any]) -> list[tuple[str, str]]:
        if section == "rules":
            deps = [("templates", item["template_type"])]
            if item.get("resolved_template_type"):
                deps.append(("templates", item["resolved_template_type"]))
            deps += [("rules", n) for n in item.get("inhibited_by") or []]
            deps += [("variables", v) for v in vars_read(
                item.get("vars_extract"), item.get("condition_expr"), item.get("recovery_expr"))]
            return deps
        if section == "variables":
            deps = [("inputs", item["input"])] if item.get("input") else []
            formula = (item.get("config") or {}).get("formula")
            return deps + [("variables", v) for v in expression_vars(formula)]
        if section == "templates" and item.get("gate_variable"):
            return [("variables", item["gate_variable"])]
        if section == "schedules":
            return [("templates", item["template_type"])]
        return []

    pending = [(sec, i) for sec in COPYABLE for i in out.get(sec) or []]
    have = {(sec, item_key(sec, i)) for sec, i in pending}
    while pending:
        section, item = pending.pop()
        for dep in needs(section, item):
            if dep in have or dep[1] not in by_key.get(dep[0], {}):
                continue  # already in, or not a configured item (a constant name, a typo)
            have.add(dep)
            found = by_key[dep[0]][dep[1]]
            out.setdefault(dep[0], []).append(found)
            pending.append((dep[0], found))


# ── Preview ────────────────────────────────────────────────────────


@dataclass
class PreviewItem:
    section: str
    key: str
    status: Status
    changes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Preview:
    ok: bool
    errors: list[str]
    warnings: list[str]
    items: list[PreviewItem]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "errors": self.errors, "warnings": self.warnings,
            "items": [vars(i) for i in self.items],
            "counts": {s: sum(1 for i in self.items if i.status == s) for s in ("new", "identical", "differs")},
        }


async def preview_import(session: AsyncSession, pack: dict[str, Any]) -> Preview:
    plan = await config_io.import_config(session, copy.deepcopy(pack), apply=False)
    current = await config_io.export_config(session, mask_secrets=False)
    index = {s: {item_key(s, i): i for i in current.get(s) or []} for s in SECTIONS}
    items: list[PreviewItem] = []
    for section in SECTIONS:
        for item in pack.get(section) or []:
            if not isinstance(item, dict):
                continue
            key = item_key(section, item)
            cur = index[section].get(key)
            if cur is None:
                items.append(PreviewItem(section, key, "new"))
                continue
            changes = _diff(section, item, cur)
            items.append(PreviewItem(section, key, "differs" if changes else "identical", changes))
    return Preview(ok=plan.ok, errors=plan.errors, warnings=plan.warnings, items=items)


# ── Apply ──────────────────────────────────────────────────────────


@dataclass
class MergeResult:
    plan: config_io.ImportPlan
    created: list[str] = field(default_factory=list)
    overwritten: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    copied: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        out = self.plan.summary()
        out.update(created=self.created, overwritten=self.overwritten,
                   skipped=self.skipped, copied=self.copied)
        return out


def _copy_name(base: str, taken: set[str], limit: int) -> str:
    for n in range(1, 1000):
        suffix = "_copy" if n == 1 else f"_copy{n}"
        candidate = base[: limit - len(suffix)] + suffix
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    raise ValueError(f"no free copy name for {base!r}")


_ID_LIMITS = {"templates": 64, "rules": 128, "variables": 128, "inputs": 64, "channels": 64, "schedules": 128}


async def build_merged_pack(
    session: AsyncSession,
    pack: dict[str, Any],
    decisions: dict[str, Action],
    default_existing: Action = "skip",
) -> tuple[dict[str, Any], MergeResult, Preview]:
    """The pack to import after applying the per-item decisions.

    ``decisions`` keys are ``"<section>:<key>"``. New items are imported
    (unless their decision is ``skip``), identical ones dropped; an existing item that differs follows
    its decision (default ``default_existing``). A copied template takes the
    pack's references to it (rules, routes, schedules) with it — they
    describe the incoming template. Copied variables / rules are renamed
    only; expressions that mention them are not rewritten.
    """
    preview = await preview_import(session, pack)
    status = {(i.section, i.key): i.status for i in preview.items}
    current = await config_io.export_config(session, mask_secrets=False)
    taken = {s: {item_key(s, i) for i in current.get(s) or []} | {item_key(s, i) for i in pack.get(s) or [] if isinstance(i, dict)}
             for s in SECTIONS}
    out: dict[str, Any] = {k: v for k, v in pack.items() if k not in SECTIONS}
    result = MergeResult(plan=config_io.ImportPlan())
    renamed_templates: dict[str, str] = {}

    for section in SECTIONS:
        kept = []
        for item in pack.get(section) or []:
            if not isinstance(item, dict):
                kept.append(item)
                continue
            if section == "routes" and item.get("template") in renamed_templates:
                # The route of a copied template describes the copy: always new.
                moved = dict(item, template=renamed_templates[item["template"]])
                kept.append(moved)
                result.created.append(f"routes:{item_key('routes', moved)}")
                continue
            key = item_key(section, item)
            label = f"{section}:{key}"
            st = status.get((section, key), "new")
            if st == "new":
                # New items are imported unless explicitly skipped (e.g. a
                # route to a channel the target doesn't have).
                if decisions.get(label) == "skip":
                    result.skipped.append(label)
                else:
                    kept.append(item)
                    result.created.append(label)
                continue
            if st == "identical":
                result.skipped.append(label)
                continue
            action = decisions.get(label, default_existing)
            if action == "copy" and section not in COPYABLE:
                action = default_existing if default_existing != "copy" else "skip"
            if action == "skip":
                result.skipped.append(label)
            elif action == "overwrite":
                kept.append(item)
                result.overwritten.append(label)
            else:
                new_item = dict(item)
                id_field = SECTIONS[section]
                new_name = _copy_name(key, taken[section], _ID_LIMITS[section])
                new_item[id_field] = new_name
                if section == "templates":
                    renamed_templates[key] = new_name
                kept.append(new_item)
                result.copied[label] = new_name
        out[section] = kept

    # A copied template carries the pack's own references to it.
    if renamed_templates:
        for r in out.get("rules") or []:
            for f in ("template_type", "resolved_template_type"):
                if isinstance(r, dict) and r.get(f) in renamed_templates:
                    r[f] = renamed_templates[r[f]]
        for s in out.get("schedules") or []:
            if isinstance(s, dict) and s.get("template_type") in renamed_templates:
                s["template_type"] = renamed_templates[s["template_type"]]
    return {k: v for k, v in out.items() if k not in SECTIONS or v}, result, preview


async def apply_import(
    session: AsyncSession,
    pack: dict[str, Any],
    decisions: dict[str, Action],
    default_existing: Action = "skip",
) -> MergeResult:
    """Apply the merged pack in one transaction (caller commits)."""
    merged, result, _ = await build_merged_pack(session, pack, decisions, default_existing)
    result.plan = await config_io.import_config(session, merged, apply=True)
    return result
