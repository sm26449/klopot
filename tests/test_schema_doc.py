"""docs/SCHEMA.md must match the models (drift check, like OpenAPI drift).

For every ``CREATE TABLE`` block in the doc whose table exists in the
models: each documented column exists, each model column is documented,
``VARCHAR(n)`` lengths match ``String(n)``, and ``ENUM(...)`` values match the
model enum. Tables described only in prose (incidents, Telegram action
tables) are not checked here. Fix the doc when this fails.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import Enum, String

import app.db.models  # noqa: F401  — registers every table on the metadata
from app.db.base import Base

DOC = Path(__file__).resolve().parents[1] / "docs" / "SCHEMA.md"
_SKIP = {"INDEX", "UNIQUE", "PRIMARY", "FOREIGN", "KEY", "CONSTRAINT", "ON", "NOT", "DEFAULT"}
_COLUMN = re.compile(
    r"^\s{4}(?P<name>\w+)\s+(?:VARCHAR\((?P<len>\d+)\)|ENUM\((?P<enum>.*?)\)|[A-Z]+)",
    re.M | re.S,
)


def _blocks() -> list[tuple[str, str]]:
    text = DOC.read_text()
    return re.findall(r"```sql\s*CREATE TABLE (\w+) \((.*?)\n\);", text, re.S)


def _documented(body: str) -> dict[str, dict]:
    # Drop SQL comments so a "--" note can't look like a column.
    body = re.sub(r"--[^\n]*", "", body)
    out: dict[str, dict] = {}
    for m in _COLUMN.finditer(body):
        name = m.group("name")
        if name.upper() in _SKIP:
            continue
        out[name] = {
            "len": int(m.group("len")) if m.group("len") else None,
            "enum": set(re.findall(r"'([^']+)'", m.group("enum"))) if m.group("enum") is not None else None,
        }
    return out


BLOCKS = [(t, b) for t, b in _blocks() if t in Base.metadata.tables]


def test_doc_has_table_blocks():
    assert len(BLOCKS) >= 10, "the CREATE TABLE blocks in docs/SCHEMA.md were not found"


@pytest.mark.parametrize(("table", "body"), BLOCKS, ids=[t for t, _ in BLOCKS])
def test_schema_doc_matches_model(table, body):
    doc = _documented(body)
    model = Base.metadata.tables[table]
    problems = []
    for name in sorted(set(doc) - set(model.c.keys())):
        problems.append(f"{table}.{name}: documented, not in the model")
    for name in sorted(set(model.c.keys()) - set(doc)):
        problems.append(f"{table}.{name}: in the model, not documented")
    for name, spec in doc.items():
        if name not in model.c:
            continue
        ctype = model.c[name].type
        if spec["len"] is not None and isinstance(ctype, String) and not isinstance(ctype, Enum) \
                and ctype.length != spec["len"]:
            problems.append(f"{table}.{name}: doc VARCHAR({spec['len']}) vs model String({ctype.length})")
        if spec["enum"] is not None and isinstance(ctype, Enum) and spec["enum"] != set(ctype.enums):
            problems.append(f"{table}.{name}: doc ENUM {sorted(spec['enum'])} vs model {sorted(ctype.enums)}")
    assert not problems, "docs/SCHEMA.md drifted from app/db/models.py:\n  " + "\n  ".join(problems)
