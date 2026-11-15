"""Packs: configuration with a header and parameters (docs/PACKS.md).

A pack is a config-export document plus a ``pack:`` header. This module
parses the header, checks and coerces the parameter values, substitutes
``${name}`` in the body, and lists the built-in catalog (``app/packs/``).
Validation, preview and the transactional install are ``config_merge`` /
``config_io`` — a rendered pack is an ordinary import document.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..utils.safe_yaml import BoundedYAMLError, load_bounded

CATALOG_DIR = Path(__file__).resolve().parent.parent / "packs"
BODY_SECTIONS = ("settings", "inputs", "templates", "channels", "variables", "rules", "routes", "schedules")
ParamType = Literal["string", "number", "integer", "boolean", "env", "channel"]
LocalText = str | dict[str, str]

_PLACEHOLDER = re.compile(r"\$\$\{|\$\{([^{}]*)\}")
_WHOLE = re.compile(r"^\$\{([a-z][a-z0-9_]*)\}$")
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_CHANNEL_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


class PackParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
    label: LocalText | None = None
    description: LocalText | None = None
    type: ParamType = "string"
    default: Any = None
    required: bool | None = None
    example: Any = None

    @property
    def is_required(self) -> bool:
        return self.required if self.required is not None else self.default is None


class PackHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    name: LocalText
    description: LocalText | None = None
    version: str = Field(default="1.0.0", max_length=32)
    tags: list[str] = Field(default_factory=list)
    parameters: list[PackParameter] = Field(default_factory=list)


class PackError(ValueError):
    """The pack or its parameters are invalid; ``errors`` lists every problem."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class Pack:
    header: PackHeader | None
    body: dict[str, Any]

    def counts(self) -> dict[str, int]:
        return {s: len(self.body[s]) for s in BODY_SECTIONS
                if s != "settings" and isinstance(self.body.get(s), list) and self.body[s]}

    def summary(self) -> dict[str, Any]:
        h = self.header
        return {
            "id": h.id if h else None,
            "name": h.name if h else None,
            "description": h.description if h else None,
            "version": h.version if h else None,
            "tags": h.tags if h else [],
            "parameters": [p.model_dump() | {"required": p.is_required} for p in h.parameters] if h else [],
            "counts": self.counts(),
        }


@dataclass
class Rendered:
    pack: Pack
    document: dict[str, Any]              # import document: body with values substituted
    params: dict[str, Any] = field(default_factory=dict)


# ── Parsing ─────────────────────────────────────────────────────────


def parse(text_or_data: str | dict[str, Any], *, max_depth: int = 64) -> Pack:
    """A pack (header optional) from YAML text or an already-loaded mapping."""
    if isinstance(text_or_data, str):
        try:
            data = load_bounded(text_or_data, max_depth)
        except BoundedYAMLError as e:
            raise PackError([str(e)]) from None
    else:
        data = text_or_data
    if not isinstance(data, dict):
        raise PackError(["Top-level must be a mapping"])
    data = dict(data)
    raw_header = data.pop("pack", None)
    header = None
    if raw_header is not None:
        try:
            header = PackHeader.model_validate(raw_header)
        except ValidationError as e:
            raise PackError([f"pack.{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]) from None
        names = [p.name for p in header.parameters]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise PackError([f"pack.parameters: duplicate name(s) {dupes}"])
    return Pack(header=header, body=data)


# ── Parameters ──────────────────────────────────────────────────────


def _coerce(p: PackParameter, value: Any) -> Any:
    """The value as the parameter's type, or ValueError with a short reason."""
    t = p.type
    if t == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0", "yes", "no"}:
            return value.strip().lower() in {"true", "1", "yes"}
        raise ValueError("expected true or false")
    if t in ("number", "integer"):
        if isinstance(value, bool):
            raise ValueError("expected a number")
        if not isinstance(value, int | float):
            text = str(value).strip()
            try:
                value = int(text) if re.fullmatch(r"[+-]?\d+", text) else float(text)
            except ValueError:
                raise ValueError("expected a number") from None
        if t == "integer":
            if float(value) != int(value):
                raise ValueError("expected a whole number")
            return int(value)
        return value
    text = "" if value is None else str(value).strip()
    if t == "env" and not _ENV_NAME.match(text):
        raise ValueError("expected an environment variable name like MY_TOKEN")
    if t == "channel" and not _CHANNEL_NAME.match(text):
        raise ValueError("expected a channel name")
    return text


def resolve_params(header: PackHeader | None, given: dict[str, Any] | None) -> dict[str, Any]:
    """Every declared parameter's value (given, else default), type-checked."""
    given = dict(given or {})
    declared = {p.name: p for p in (header.parameters if header else [])}
    errors = [f"unknown parameter: {name}" for name in sorted(set(given) - set(declared))]
    out: dict[str, Any] = {}
    for name, p in declared.items():
        raw = given.get(name)
        if raw is None or raw == "":
            raw = p.default
        if raw is None or raw == "":
            if p.is_required:
                errors.append(f"parameter {name}: required")
            out[name] = ""
            continue
        try:
            out[name] = _coerce(p, raw)
        except ValueError as e:
            errors.append(f"parameter {name}: {e}")
    if errors:
        raise PackError(errors)
    return out


def _substitute(value: Any, params: dict[str, Any], used: set[str], errors: list[str], path: str) -> Any:
    if isinstance(value, dict):
        return {k: _substitute(v, params, used, errors, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, params, used, errors, f"{path}[{i}]") for i, v in enumerate(value)]
    if not isinstance(value, str) or "${" not in value:
        return value
    whole = _WHOLE.match(value)
    if whole and whole.group(1) in params:
        used.add(whole.group(1))
        return params[whole.group(1)]

    def repl(m: re.Match[str]) -> str:
        if m.group(0) == "$${":
            return "${"
        name = m.group(1)
        if name not in params:
            errors.append(f"{path}: ${{{name}}} is not a declared parameter")
            return m.group(0)
        used.add(name)
        v = params[name]
        return ("true" if v else "false") if isinstance(v, bool) else str(v)

    return _PLACEHOLDER.sub(repl, value)


def render(pack: Pack, params: dict[str, Any] | None = None) -> Rendered:
    """The import document for ``pack`` with ``params``; PackError lists every problem."""
    values = resolve_params(pack.header, params)
    errors: list[str] = []
    used: set[str] = set()
    document = _substitute(copy.deepcopy(pack.body), values, used, errors, "pack")
    unused = sorted(set(values) - used)
    if unused:
        errors.append(f"pack.parameters: declared but never used: {unused}")
    if errors:
        raise PackError(errors)
    return Rendered(pack=pack, document=document, params=values)


# ── Catalog ─────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _catalog_cached(directory: str) -> dict[str, Pack]:
    packs: dict[str, Pack] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        pack = parse(path.read_text(encoding="utf-8"))
        if pack.header is None or pack.header.id != path.stem:
            raise PackError([f"{path.name}: header id must equal the file name"])
        packs[pack.header.id] = pack
    return packs


def catalog() -> dict[str, Pack]:
    """Built-in packs by id (``app/packs/*.yaml``), parsed once."""
    return _catalog_cached(str(CATALOG_DIR))


def catalog_text(pack_id: str) -> str | None:
    path = CATALOG_DIR / f"{pack_id}.yaml"
    return path.read_text(encoding="utf-8") if pack_id in catalog() else None
