"""B-03: a reload must not drop the members of an aggregate whose binding
did not change.

``replace_mappings`` used to rebuild every aggregate buffer from scratch on
every hot reload, so any unrelated input/variable edit silently forgot the
cached members. A sum of 10 + 20 = 30 would quietly become 10 the next time
only the first source republished, because the second (still-valid) member's
20 had been wiped and the quiet source would not replay it for a while.

The fix retains the buffer for an aggregate whose mapping is unchanged, keeps
only still-applicable members when the membership changes, and recomputes the
output of a rebound aggregate so it stays consistent after the reload.
"""
from __future__ import annotations

import pytest

from app.core.state_cache import StateCache
from app.core.variable_resolver import VariableResolver, VarMapping

pytestmark = pytest.mark.anyio


@pytest.fixture
def cache():
    return StateCache()


@pytest.fixture
def resolver(cache):
    return VariableResolver(cache)


def _agg(name="pv.total", topics=("pv/1", "pv/2"), op="sum", stale=None):
    return VarMapping(
        name=name, source="aggregate", value_type="number",
        topics=list(topics), aggregate=op, stale_after_sec=stale,
    )


async def test_unchanged_mapping_retains_members_across_reload(resolver, cache):
    """The core regression: an unrelated edit reloads the config, but the
    aggregate's own binding is identical, so its members survive and a later
    single-member message does not collapse the sum."""
    resolver.replace_mappings([_agg()])
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    await resolver.handle_inbound("pv/2", 20, "mqtt")
    assert cache.value("pv.total") == 30.0

    # An unrelated variable is added — the aggregate mapping is unchanged.
    invalidated = resolver.replace_mappings([
        _agg(),
        VarMapping(name="unrelated", source="mqtt", value_type="number", topic="x/y"),
    ])
    assert "pv.total" not in invalidated          # binding didn't change
    assert cache.value("pv.total") == 30.0        # output untouched by the swap

    # Only pv/1 republishes. The retained pv/2 = 20 must still contribute.
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    assert cache.value("pv.total") == 30.0        # 10 + retained 20, NOT 10


async def test_membership_change_keeps_applicable_members(resolver, cache):
    """Adding a sibling member must not wipe the members already buffered:
    only members whose topic left the membership are forgotten."""
    resolver.replace_mappings([_agg(topics=("pv/1", "pv/2"))])
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    await resolver.handle_inbound("pv/2", 20, "mqtt")
    assert cache.value("pv.total") == 30.0

    # Drop pv/2, add pv/3. pv/1 is still a member and must be preserved.
    invalidated = resolver.replace_mappings([_agg(topics=("pv/1", "pv/3"))])
    assert "pv.total" in invalidated              # binding changed
    # Recompute (as the manager does for a rebound aggregate): pv/1 survives,
    # pv/2 is gone.
    await resolver.recompute_aggregates(only={"pv.total"})
    assert cache.value("pv.total") == 10.0        # only the retained pv/1

    # The new member now contributes alongside the preserved one.
    await resolver.handle_inbound("pv/3", 5, "mqtt")
    assert cache.value("pv.total") == 15.0        # 10 (kept) + 5 (new)


async def test_rebound_aggregate_recompute_is_immediate(resolver, cache):
    """A rebound aggregate's output is recomputed from retained members right
    away, without waiting for a fresh member message."""
    resolver.replace_mappings([_agg(topics=("pv/1", "pv/2"), op="sum")])
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    await resolver.handle_inbound("pv/2", 20, "mqtt")

    # Change only the aggregate op (sum → max): membership identical, so both
    # members are preserved, and the recompute reflects the new op at once.
    invalidated = resolver.replace_mappings([_agg(topics=("pv/1", "pv/2"), op="max")])
    assert "pv.total" in invalidated
    await resolver.recompute_aggregates(only={"pv.total"})
    assert cache.value("pv.total") == 20.0        # max(10, 20), no new message


async def test_deleted_aggregate_drops_its_buffer(resolver, cache):
    """An aggregate removed from the config leaves no buffer behind to leak
    into a later aggregate that reuses the name."""
    resolver.replace_mappings([_agg(name="old.agg", topics=("a",))])
    await resolver.handle_inbound("a", 99, "mqtt")
    assert cache.value("old.agg") == 99.0

    resolver.replace_mappings([])                 # removed entirely
    assert resolver._agg_buffers == {}            # no orphan buffer retained
