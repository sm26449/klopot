"""The traefik overlays keep Klopot private unless compose.public.yml opens
exactly `POST /v1/fire` (public-exposure review, stage 0).

These check the shipped files; the routing itself was verified once against a
real traefik v3 (allowed / 403 / 413 / 429). Keep both in step when editing."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _labels(name: str) -> dict[str, str]:
    return yaml.safe_load((ROOT / name).read_text())["services"]["alertd"]["labels"]


def test_the_traefik_overlay_is_private_and_requires_trusted_proxies():
    labels = _labels("compose.traefik.yml")
    env = yaml.safe_load((ROOT / "compose.traefik.yml").read_text())["services"]["alertd"]["environment"]
    assert labels["traefik.http.routers.klopot.middlewares"].split(",")[0] == "klopot-private"
    allow = labels["traefik.http.middlewares.klopot-private.ipallowlist.sourcerange"]
    assert allow.startswith("${KLOPOT_PRIVATE_CIDRS:-")
    assert "0.0.0.0/0" not in allow
    assert "::/0" not in allow
    assert ":?" in env["ALERTD_TRUSTED_PROXY_CIDRS"], "behind traefik the proxy's address must be set"


def test_the_public_overlay_opens_exactly_post_fire_with_limits():
    public = _labels("compose.public.yml")
    rule = public["traefik.http.routers.klopot-public.rule"]
    assert "Method(`POST`)" in rule
    assert "Path(`/v1/fire`)" in rule
    assert "PathPrefix" not in rule, "an exact path, never a prefix"
    assert "PathRegexp" not in rule
    assert int(public["traefik.http.routers.klopot-public.priority"]) > int(
        _labels("compose.traefik.yml")["traefik.http.routers.klopot.priority"])
    chain = public["traefik.http.routers.klopot-public.middlewares"].split(",")
    assert chain[:3] == ["klopot-public-body", "klopot-public-inflight", "klopot-public-rate"], chain
    assert public["traefik.http.middlewares.klopot-public-inflight.inflightreq.sourcecriterion.requesthost"] == "true"


def test_the_file_provider_example_matches_the_overlays():
    doc = yaml.safe_load((ROOT / "deploy/traefik/klopot.example.yml").read_text())["http"]
    assert doc["routers"]["klopot"]["middlewares"][0] == "klopot-private"
    assert "0.0.0.0/0" not in doc["middlewares"]["klopot-private"]["ipAllowList"]["sourceRange"]
    assert "klopot-public" not in doc["routers"], "the public router ships commented out"
