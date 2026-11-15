"""Pack parsing, parameters and substitution (app/services/packs.py, docs/PACKS.md)."""
from __future__ import annotations

import pytest

from app.services import packs
from app.services.config_import_schema import validate_pack


def _pack(params: list[dict], body: dict) -> packs.Pack:
    return packs.parse({"pack": {"id": "demo", "name": "Demo", "parameters": params}, **body})


def test_header_is_optional_and_split_from_the_body():
    p = packs.parse("version: '1.0'\ntemplates: []\n")
    assert p.header is None and p.body == {"version": "1.0", "templates": []}
    p = packs.parse({"pack": {"id": "x1", "name": {"en": "X", "ro": "X"}}, "templates": [{"type": "a"}]})
    assert p.header.id == "x1" and "pack" not in p.body and p.counts() == {"templates": 1}


@pytest.mark.parametrize("header, fragment", [
    ({"id": "Bad id", "name": "x"}, "pack.id"),
    ({"id": "ok-id", "name": "x", "colour": "red"}, "pack.colour"),
    ({"id": "ok-id", "name": "x", "parameters": [{"name": "a"}, {"name": "a"}]}, "duplicate"),
    ({"id": "ok-id", "name": "x", "parameters": [{"name": "a", "type": "file"}]}, "type"),
])
def test_invalid_headers_are_reported(header, fragment):
    with pytest.raises(packs.PackError) as e:
        packs.parse({"pack": header})
    assert fragment in "; ".join(e.value.errors)


def test_whole_value_keeps_the_parameter_type_and_inline_becomes_text():
    p = _pack([{"name": "port", "type": "integer", "default": 1883}, {"name": "room"},
               {"name": "on", "type": "boolean", "default": True}],
              {"inputs": [{"config": {"port": "${port}", "topic": "sensors/${room}/t", "flag": "${on}", "note": "on=${on}"}}]})
    doc = packs.render(p, {"room": "attic"}).document
    assert doc["inputs"][0]["config"] == {"port": 1883, "topic": "sensors/attic/t", "flag": True, "note": "on=true"}


def test_given_values_are_coerced_and_checked():
    p = _pack([{"name": "n", "type": "number", "default": 1}, {"name": "i", "type": "integer", "default": 1},
               {"name": "e", "type": "env", "default": "TOKEN"}, {"name": "c", "type": "channel", "default": "ui_default"}],
              {"x": ["${n}", "${i}", "${e}", "${c}"]})
    assert packs.render(p, {"n": "2.5", "i": "7"}).document["x"] == [2.5, 7, "TOKEN", "ui_default"]
    with pytest.raises(packs.PackError) as e:
        packs.render(p, {"n": "abc", "i": "1.5", "e": "lower-case", "c": "Bad Name"})
    assert len(e.value.errors) == 4


def test_required_unknown_and_unused_parameters_are_errors():
    p = _pack([{"name": "host"}, {"name": "spare", "default": "x"}], {"v": "${host}"})
    with pytest.raises(packs.PackError) as e:
        packs.render(p, {"nope": 1})
    msg = "; ".join(e.value.errors)
    assert "unknown parameter: nope" in msg and "host: required" in msg
    with pytest.raises(packs.PackError) as e:
        packs.render(p, {"host": "h"})
    assert "never used: ['spare']" in "; ".join(e.value.errors)


def test_undeclared_placeholder_is_an_error_and_escape_writes_a_literal():
    p = _pack([{"name": "a", "default": "1"}], {"v": "${a} $${literal} ${typo}"})
    with pytest.raises(packs.PackError) as e:
        packs.render(p)
    assert "${typo} is not a declared parameter" in e.value.errors[0]
    ok = _pack([{"name": "a", "default": "1"}], {"v": "${a} costs $${price}", "t": "{name} stays"})
    assert packs.render(ok).document == {"v": "1 costs ${price}", "t": "{name} stays"}


def test_optional_parameter_without_value_renders_empty():
    p = _pack([{"name": "unit", "required": False}], {"t": "{v}${unit}"})
    assert packs.render(p).document == {"t": "{v}"}


def test_every_catalog_pack_renders_with_defaults_into_a_valid_document():
    catalog = packs.catalog()
    assert {"self-monitoring", "service-heartbeat", "sensor-threshold", "alertmanager"} <= set(catalog)
    for pack_id, pack in catalog.items():
        assert pack.header and pack.header.id == pack_id
        assert isinstance(pack.header.name, dict) and {"en", "ro"} <= set(pack.header.name), pack_id
        for param in pack.header.parameters:
            assert isinstance(param.label, dict) and {"en", "ro"} <= set(param.label), (pack_id, param.name)
        assert validate_pack(packs.render(pack).document) == [], pack_id
