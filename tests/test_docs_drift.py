"""Documentation-drift review (2026-11-18): the checks that keep the fixed
findings from coming back."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent


def test_every_setting_is_in_the_env_example():
    """D01: 22 settings were missing from .env.example."""
    text = (ROOT / ".env.example").read_text()
    missing = [f"ALERTD_{n.upper()}" for n in Settings.model_fields if f"ALERTD_{n.upper()}" not in text]
    assert not missing, f"add to .env.example: {missing}"


def test_fire_declares_the_errors_it_returns():
    """D03: only 202 / 422 (as a list) were declared; a domain 422's string
    detail broke the generated Python client."""
    spec = json.loads((ROOT / "openapi" / "v1.json").read_text())
    responses = spec["paths"]["/v1/fire"]["post"]["responses"]
    assert {"401", "403", "413", "422", "429"} <= set(responses)
    detail = spec["components"]["schemas"]["ErrorDetail"]["properties"]["detail"]["anyOf"]
    assert {"type": "string"} in detail


def test_the_python_sdk_readme_is_ours():
    """D05 / D12: the generator's README taught a Bearer header and placeholder endpoints."""
    readme = (ROOT / "sdk" / "python" / "README.md").read_text()
    assert readme == (ROOT / "sdk" / "python-README.md").read_text()
    assert 'auth_header_name="X-API-Key"' in readme
    assert "MyDataModel" not in readme
