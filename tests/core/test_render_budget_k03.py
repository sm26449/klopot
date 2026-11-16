"""Rendering stays cheap whatever the context holds (review K03).

- The output cap was applied after ``re.sub`` had built the whole string:
  ``"{x}" * 5000`` with a 600 KB value allocated ~3 GB on the event loop.
- The preview found unresolved names with a regex over the *output*; a context
  value of ``"[?" * n`` made that regex quadratic (50 K characters held the
  loop for ~30 s, reachable with a ``read`` key). It also reported a value
  that merely contained ``[?x]`` as a missing variable.
"""
from __future__ import annotations

import time

from app.core import rendering
from app.core.rendering import render, render_with_missing
from app.db.models import Severity, Template


def test_output_is_bounded_while_it_is_built():
    started = time.perf_counter()
    out = render("{x}" * 5000, {"x": "A" * 600_000})
    assert len(out) == rendering._MAX_RENDER_LEN
    assert time.perf_counter() - started < 0.5


def test_missing_names_come_from_the_substitution():
    text, missing = render_with_missing("{a} {b.c} {d | upper} %e% {v} {n | div(0)}",
                                        {"a": 1, "v": "[?ghost]", "n": 5})
    assert text == "1 [?b.c] [?d] [?e] [?ghost] [?n|div(0)]"
    assert missing == ["b.c", "d", "e", "n"]          # not "ghost": a value is not a placeholder


async def test_preview_with_a_hostile_value_is_fast(db_client, db_session, admin_key):
    db_session.add(Template(type="t_k03", severity=Severity.info, title_template="T {v}",
                            message_template="M {v} {absent}"))
    await db_session.commit()
    started = time.perf_counter()
    r = await db_client.post("/v1/templates/t_k03/preview", headers={"X-API-Key": admin_key},
                             json={"context": {"v": "[?" * 50_000}})
    elapsed = time.perf_counter() - started
    assert r.status_code == 200, r.text[:200]
    assert r.json()["missing_vars"] == ["absent"]
    # The quadratic regex took ~30 s here; a linear preview takes ~0.3 s, and
    # several times that on a loaded machine (1.8 s seen with the host busy).
    # The bound tells the two apart without measuring the machine.
    assert elapsed < 5.0, f"preview took {elapsed:.1f} s"
