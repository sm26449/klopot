"""F31: the runtime mapping and the /v1/variables API must resolve the same
staleness policy, so is_stale in the API can never disagree with how the
engine actually treats a value."""
from __future__ import annotations

from app.api.v1.variables import _stale_after_sec
from app.core.manager import _var_to_mapping
from app.core.staleness import DEFAULT_STALE_SEC, effective_stale_after_sec
from app.db.models import Variable, VariableSource


def _var(source, cfg):
    return Variable(name="v", source=source, config=cfg, enabled=True)


def test_effective_policy_source_aware():
    assert effective_stale_after_sec("constant", None) is None
    assert effective_stale_after_sec("schedule", None) is None
    assert effective_stale_after_sec("mqtt", None) == DEFAULT_STALE_SEC
    assert effective_stale_after_sec("aggregate", None) == DEFAULT_STALE_SEC
    assert effective_stale_after_sec("computed", None) == DEFAULT_STALE_SEC
    assert effective_stale_after_sec("mqtt", 42) == 42
    assert effective_stale_after_sec("mqtt", 0) == DEFAULT_STALE_SEC  # invalid → default
    assert effective_stale_after_sec("mqtt", True) == DEFAULT_STALE_SEC  # bool guard


def test_mqtt_without_policy_is_stale_at_default_at_runtime():
    # The core F31 bug: runtime used to store None (never stale) here.
    m = _var_to_mapping(_var(VariableSource.mqtt, {"topic": "t", "type": "number"}))
    assert m.stale_after_sec == DEFAULT_STALE_SEC


def test_schedule_latches_at_runtime():
    m = _var_to_mapping(_var(
        VariableSource.schedule, {"cron": "* * * * *", "value": 1, "type": "number"},
    ))
    assert m.stale_after_sec is None


def test_api_and_runtime_agree_per_source():
    cases = [
        (VariableSource.mqtt, {"topic": "t", "type": "number"}),
        (VariableSource.aggregate, {"topics": ["a", "b"], "type": "number"}),
        (VariableSource.computed, {"formula": "1+1", "type": "number"}),
        (VariableSource.constant, {"value": 5, "type": "number"}),
        (VariableSource.schedule, {"cron": "* * * * *", "value": 1}),
    ]
    for source, cfg in cases:
        var = _var(source, cfg)
        m = _var_to_mapping(var)
        runtime = m.stale_after_sec if m is not None else None
        # constant mapping carries no stale field → effective policy is None
        if source is VariableSource.constant:
            runtime = None
        assert runtime == _stale_after_sec(var), f"mismatch for {source}"
