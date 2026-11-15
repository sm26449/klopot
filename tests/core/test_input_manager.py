"""Tests for app.core.manager (InputManager).

The manager wires DB rows to runtime adapter instances. Tests use a
fake adapter class that records start/stop/update_topics calls so we
don't need a real MQTT broker.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.manager import InputManager, _var_to_mapping, get_manager
from app.core.state_cache import reset_state_cache_for_tests
from app.db.models import Input, InputKind, Variable, VariableSource
from app.inputs.base import BaseInput


class _FakeAdapter(BaseInput):
    """Records lifecycle calls; never opens real sockets."""

    kind = "fake"
    instances: list["_FakeAdapter"] = []

    def __init__(self, *, name: str, config: dict[str, Any], on_value):
        super().__init__(name=name, config=config, on_value=on_value)
        self.started = False
        self.stopped = False
        self.last_topics: dict | None = None
        _FakeAdapter.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def health(self) -> dict[str, Any]:
        return {
            "connected": self.started and not self.stopped,
            "last_msg_ts": None, "msg_count": 0, "error": None,
        }

    async def update_topics(self, topics: dict) -> None:
        self.last_topics = topics


@pytest.fixture(autouse=True)
def _reset_fake_instances():
    _FakeAdapter.instances.clear()
    reset_state_cache_for_tests()


@pytest.fixture
def patch_registry():
    """Replace the inputs registry with our fake adapter for the test."""
    fake_registry = {"mqtt": _FakeAdapter, "http_poll": _FakeAdapter}
    with patch("app.core.manager.REGISTRY", fake_registry):
        yield


# ── _var_to_mapping (pure logic) ──────────────────────────────────


def test_var_to_mapping_mqtt():
    v = Variable(
        name="battery.soc",
        source=VariableSource.mqtt,
        config={"topic": "tankbus/soc", "type": "number"},
        enabled=True,
    )
    m = _var_to_mapping(v)
    assert m is not None
    assert m.source == "mqtt"
    assert m.topic == "tankbus/soc"
    assert m.value_type == "number"


def test_var_to_mapping_mqtt_missing_topic_returns_none():
    v = Variable(
        name="bad", source=VariableSource.mqtt,
        config={"type": "number"}, enabled=True,
    )
    assert _var_to_mapping(v) is None


def test_var_to_mapping_aggregate():
    v = Variable(
        name="pv.total", source=VariableSource.aggregate,
        config={"topics": ["pv/1", "pv/2"], "aggregate": "sum", "type": "number"},
        enabled=True,
    )
    m = _var_to_mapping(v)
    assert m.source == "aggregate"
    assert m.topics == ["pv/1", "pv/2"]
    assert m.aggregate == "sum"


def test_var_to_mapping_aggregate_missing_topics():
    v = Variable(
        name="bad", source=VariableSource.aggregate,
        config={"aggregate": "sum"}, enabled=True,
    )
    assert _var_to_mapping(v) is None


def test_var_to_mapping_constant():
    v = Variable(
        name="thresh.soc", source=VariableSource.constant,
        config={"value": 20, "type": "number"}, enabled=True,
    )
    m = _var_to_mapping(v)
    assert m.source == "constant"
    assert m.constant_value == 20


def test_var_to_mapping_computed_without_formula_returns_none():
    """Computed needs a formula; without one it's skipped (audit A15)."""
    v = Variable(
        name="x", source=VariableSource.computed,
        config={}, enabled=True,
    )
    assert _var_to_mapping(v) is None


def test_var_to_mapping_computed_with_formula():
    v = Variable(
        name="x", source=VariableSource.computed,
        config={"formula": "a + b", "type": "number"}, enabled=True,
    )
    m = _var_to_mapping(v)
    assert m is not None
    assert m.source == "computed"
    assert m.formula == "a + b"


def test_var_to_mapping_schedule_with_cron():
    v = Variable(
        name="tariff", source=VariableSource.schedule,
        config={"cron": "0 22 * * *", "value": "offpeak"}, enabled=True,
    )
    m = _var_to_mapping(v)
    assert m is not None
    assert m.source == "schedule"
    assert m.cron == "0 22 * * *"
    assert m.constant_value == "offpeak"


def test_var_to_mapping_schedule_without_cron_returns_none():
    v = Variable(
        name="bad", source=VariableSource.schedule, config={}, enabled=True,
    )
    assert _var_to_mapping(v) is None


# ── _load: adapter wiring ─────────────────────────────────────────


async def test_load_starts_adapters_for_enabled_inputs(
    db_engine, db_session, patch_registry,
):
    db_session.add(Input(
        id=100, name="edge_mqtt", kind=InputKind.mqtt,
        config={"host": "localhost"}, enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        assert "edge_mqtt" in mgr._adapters
        assert _FakeAdapter.instances[0].started is True
    finally:
        await mgr.stop()


async def test_load_skips_disabled_inputs(
    db_engine, db_session, patch_registry,
):
    db_session.add(Input(
        id=101, name="off", kind=InputKind.mqtt,
        config={}, enabled=False,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        assert "off" not in mgr._adapters
    finally:
        await mgr.stop()


async def test_load_skips_unknown_kind(
    db_engine, db_session, caplog,
):
    """An input.kind not in REGISTRY → log warning, no adapter (the warning
    was missing until the Copilot hygiene pass, #5)."""
    db_session.add(Input(
        id=102, name="weird",
        kind=InputKind.mqtt,  # valid enum
        config={}, enabled=True,
    ))
    await db_session.commit()

    # Patch registry to be empty so the kind lookup fails
    with patch("app.core.manager.REGISTRY", {}), caplog.at_level("WARNING", logger="app.core.manager"):
        mgr = InputManager()
        await mgr.start()
        try:
            assert "weird" not in mgr._adapters
        finally:
            await mgr.stop()
    assert "'weird'" in caplog.text and "no adapter" in caplog.text


async def test_seeds_constant_variables(
    db_engine, db_session, patch_registry,
):
    """Constants get written into the state cache during _load."""
    db_session.add(Variable(
        name="thresh.x", source=VariableSource.constant,
        config={"value": 42, "type": "number"}, enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        assert mgr.cache.value("thresh.x") == 42
    finally:
        await mgr.stop()


# ── reload: hot swap ──────────────────────────────────────────────


async def test_reload_idempotent_when_db_unchanged(
    db_engine, db_session, patch_registry,
):
    """Reload with no DB change should leave adapters in place."""
    db_session.add(Input(
        id=110, name="stable_b", kind=InputKind.mqtt,
        config={}, enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        a1 = mgr._adapters["stable_b"]
        await mgr.reload()
        await mgr.reload()
        a2 = mgr._adapters["stable_b"]
        assert a1 is a2
    finally:
        await mgr.stop()


async def test_reload_keeps_existing_when_config_unchanged(
    db_engine, db_session, patch_registry,
):
    db_session.add(Input(
        id=112, name="stable", kind=InputKind.mqtt,
        config={"host": "x"}, enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        adapter1 = mgr._adapters["stable"]
        await mgr.reload()
        adapter2 = mgr._adapters["stable"]
        # Same instance — config unchanged → no restart
        assert adapter1 is adapter2
        assert adapter1.stopped is False
    finally:
        await mgr.stop()


async def test_reload_evicts_deleted_variable_from_cache(
    db_engine, db_session, patch_registry,
):
    """A06 on the real reload path (``_load`` → ``replace_mappings``): a
    constant seeded into the cache at start must be evicted after the row
    is deleted and the manager reloads — not left serving a removed value
    indefinitely (repro: audit cache_after_variable_delete).

    ``_load`` is driven with the test's own session so the delete is
    visible to the reload read (the DB fixture shares a single SQLite
    connection; two sessions would not see each other's writes)."""
    var = Variable(
        name="audit_deleted_constant", source=VariableSource.constant,
        config={"value": 123, "type": "number"}, enabled=True,
    )
    db_session.add(var)
    await db_session.commit()

    mgr = InputManager()
    await mgr._load(db_session)
    assert mgr.cache.value("audit_deleted_constant") == 123

    # Delete the row the way the API does, then hot-reload.
    await db_session.delete(var)
    await db_session.commit()
    await mgr._load(db_session, reload=True)
    assert mgr.cache.get("audit_deleted_constant") is None


async def test_reload_evicts_disabled_variable_from_cache(
    db_engine, db_session, patch_registry,
):
    """A06: disabling a variable (enabled=False) drops it from the
    enabled set the manager loads, so its cached value is evicted too."""
    var = Variable(
        name="thresh.off", source=VariableSource.constant,
        config={"value": 55, "type": "number"}, enabled=True,
    )
    db_session.add(var)
    await db_session.commit()

    mgr = InputManager()
    await mgr._load(db_session)
    assert mgr.cache.value("thresh.off") == 55

    var.enabled = False
    await db_session.commit()
    await mgr._load(db_session, reload=True)
    assert mgr.cache.get("thresh.off") is None


async def test_reload_is_serialized(db_engine, db_session, patch_registry):
    """R03: concurrent reloads must not run _load at the same time (which
    could interleave and install a stale snapshot)."""
    import asyncio

    mgr = InputManager()
    seen = {"concurrent": 0, "max": 0}

    async def _tracking_load(session, reload=False):
        seen["concurrent"] += 1
        seen["max"] = max(seen["max"], seen["concurrent"])
        await asyncio.sleep(0.02)
        seen["concurrent"] -= 1

    mgr._load = _tracking_load
    await asyncio.gather(mgr.reload(), mgr.reload(), mgr.reload())
    assert seen["max"] == 1  # never two _load passes at once


class _FakeAdapterB(_FakeAdapter):
    """A second fake adapter kind, so a kind switch has a different class."""


async def test_reload_replaces_adapter_on_kind_change(db_engine, db_session):
    """F12: switching an input's kind (even with unchanged config) must
    stop the old adapter and build the new kind's adapter."""
    reg = {"mqtt": _FakeAdapter, "http_poll": _FakeAdapterB}
    with patch("app.core.manager.REGISTRY", reg):
        row = Input(id=130, name="kchg", kind=InputKind.mqtt, config={}, enabled=True)
        db_session.add(row)
        await db_session.commit()

        mgr = InputManager()
        await mgr._load(db_session)
        a1 = mgr._adapters["kchg"]
        assert type(a1) is _FakeAdapter

        row.kind = InputKind.http_poll  # same config, different kind
        await db_session.commit()
        await mgr._load(db_session, reload=True)
        a2 = mgr._adapters["kchg"]
        assert type(a2) is _FakeAdapterB
        assert a1.stopped is True


async def test_force_restart_rebuilds_even_when_config_unchanged(
    db_engine, db_session, patch_registry,
):
    """F13: /restart must truly stop+reconstruct the adapter, not keep the
    existing instance the way a plain config-equal reload does."""
    db_session.add(Input(
        id=131, name="fr", kind=InputKind.mqtt, config={"host": "x"}, enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        a1 = mgr._adapters["fr"]
        rebuilt = await mgr.force_restart("fr")
        a2 = mgr._adapters["fr"]
        assert rebuilt is True
        assert a1 is not a2       # a brand-new instance
        assert a1.stopped is True  # the old one was stopped
    finally:
        await mgr.stop()


# ── Health + accessors ────────────────────────────────────────────


async def test_adapter_health_aggregates(
    db_engine, db_session, patch_registry,
):
    db_session.add(Input(
        id=120, name="health_a", kind=InputKind.mqtt,
        config={}, enabled=True,
    ))
    db_session.add(Input(
        id=121, name="health_b", kind=InputKind.mqtt,
        config={}, enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        h = mgr.adapter_health()
        assert "health_a" in h and "health_b" in h
        assert h["health_a"]["connected"] is True
    finally:
        await mgr.stop()


async def test_get_adapter_returns_running_instance(
    db_engine, db_session, patch_registry,
):
    db_session.add(Input(
        id=130, name="get_me", kind=InputKind.mqtt,
        config={}, enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        a = mgr.get_adapter("get_me")
        assert a is not None and a.name == "get_me"
        assert mgr.get_adapter("not_running") is None
    finally:
        await mgr.stop()


async def test_topic_filters_pushed_to_adapters(
    db_engine, db_session, patch_registry,
):
    db_session.add(Input(
        id=140, name="t_filter", kind=InputKind.mqtt,
        config={}, enabled=True,
    ))
    db_session.add(Variable(
        name="x",
        source=VariableSource.mqtt,
        config={"topic": "foo/bar", "type": "number"},
        enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    try:
        adapter = mgr._adapters["t_filter"]
        assert adapter.last_topics is not None
        assert "foo/bar" in adapter.last_topics["exact"]
    finally:
        await mgr.stop()


# ── Lifecycle ────────────────────────────────────────────────────


async def test_start_idempotent(db_engine, patch_registry):
    mgr = InputManager()
    await mgr.start()
    started_first = mgr._started
    await mgr.start()  # second call: no-op
    assert mgr._started is True
    assert started_first is True
    await mgr.stop()


async def test_stop_idempotent(db_engine, patch_registry):
    mgr = InputManager()
    await mgr.stop()  # not started — no-op
    assert mgr._started is False


async def test_stop_clears_adapters(
    db_engine, db_session, patch_registry,
):
    db_session.add(Input(
        id=150, name="ad", kind=InputKind.mqtt, config={}, enabled=True,
    ))
    await db_session.commit()

    mgr = InputManager()
    await mgr.start()
    await mgr.stop()
    assert mgr._adapters == {}


def test_get_manager_singleton():
    a = get_manager()
    b = get_manager()
    assert a is b


# ── A32: input_id isolation end-to-end ────────────────────────────


def test_var_to_mapping_carries_input_id():
    v = Variable(
        name="x", source=VariableSource.mqtt,
        config={"topic": "t", "type": "number"}, enabled=True, input_id=7,
    )
    assert _var_to_mapping(v).input_id == 7


async def test_adapter_on_value_isolated_by_input(
    db_engine, db_session, patch_registry,
):
    """Two inputs share a topic; each has its own bound variable. A message
    delivered through one input's adapter must only update that input's
    variable (audit A32)."""
    db_session.add_all([
        Input(id=200, name="brokerA", kind=InputKind.mqtt, config={}, enabled=True),
        Input(id=201, name="brokerB", kind=InputKind.mqtt, config={}, enabled=True),
        Variable(name="va", source=VariableSource.mqtt,
                 config={"topic": "shared/t", "type": "number"},
                 enabled=True, input_id=200),
        Variable(name="vb", source=VariableSource.mqtt,
                 config={"topic": "shared/t", "type": "number"},
                 enabled=True, input_id=201),
    ])
    await db_session.commit()

    mgr = InputManager()
    await mgr._load(db_session)
    # Deliver via broker A's adapter (its on_value is bound to input 200).
    await mgr._adapters["brokerA"].on_value("shared/t", 42, "mqtt")
    assert mgr.cache.value("va") == 42.0
    assert mgr.cache.get("vb") is None  # broker A must not touch vb
