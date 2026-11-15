"""The generated Python SDK (sdk/python, package klopot_client) against the
real app, in-process — proves the committed client matches the API."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python"))

from klopot_client import AuthenticatedClient  # noqa: E402
from klopot_client.api.fire import post_fire_v1_fire_post  # noqa: E402
from klopot_client.models import FireRequest, FireRequestContext, FireResponse  # noqa: E402

from app.db.models import Severity, Template  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
async def sdk(db_engine, db_session, admin_key):
    db_session.add(Template(type="sdk_probe", severity=Severity.info, title_template="Probe {n}", min_repeat_min=0))
    await db_session.commit()
    client = AuthenticatedClient(
        base_url="http://testserver", token=admin_key, prefix="", auth_header_name="X-API-Key",
        httpx_args={"transport": ASGITransport(app=create_app())},
    )
    async with client:
        yield client


async def test_fire_with_the_generated_client(sdk):
    body = FireRequest(type_="sdk_probe", context=FireRequestContext.from_dict({"n": 7}),
                       idempotency_key="sdk-1")
    res = await post_fire_v1_fire_post.asyncio(client=sdk, body=body)
    assert isinstance(res, FireResponse)
    assert res.title == "Probe 7"
    assert res.episode == "opened"
    again = await post_fire_v1_fire_post.asyncio(client=sdk, body=body)
    assert again.episode == "repeat"
