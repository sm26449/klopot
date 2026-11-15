"""docker-compose.yml passes every setting of app/config.py into the container,
with the same default — otherwise a value set in .env silently has no effect."""
from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
# Not operator settings: identity, the version (from app.__version__), SQL echo (debug).
NOT_PASSED = {"service_name", "version", "database_echo"}
# Deliberately different in the container: fixed bind address, MQTT on the host,
# cookies insecure on plain-HTTP localhost (compose.traefik.yml forces true).
CONTAINER_DEFAULTS = {"bind_host", "bind_port", "mqtt_host", "cookie_secure"}


def _compose_env() -> dict[str, str | None]:
    """ALERTD_* → its `${VAR:-default}` default (None when the value is a literal)."""
    out: dict[str, str | None] = {}
    for name, value in re.findall(r"^\s+(ALERTD_[A-Z0-9_]+):\s*(.*)$", COMPOSE.read_text(), re.M):
        m = re.fullmatch(r"\$\{" + name + r":-(.*)\}", value.strip())
        out[name] = m.group(1) if m else None
    return out


def test_every_setting_reaches_the_container():
    env = _compose_env()
    missing = sorted(f"ALERTD_{n.upper()}" for n in Settings.model_fields
                     if n not in NOT_PASSED and f"ALERTD_{n.upper()}" not in env)
    assert not missing, f"add to docker-compose.yml environment: {missing}"


def test_compose_defaults_match_the_code():
    env = _compose_env()
    wrong = {}
    for name, field in Settings.model_fields.items():
        key = f"ALERTD_{name.upper()}"
        if name in NOT_PASSED | CONTAINER_DEFAULTS or env.get(key) is None:
            continue
        raw = env[key]
        if raw == "":
            ok = field.default in ("", None)
        else:
            ok = Settings(**{name: raw}).model_dump()[name] == field.default
        if not ok:
            wrong[key] = (raw, field.default)
    assert not wrong, f"compose default differs from app/config.py: {wrong}"


def test_no_known_password_is_a_default():
    """Pre-open-source audit: a forgotten .env must not leave the stack running
    with a password everyone knows. The URL has no default (Klopot refuses to
    start), MYSQL_* passwords have none, and the healthcheck keeps the password
    off the command line."""
    text = COMPOSE.read_text()
    assert Settings.model_fields["database_url"].default == ""
    assert _compose_env()["ALERTD_DATABASE_URL"] == ""
    assert re.search(r"MYSQL_(ROOT_)?PASSWORD:\s*\$\{MYSQL_(ROOT_)?PASSWORD:-[^}]", text) is None
    assert "-p${" not in text and "MYSQL_PWD=" in text


def test_a_missing_database_url_is_a_clear_error():
    import pytest

    with pytest.raises(RuntimeError, match="ALERTD_DATABASE_URL is not set"):
        Settings(database_url="").require_database_url()
    with pytest.raises(RuntimeError, match="placeholder"):
        Settings(database_url="mysql+aiomysql://alertd:<MYSQL_PASSWORD>@mysql:3306/alertd").require_database_url()
    assert Settings(database_url="sqlite+aiosqlite://").require_database_url() == "sqlite+aiosqlite://"
