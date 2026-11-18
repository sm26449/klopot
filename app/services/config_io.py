"""Configuration export / import — full YAML round-trip.

Export: dump every config table (inputs, variables, templates,
channels, template_channels routes, schedules) to a YAML-friendly
dict. Identifiers across tables use NAMES (string), never the
auto-generated ``id`` columns — same DB on a different machine has
different ids but same names.

Import: parse the dict back, run validation, then upsert in
dependency order inside one transaction. Dry-run mode returns the
planned changes without committing.

What's NOT exported:
- ``api_keys`` — secrets must never round-trip through YAML
- ``audit_log`` — historical, not config
- ``notifications_log`` — historical
- ``rule_state`` / ``throttle_state`` — runtime
- ``user_prefs`` — per-user, separate concern
- ``settings`` — exported (it's config)

Secret handling:
- Channel/input ``config`` JSON may contain ``*_ref`` fields (env
  var names). Export emits them as-is. Import preserves them.
- Plaintext secrets (e.g., ``bot_token`` literal) ARE exported. The
  CLI ``--mask-secrets`` flag rewrites them as ``env:UNKNOWN`` on
  the way out so a sharing-friendly YAML never leaks. Production
  deployments should always use ``_ref`` so the question never
  arises.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels import sms_config
from ..core.eval import ExpressionError as _ExpressionError
from ..core.eval import validate_expression as _validate_expression
from ..core.incidents import lifecycle_config
from ..core.parametric import check_expressions, normalize_for_each
from ..core.rule_state_ops import reset_streak_on_reconfig
from ..db.models import (
    Channel,
    ChannelKind,
    Input,
    InputKind,
    Rule,
    Schedule,
    Settings,
    Severity,
    Template,
    TemplateChannel,
    Variable,
    VariableSource,
)
from ..secrets_registry import is_url_display_key
from ..utils.icons import validate_icon
from ..utils.redact import is_redacted_url_display, safe_url_display
from .categories import canonical_category
from .config_import_schema import SETTINGS_FIELDS, validate_pack

logger = logging.getLogger(__name__)

# Strings that mean False — so an imported ``enabled: "false"`` disables the
# row instead of enabling it, as plain ``bool("false")`` wrongly did (F28).
_FALSE_STRINGS = frozenset({"false", "0", "no", "off", "", "null", "none"})


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce an imported ``enabled`` value to a bool, honouring string
    forms like ``"false"`` (audit F28). Omitted/None → ``default``."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in _FALSE_STRINGS
    return bool(value)


# Sections to export, in dependency order. Listed as keys in the
# emitted YAML.
SECTIONS = (
    "settings",
    "inputs",
    "templates",
    "channels",
    "variables",   # depends on inputs (by name)
    "rules",       # depends on templates (by type, soft FK)
    "routes",      # depends on templates + channels (by name)
    "schedules",   # depends on templates (by type)
)


# ── Export ────────────────────────────────────────────────────────


async def export_config(
    session: AsyncSession,
    *,
    mask_secrets: bool = False,
) -> dict[str, Any]:
    """Read all config tables and emit a portable dict ready for
    YAML serialization."""
    out: dict[str, Any] = {"version": "1.0"}

    out["settings"] = await _export_settings(session)
    out["inputs"] = await _export_inputs(session, mask_secrets=mask_secrets)
    out["templates"] = await _export_templates(session)
    out["channels"] = await _export_channels(session, mask_secrets=mask_secrets)
    out["variables"] = await _export_variables(session)
    out["rules"] = await _export_rules(session)
    out["routes"] = await _export_routes(session, mask_secrets=mask_secrets)
    out["schedules"] = await _export_schedules(session)
    return out


async def _export_settings(session: AsyncSession) -> dict[str, Any]:
    row = (
        await session.execute(select(Settings).where(Settings.id == 1))
    ).scalar_one_or_none()
    if row is None:
        return {}
    return {
        "log_retention_days": row.log_retention_days,
        "audit_retention_days": row.audit_retention_days,
        "idempotency_window_sec": row.idempotency_window_sec,
        "default_eval_interval_sec": row.default_eval_interval_sec,
        "circuit_breaker_threshold": row.circuit_breaker_threshold,
        "circuit_breaker_open_sec": row.circuit_breaker_open_sec,
        "bridge_max_queue": row.bridge_max_queue,
        "timezone": row.timezone,
    }


async def _export_inputs(session: AsyncSession, *, mask_secrets: bool) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Input).order_by(Input.name))).scalars().all()
    return [
        {
            "name": r.name,
            "kind": r.kind.value,
            "config": _maybe_mask(dict(r.config or {}), mask_secrets),
            "enabled": r.enabled,
        }
        for r in rows
    ]


async def _export_templates(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Template).order_by(Template.type))).scalars().all()
    return [
        {
            "type": r.type,
            "severity": r.severity.value,
            "icon": r.icon,
            "category": r.category,
            "title_template": r.title_template,
            "message_template": r.message_template,
            "runbook_url": r.runbook_url,
            "description": r.description,
            "locale": r.locale,
            "min_repeat_min": r.min_repeat_min,
            "gate_variable": r.gate_variable,
            "gate_min": r.gate_min,
            "quiet_hours": r.quiet_hours,
            "enabled": r.enabled,
        }
        for r in rows
    ]


async def _export_channels(session: AsyncSession, *, mask_secrets: bool) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Channel).order_by(Channel.name))).scalars().all()
    return [
        {
            "name": r.name,
            "kind": r.kind.value,
            "config": _maybe_mask(dict(r.config or {}), mask_secrets),
            "enabled": r.enabled,
            "rate_limit_per_min": r.rate_limit_per_min,
            "quiet_hours": r.quiet_hours,
        }
        for r in rows
    ]


async def _export_variables(session: AsyncSession) -> list[dict[str, Any]]:
    """Variables reference inputs by name (resolved from input_id)."""
    rows = (
        await session.execute(
            select(Variable, Input.name)
            .outerjoin(Input, Input.id == Variable.input_id)
            .order_by(Variable.name)
        )
    ).all()
    out = []
    for v, input_name in rows:
        out.append({
            "name": v.name,
            "source": v.source.value,
            "input": input_name,  # may be None
            "config": dict(v.config or {}),
            "description": v.description,
            "enabled": v.enabled,
        })
    return out


async def _export_rules(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Rule).order_by(Rule.name))).scalars().all()
    return [
        {
            "name": r.name,
            "template_type": r.template_type,
            "condition_expr": r.condition_expr,
            "incident_enabled": r.incident_enabled,
            "recovery_expr": r.recovery_expr,
            "recovery_persist_n": r.recovery_persist_n,
            "resolved_template_type": r.resolved_template_type,
            "persist_n": r.persist_n,
            "eval_interval_sec": r.eval_interval_sec,
            "vars_extract": list(r.vars_extract or []),
            "inhibited_by": list(r.inhibited_by or []),
            "trigger_summary": r.trigger_summary,
            "trigger_logic_md": r.trigger_logic_md,
            "enabled": r.enabled,
            "sort_order": r.sort_order,
            **({"for_each": r.for_each} if r.for_each else {}),
        }
        for r in rows
    ]


async def _export_routes(session: AsyncSession, *, mask_secrets: bool = False) -> list[dict[str, Any]]:
    """template_channels rows expressed as (template_type, channel_name).

    Route ``channel_overrides`` are a partial channel config and can carry
    secrets, so a masked export redacts them too (audit F02) — previously
    they were emitted literally even with ``mask_secrets=true``."""
    rows = (
        await session.execute(
            select(Template.type, Channel.name, TemplateChannel.severity_min,
                   TemplateChannel.enabled, TemplateChannel.channel_overrides)
            .join(TemplateChannel, TemplateChannel.template_id == Template.id)
            .join(Channel, Channel.id == TemplateChannel.channel_id)
            .order_by(Template.type, Channel.name)
        )
    ).all()
    return [
        {
            "template": ttype,
            "channel": cname,
            "severity_min": sev_min.value,
            "enabled": en,
            "channel_overrides": _maybe_mask(dict(overrides), mask_secrets) if overrides else overrides,
        }
        for ttype, cname, sev_min, en, overrides in rows
    ]


async def _export_schedules(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Schedule).order_by(Schedule.name))).scalars().all()
    return [
        {
            "name": r.name,
            "cron_expr": r.cron_expr,
            "template_type": r.template_type,
            "context": dict(r.context or {}),
            "enabled": r.enabled,
        }
        for r in rows
    ]


_SECRET_HINTS = {"token", "password", "secret", "api_key", "key", "auth_value"}
# Sensitive keys that appear NESTED (webhook ``headers`` map) and don't
# match the substring hints above (audit A08: masked export still leaked
# ``headers.Authorization``).
_SECRET_HEADER_KEYS = {
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "apikey", "x-auth-token", "x-token", "x-auth",
}


# Prefix emitted by _mask_recursive for a masked-out secret. A masked
# export carries these in place of real values; importing them back must
# NOT clobber a live credential (audit A14).
_MASK_PLACEHOLDER_PREFIX = "env:UNKNOWN_"


def _is_mask_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_MASK_PLACEHOLDER_PREFIX)


def _sanitize_imported_config(
    new_config: Any, existing_config: Any,
) -> tuple[Any, list[str]]:
    """Strip masked placeholders from an imported config (audit A14).

    For every value equal to ``env:UNKNOWN_*`` (produced by a masked
    export), keep the existing real value at the same path when updating,
    or drop the key entirely when there is none — never write the
    placeholder over a valid credential. Recurses into nested dicts
    (e.g. webhook ``headers``). Returns ``(clean_config, dropped_paths)``.
    """
    dropped: list[str] = []

    def _walk(new: Any, existing: Any, prefix: str) -> Any:
        if not isinstance(new, dict):
            return new
        ex = existing if isinstance(existing, dict) else {}
        out: dict[str, Any] = {}
        for k, v in new.items():
            path = f"{prefix}{k}"
            if _is_mask_placeholder(v):
                dropped.append(path)
                if k in ex and not _is_mask_placeholder(ex[k]):
                    out[k] = ex[k]  # preserve the live value
                # else: omit — no real value to keep
            elif is_url_display_key(k) and isinstance(v, str):
                # A redacted URL display must never be written over a real URL
                # (audit A-06): keep the live value on an echo, drop it on a
                # fresh import with nothing to restore, else take the new URL.
                ex_v = ex.get(k)
                if isinstance(ex_v, str) and v == safe_url_display(ex_v):
                    out[k] = ex_v
                elif is_redacted_url_display(v):
                    dropped.append(path)
                else:
                    out[k] = v
            elif isinstance(v, dict):
                out[k] = _walk(v, ex.get(k), f"{path}.")
            else:
                out[k] = v
        return out

    return _walk(new_config or {}, existing_config or {}, ""), dropped


def _is_secret_hint(key: Any) -> bool:
    kl = str(key).lower()
    if kl.endswith("_ref"):
        return False
    return kl in _SECRET_HEADER_KEYS or any(h in kl for h in _SECRET_HINTS)


def _mask_recursive(value: Any) -> Any:
    """Rewrite literal-looking secrets to ``env:UNKNOWN_<KEY>`` at any
    depth (top-level config AND nested dicts/lists like webhook headers)."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).endswith("_ref"):
                out[k] = v  # already a reference
            elif is_url_display_key(k) and isinstance(v, str) and v:
                out[k] = safe_url_display(v)  # host-only display (audit A-06)
            elif _is_secret_hint(k) and isinstance(v, str) and v:
                out[k] = f"env:UNKNOWN_{str(k).upper()}"
            elif isinstance(v, dict | list):
                out[k] = _mask_recursive(v)
            else:
                out[k] = v
        return out
    if isinstance(value, list):
        return [_mask_recursive(x) for x in value]
    return value


def _maybe_mask(cfg: dict[str, Any], mask: bool) -> dict[str, Any]:
    """If ``mask=True``, rewrite any literal-looking secret to
    ``"env:UNKNOWN_<KEY>"`` so the YAML is shareable without leaking —
    recursively, so nested webhook headers are covered too (audit A08)."""
    if not mask:
        return cfg
    return _mask_recursive(cfg)


# ── Import ────────────────────────────────────────────────────────


@dataclass
class ImportPlan:
    """What an import would do, returned by validate / dry-run."""

    creates: dict[str, list[str]] = field(default_factory=dict)  # section → names
    updates: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> dict[str, Any]:
        total_creates = sum(len(v) for v in self.creates.values())
        total_updates = sum(len(v) for v in self.updates.values())
        return {
            "ok": self.ok,
            "creates_total": total_creates,
            "updates_total": total_updates,
            "creates": self.creates,
            "updates": self.updates,
            "errors": self.errors,
            "warnings": self.warnings,
        }


async def import_config(
    session: AsyncSession,
    config: dict[str, Any],
    *,
    apply: bool = False,
) -> ImportPlan:
    """Validate and (optionally) apply a config dict.

    On ``apply=False`` (default): runs all validations and returns
    the plan; never writes to the DB.

    On ``apply=True``: same plus writes everything in this session's
    transaction. Caller must commit. Any error during apply rolls
    back the whole import — partial state never reaches the DB.
    """
    plan = ImportPlan()

    # Pre-flight validation
    if not isinstance(config, dict):
        plan.errors.append("config must be a YAML mapping at the top level")
        return plan

    # Schema validation (audit A09): enforce structure, enums, required
    # fields, settings whitelist, sizes and in-pack duplicates BEFORE any
    # DB access. Catches what used to surface as a 500 (bad enum, missing
    # title, ``inputs: 5``, ``settings: {id: 2}``) as localized errors.
    schema_errors = validate_pack(config)
    if schema_errors:
        plan.errors.extend(schema_errors)
        return plan

    # Cross-reference checks (do BEFORE writing anything)
    input_names = {i["name"] for i in config.get("inputs") or [] if isinstance(i, dict) and "name" in i}
    template_types = {t["type"] for t in config.get("templates") or [] if isinstance(t, dict) and "type" in t}
    channel_names = {c["name"] for c in config.get("channels") or [] if isinstance(c, dict) and "name" in c}

    # Existing names in DB (still referenceable even if not in this YAML — partial imports)
    db_input_names = {r[0] for r in (await session.execute(select(Input.name))).all()}
    db_template_types = {r[0] for r in (await session.execute(select(Template.type))).all()}
    db_channel_names = {r[0] for r in (await session.execute(select(Channel.name))).all()}

    available_inputs = input_names | db_input_names
    available_templates = template_types | db_template_types
    available_channels = channel_names | db_channel_names

    # Variables → input must exist, and the config must compile into a runtime
    # mapping (audit V09). An mqtt topic given as a JSON object is unhashable and
    # makes the post-import hot reload raise — which import silently swallows,
    # leaving a persisted config that breaks every future reload. Catch it as a
    # localized pre-flight error so the whole import is rejected before commit.
    from ..core.manager import VariableConfigError, dry_compile_variable

    for v in (config.get("variables") or []):
        if not isinstance(v, dict):
            continue
        if v.get("input") and v["input"] not in available_inputs:
            plan.errors.append(
                f"variable {v.get('name')!r} references unknown input {v['input']!r}"
            )
        try:
            dry_compile_variable(
                VariableSource(v["source"]), v.get("config") or {}, v.get("name")
            )
        except VariableConfigError as e:
            plan.errors.append(
                f"variable {v.get('name')!r} has an invalid config: {e}"
            )

    # Rules → template must exist (warning, not error — rule auto-disables in engine)
    for r in (config.get("rules") or []):
        if not isinstance(r, dict):
            continue
        if r.get("template_type") and r["template_type"] not in available_templates:
            plan.warnings.append(
                f"rule {r.get('name')!r} references unknown template_type "
                f"{r['template_type']!r} (rule will fire but won't dispatch)"
            )
        # Reject an imported condition outside the language contract (audit
        # A-01) — the same validator the REST create/update uses, as every
        # instance of a parametric rule sees it (ADR-0005).
        try:
            for_each = normalize_for_each(r.get("for_each"))
        except ValueError as e:
            plan.errors.append(f"rule {r.get('name')!r}: {e}")
            continue
        expr = r.get("condition_expr")
        if expr:
            try:
                check_expressions(for_each, _validate_expression, expr)
            except _ExpressionError as e:
                plan.errors.append(f"rule {r.get('name')!r}: invalid expression — {e}")
        if r.get("recovery_expr"):
            try:
                check_expressions(for_each, _validate_expression, r["recovery_expr"])
            except _ExpressionError as e:
                plan.errors.append(f"rule {r.get('name')!r}: invalid recovery expression — {e}")

    # Routes → both ends must exist
    for rt in (config.get("routes") or []):
        if not isinstance(rt, dict):
            continue
        if rt.get("template") and rt["template"] not in available_templates:
            plan.errors.append(
                f"route references unknown template {rt['template']!r}"
            )
        if rt.get("channel") and rt["channel"] not in available_channels:
            plan.errors.append(
                f"route references unknown channel {rt['channel']!r}"
            )

    # Schedules → template must exist
    for s in (config.get("schedules") or []):
        if not isinstance(s, dict):
            continue
        if s.get("template_type") and s["template_type"] not in available_templates:
            plan.errors.append(
                f"schedule {s.get('name')!r} references unknown template_type "
                f"{s['template_type']!r}"
            )
        # Validate cron at parse time
        try:
            from croniter import croniter
            if s.get("cron_expr"):
                croniter(s["cron_expr"])
        except Exception as e:
            plan.errors.append(f"schedule {s.get('name')!r}: invalid cron — {e}")

    # Entity admission caps (audit D-02/A-14): refuse an import that would push a
    # capped entity's TOTAL past its configured limit. Counts net-new names only,
    # so re-importing an existing (possibly already over-cap) config whose rows
    # are all updates still applies; only genuinely new rows are gated.
    from ..config import get_settings as _get_settings
    _s = _get_settings()
    pack_rule_names = {
        r["name"] for r in (config.get("rules") or [])
        if isinstance(r, dict) and "name" in r
    }
    db_rule_names = {r[0] for r in (await session.execute(select(Rule.name))).all()}
    for _entity, _cap, _pack_names, _db_names in (
        ("rules", _s.max_rules, pack_rule_names, db_rule_names),
        ("inputs", _s.max_inputs, input_names, db_input_names),
        ("channels", _s.max_channels, channel_names, db_channel_names),
    ):
        if _cap <= 0:
            continue
        _new = len(_pack_names - _db_names)
        _total = len(_db_names) + _new
        # Only genuinely new rows are gated; a pure-update import of an already
        # over-cap config still applies (mirrors the REST create semantics).
        if _new > 0 and _total > _cap:
            plan.errors.append(
                f"{_entity}: import would reach {_total}, over the limit of {_cap} "
                f"({len(_db_names)} exist, {_new} new) — raise the configured limit"
            )

    if not plan.ok:
        return plan

    # ── Apply (or dry-run) — same logic, transactional ───────────
    # Flush after each stage that creates parents so a later stage's
    # lookup SELECT sees the just-inserted rows (audit F01). Production
    # uses autoflush=False, so without these explicit flushes the
    # variable→input and route→template/channel lookups miss pending
    # parents and silently drop the binding/route.
    if config.get("settings"):
        await _import_settings(session, config["settings"], plan)
    await _import_inputs(session, config.get("inputs") or [], plan)
    await session.flush()
    await _import_templates(session, config.get("templates") or [], plan)
    await _import_channels(session, config.get("channels") or [], plan)
    await session.flush()
    await _import_variables(session, config.get("variables") or [], plan)
    await _import_rules(session, config.get("rules") or [], plan)
    # The history the imported rules and formulas need (ADR-0004, RC-03).
    from .history_budget import history_budget_problem
    problem = await history_budget_problem(session)
    if problem:
        plan.errors.append(problem)
    await _import_routes(session, config.get("routes") or [], plan)
    await _import_schedules(session, config.get("schedules") or [], plan)

    if not apply:
        # Roll back any pending changes from the dry-run pass
        await session.rollback()

    return plan


async def _import_settings(session: AsyncSession, data: dict[str, Any], plan: ImportPlan) -> None:
    row = (await session.execute(select(Settings).where(Settings.id == 1))).scalar_one_or_none()
    if row is None:
        row = Settings(id=1)
        session.add(row)
        plan.creates.setdefault("settings", []).append("singleton")
    else:
        plan.updates.setdefault("settings", []).append("singleton")
    # Whitelisted columns only (audit A09). The schema layer already
    # rejects unknown keys, but writing against an explicit allowlist keeps
    # the write path safe even if called directly, never touching ``id`` or
    # ORM internals that ``hasattr`` would otherwise accept.
    # An explicit null for a non-nullable setting (e.g. timezone) must be a
    # plan error, not a NOT NULL violation that raises at commit (F28).
    nonnullable = {c.name for c in Settings.__table__.columns if not c.nullable}
    for k, v in data.items():
        if k not in SETTINGS_FIELDS:
            continue
        if v is None and k in nonnullable:
            plan.errors.append(f"settings.{k}: must not be null")
            continue
        setattr(row, k, v)
    # Infrastructure settings are not fully restorable from a config pack
    # (audit A14): the service reads several operational values from the
    # environment at startup, so writing the Settings row here does not
    # change the running configuration until a restart with matching env.
    if data:
        plan.warnings.append(
            "settings: written to the DB Settings row, but operational "
            "values the service reads from the environment at startup are "
            "NOT changed by this import — update env + restart for those"
        )


async def _import_inputs(session: AsyncSession, items: list[dict[str, Any]], plan: ImportPlan) -> None:
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            plan.errors.append(f"invalid input row: {item}")
            continue
        from ..inputs import REGISTRY

        if item.get("kind") not in REGISTRY:
            # The REST API refuses these (audit F29); an import must too, or it
            # stores an input that never runs (Copilot hygiene #5).
            plan.errors.append(f"input {item['name']!r}: kind {item.get('kind')!r} is not supported "
                               f"(no adapter); supported: {sorted(REGISTRY)}")
            continue
        existing = (
            await session.execute(select(Input).where(Input.name == item["name"]))
        ).scalar_one_or_none()
        config, dropped = _sanitize_imported_config(
            item.get("config"), existing.config if existing else None,
        )
        if dropped:
            plan.warnings.append(
                f"input {item['name']!r}: ignored masked placeholder(s) "
                f"{dropped} from a masked export — live secret kept"
            )
        # The same rules as the API (the adapter's validate_config): e.g. an
        # inbound input that requires a token must have one (a masked export
        # carries none for a new input), and a token that is set or changed
        # must be long enough — restoring an export of an input as it is never
        # fails on its old token.
        before = (existing.config or {}) if existing and existing.kind.value == item["kind"] else None
        try:
            REGISTRY[item["kind"]].validate_config(config or {}, before=before)
        except ValueError as e:
            plan.errors.append(f"input {item['name']!r}: {e}")
            continue
        if existing is None:
            session.add(Input(
                name=item["name"],
                kind=InputKind(item["kind"]),
                config=config,
                enabled=_coerce_bool(item.get("enabled"), True),
            ))
            plan.creates.setdefault("inputs", []).append(item["name"])
        else:
            existing.kind = InputKind(item["kind"])
            existing.config = config
            existing.enabled = _coerce_bool(item.get("enabled"), True)
            plan.updates.setdefault("inputs", []).append(item["name"])


def legacy_template_gate(item: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Map a pre-0030 ``require_pv_kw`` onto ``gate_min`` / ``gate_variable``.

    Returns the item to import and a warning when the old key was used. The
    variable comes from ALERTD_PV_POWER_VAR (what the old key compared
    against) unless the item names one.
    """
    if "require_pv_kw" not in item:
        return item, None
    item = dict(item)
    legacy = item.pop("require_pv_kw")
    if legacy is None:
        return item, None
    item.setdefault("gate_min", legacy)
    if not item.get("gate_variable"):
        from ..config import get_settings

        item["gate_variable"] = get_settings().pv_power_var or None
    note = "" if item["gate_variable"] else " — set gate_variable: without one the gate has no effect"
    return item, f"template {item.get('type')}: require_pv_kw is deprecated, imported as gate_min{note}"


async def _import_templates(session: AsyncSession, items: list[dict[str, Any]], plan: ImportPlan) -> None:
    for item in items:
        if not isinstance(item, dict) or "type" not in item:
            plan.errors.append(f"invalid template row: {item}")
            continue
        item, legacy_note = legacy_template_gate(item)
        if legacy_note:
            plan.warnings.append(legacy_note)
        existing = (
            await session.execute(select(Template).where(Template.type == item["type"]))
        ).scalar_one_or_none()
        attrs = {
            "severity": Severity(item["severity"]),
            "icon": validate_icon(item.get("icon")),
            "category": await canonical_category(session, item.get("category"), exclude_type=item["type"]),
            "title_template": item["title_template"],
            "message_template": item.get("message_template"),
            "runbook_url": item.get("runbook_url"),
            "description": item.get("description"),
            "locale": item.get("locale", "en"),
            "min_repeat_min": item.get("min_repeat_min", 30),
            "gate_variable": item.get("gate_variable"),
            "gate_min": item.get("gate_min"),
            "quiet_hours": item.get("quiet_hours"),
            "enabled": _coerce_bool(item.get("enabled"), True),
        }
        if existing is None:
            session.add(Template(type=item["type"], **attrs))
            plan.creates.setdefault("templates", []).append(item["type"])
        else:
            for k, v in attrs.items():
                setattr(existing, k, v)
            plan.updates.setdefault("templates", []).append(item["type"])


async def _import_channels(session: AsyncSession, items: list[dict[str, Any]], plan: ImportPlan) -> None:
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            plan.errors.append(f"invalid channel row: {item}")
            continue
        existing = (
            await session.execute(select(Channel).where(Channel.name == item["name"]))
        ).scalar_one_or_none()
        config, dropped = _sanitize_imported_config(
            item.get("config"), existing.config if existing else None,
        )
        if dropped:
            plan.warnings.append(
                f"channel {item['name']!r}: ignored masked placeholder(s) "
                f"{dropped} from a masked export — live secret kept"
            )
        if item["kind"] == "sms" and sms_config.is_legacy(config or {}):
            config = sms_config.upgrade_legacy(config)
            plan.warnings.append(
                f"channel {item['name']!r}: pre-0031 SMS config (gateway_url) "
                f"converted to provider 'http' — same request as before"
            )
        attrs = {
            "kind": ChannelKind(item["kind"]),
            "config": config,
            "enabled": _coerce_bool(item.get("enabled"), True),
            "rate_limit_per_min": item.get("rate_limit_per_min", 30),
            "quiet_hours": item.get("quiet_hours"),
        }
        if existing is None:
            session.add(Channel(name=item["name"], **attrs))
            plan.creates.setdefault("channels", []).append(item["name"])
        else:
            for k, v in attrs.items():
                setattr(existing, k, v)
            plan.updates.setdefault("channels", []).append(item["name"])


async def _import_variables(session: AsyncSession, items: list[dict[str, Any]], plan: ImportPlan) -> None:
    # Build name → id map fresh (might include just-imported inputs)
    inputs_map = {
        n: i for i, n in (
            await session.execute(select(Input.id, Input.name))
        ).all()
    }
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            plan.errors.append(f"invalid variable row: {item}")
            continue
        input_name = item.get("input")
        input_id = inputs_map.get(input_name) if input_name else None
        if input_name and input_id is None:
            # Declared an input binding that doesn't resolve — fail the
            # import rather than silently store input_id=NULL (audit F01),
            # which would drop the variable's input isolation.
            plan.errors.append(
                f"variable {item['name']!r}: input {input_name!r} did not resolve"
            )
            continue
        existing = (
            await session.execute(select(Variable).where(Variable.name == item["name"]))
        ).scalar_one_or_none()
        attrs = {
            "source": VariableSource(item["source"]),
            "input_id": input_id,
            "config": item.get("config") or {},
            "description": item.get("description"),
            "enabled": _coerce_bool(item.get("enabled"), True),
        }
        if existing is None:
            session.add(Variable(name=item["name"], **attrs))
            plan.creates.setdefault("variables", []).append(item["name"])
        else:
            for k, v in attrs.items():
                setattr(existing, k, v)
            plan.updates.setdefault("variables", []).append(item["name"])


async def _import_rules(session: AsyncSession, items: list[dict[str, Any]], plan: ImportPlan) -> None:
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            plan.errors.append(f"invalid rule row: {item}")
            continue
        existing = (
            await session.execute(select(Rule).where(Rule.name == item["name"]).with_for_update())
        ).scalar_one_or_none()
        attrs = {
            "template_type": item["template_type"],
            "condition_expr": item["condition_expr"],
            "incident_enabled": item.get("incident_enabled", False),
            "recovery_expr": item.get("recovery_expr"),
            "recovery_persist_n": item.get("recovery_persist_n", 1),
            "resolved_template_type": item.get("resolved_template_type"),
            "persist_n": item.get("persist_n", 1),
            "eval_interval_sec": item.get("eval_interval_sec", 10),
            "vars_extract": item.get("vars_extract") or [],
            "inhibited_by": item.get("inhibited_by") or [],
            "trigger_summary": item.get("trigger_summary"),
            "trigger_logic_md": item.get("trigger_logic_md"),
            "enabled": _coerce_bool(item.get("enabled"), True),
            "sort_order": item.get("sort_order", 100),
            "for_each": normalize_for_each(item.get("for_each")),
        }
        if existing is None:
            session.add(Rule(name=item["name"], **attrs))
            plan.creates.setdefault("rules", []).append(item["name"])
        else:
            prev_expr = existing.condition_expr
            prev_lifecycle = lifecycle_config(existing)
            prev_for_each = existing.for_each
            for k, v in attrs.items():
                setattr(existing, k, v)
            # Same durable streak reset as the REST PATCH path: an import that
            # rewrites a rule's expression must not leave an old-expression
            # streak recoverable on restart (audit B-06).
            await reset_streak_on_reconfig(
                session, existing, previous_condition_expr=prev_expr, previous_lifecycle=prev_lifecycle,
                previous_for_each=prev_for_each,
            )
            plan.updates.setdefault("rules", []).append(item["name"])


async def _import_routes(session: AsyncSession, items: list[dict[str, Any]], plan: ImportPlan) -> None:
    """Routes addressed by (template_type, channel_name) → resolve to ids."""
    # Refresh lookups (might include just-imported items)
    tmpl_map = {
        t: i for i, t in (await session.execute(select(Template.id, Template.type))).all()
    }
    ch_map = {
        n: i for i, n in (await session.execute(select(Channel.id, Channel.name))).all()
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        tt = item.get("template")
        cn = item.get("channel")
        tid = tmpl_map.get(tt) if isinstance(tt, str) else None
        cid = ch_map.get(cn) if isinstance(cn, str) else None
        if tid is None or cid is None:
            # With the dependency flushes above, a declared template/channel
            # resolves here; a miss means a route references something that
            # didn't materialize — fail the import instead of silently
            # dropping the route (audit F01).
            plan.errors.append(
                f"route {tt!r}→{cn!r}: "
                f"{'template' if tid is None else 'channel'} did not resolve"
            )
            continue
        existing = (
            await session.execute(
                select(TemplateChannel).where(
                    TemplateChannel.template_id == tid,
                    TemplateChannel.channel_id == cid,
                )
            )
        ).scalar_one_or_none()
        # Strip masked placeholders from the route overrides just as inputs and
        # channels do (audit V02): a masked export carries secrets as
        # ``env:UNKNOWN_*``; re-importing must keep the live secret, never
        # clobber it with the placeholder.
        new_overrides = item.get("channel_overrides")
        if new_overrides is None:
            clean_overrides: dict[str, Any] | None = None
        else:
            clean_overrides, dropped = _sanitize_imported_config(
                new_overrides,
                existing.channel_overrides if existing is not None else None,
            )
            if dropped:
                plan.warnings.append(
                    f"route {tt!r}→{cn!r}: ignored masked placeholder(s) "
                    f"{dropped} from a masked export — live secret kept"
                )
        attrs = {
            "severity_min": Severity(item.get("severity_min", "info")),
            "enabled": _coerce_bool(item.get("enabled"), True),
            "channel_overrides": clean_overrides,
        }
        key = f"{tt}→{cn}"
        if existing is None:
            session.add(TemplateChannel(template_id=tid, channel_id=cid, **attrs))
            plan.creates.setdefault("routes", []).append(key)
        else:
            for k, v in attrs.items():
                setattr(existing, k, v)
            plan.updates.setdefault("routes", []).append(key)


async def _import_schedules(session: AsyncSession, items: list[dict[str, Any]], plan: ImportPlan) -> None:
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            plan.errors.append(f"invalid schedule row: {item}")
            continue
        existing = (
            await session.execute(select(Schedule).where(Schedule.name == item["name"]))
        ).scalar_one_or_none()
        attrs = {
            "cron_expr": item["cron_expr"],
            "template_type": item["template_type"],
            "context": item.get("context") or {},
            "enabled": _coerce_bool(item.get("enabled"), True),
            # Audit A10: reset so the schedule service recomputes the next
            # fire from the (possibly changed) cron, instead of keeping the
            # stale time. The import endpoint triggers recompute_pending().
            "next_fire_at": None,
        }
        if existing is None:
            session.add(Schedule(name=item["name"], **attrs))
            plan.creates.setdefault("schedules", []).append(item["name"])
        else:
            for k, v in attrs.items():
                setattr(existing, k, v)
            plan.updates.setdefault("schedules", []).append(item["name"])
