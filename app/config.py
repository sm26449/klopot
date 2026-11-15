"""Runtime configuration via Pydantic Settings.

All values come from environment variables. Each setting has a sane
default so the service starts in a development context without a
.env file. Production deployment supplies values via docker-compose
``environment:`` block (see ``docker-compose.yml``).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Secrets a `*_ref` is allowed to resolve by default — the names documented in
# .env.example (channel + input secrets, and the MQTT credentials reused by the
# MQTT input). Anything else must be opted in via ALERTD_SECRET_REF_ALLOW, so a
# ref can never reach ALERTD_DATABASE_URL or another process secret (audit S-04).
# Env vars named KLOPOT_SECRET_<NAME> are always resolvable by a *_ref: the
# one-step way to give Klopot a secret (put it in secrets.env, restart).
SECRET_REF_PREFIX = "KLOPOT_SECRET_"
SECRET_REF_PREFIX_RE = re.compile(r"KLOPOT_SECRET_[A-Z0-9_]+")

_DEFAULT_SECRET_REF_ALLOW: frozenset[str] = frozenset({
    "TELEGRAM_BOT_TOKEN",
    "SMTP_PASSWORD",
    "SMS_GATEWAY_API_KEY",
    "ALERTD_EXTERNAL_ALARM_TOKEN",
    "ALERTD_MQTT_USERNAME",
    "ALERTD_MQTT_PASSWORD",
})


class Settings(BaseSettings):
    """Service configuration. Lifecycle: read once at app boot."""

    model_config = SettingsConfigDict(
        env_prefix="ALERTD_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service identity ──────────────────────────────────────
    service_name: str = "alertd"
    # Version is sourced dynamically from app.__version__ (single
    # source of truth — kept in sync with pyproject.toml). The
    # hardcoded default here used to drift behind reality (audit
    # L-3 found it stuck at 1.0.4 while CHANGELOG was on 1.0.8+).
    version: str = ""

    def require_database_url(self) -> str:
        """The database URL, or a clear error when it is not configured."""
        if not self.database_url.strip():
            raise RuntimeError(
                "ALERTD_DATABASE_URL is not set — set it in .env, e.g. "
                "mysql+aiomysql://alertd:<MYSQL_PASSWORD>@mysql:3306/alertd (see .env.example)"
            )
        if "<MYSQL_PASSWORD>" in self.database_url:
            raise RuntimeError(
                "ALERTD_DATABASE_URL still holds the <MYSQL_PASSWORD> placeholder from "
                ".env.example — put the database password in its place"
            )
        return self.database_url

    def model_post_init(self, __context):
        if not self.version:
            from . import __version__
            object.__setattr__(self, "version", __version__)

    # ── HTTP server ───────────────────────────────────────────
    bind_host: str = "0.0.0.0"
    bind_port: int = 5090

    # ── Database (async SQLAlchemy URL) ───────────────────────
    # Format: mysql+aiomysql://user:pass@host:port/db
    # Required, no default: a default would carry a publicly known password.
    # Use require_database_url() where a connection is made.
    database_url: str = ""
    database_pool_size: int = 10
    database_max_overflow: int = 5
    database_echo: bool = False

    # Max concurrent password/key hashing operations offloaded to threads
    # (audit A13). Bounds CPU + argon2 memory (~64 MiB each) so an auth
    # burst can't starve the event loop or thrash the host.
    hash_max_concurrency: int = Field(default=4, ge=1, le=64)

    # ── MQTT ──────────────────────────────────────────────────
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = "alertd"
    mqtt_keepalive_sec: int = 60

    # ── Logging ───────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"

    # ── Behavior tuning (defaults; admin can override per-rule
    #     where applicable, via /v1/settings) ──────────────────
    default_eval_interval_sec: int = Field(default=10, ge=1, le=3600)
    idempotency_window_sec: int = Field(default=300, ge=0, le=3600)
    log_retention_days: int = Field(default=90, ge=1, le=3650)
    audit_retention_days: int = Field(default=365, ge=1, le=3650)
    circuit_breaker_threshold: int = Field(default=3, ge=1)
    circuit_breaker_open_sec: int = Field(default=60, ge=1)
    # Hard ceiling on a single channel send. Each adapter sets its own HTTP
    # timeout, but a hung send (or a stuck half-open breaker probe) must not
    # stall the dispatcher or the delivery worker, or wedge the breaker until a
    # restart — so every send is bounded by this outer timeout (audit C-01/C-02).
    # Capped below FIRST_ATTEMPT_BUDGET_SEC (45) and the delivery lease (60) so a
    # per-send timeout always fires first — otherwise the budget cancel re-opens
    # the C-01 race, or a leased delivery could be sent twice.
    adapter_send_timeout_sec: float = Field(default=30.0, ge=1.0, le=40.0)
    # Hard admission caps on config-entity counts (audit D-02/A-14). NFR.md
    # documents these as the intentional v1 limits; they are enforced at create
    # (REST + config import) with a 409 once the total is reached. 0 disables a
    # cap. NOTE: an instance already over a cap (e.g. a deployment with >100
    # rules) must raise the matching ALERTD_MAX_* before it can create more.
    max_rules: int = Field(default=100, ge=0, le=100000)
    max_inputs: int = Field(default=50, ge=0, le=100000)
    max_channels: int = Field(default=20, ge=0, le=100000)
    # SSRF egress policy (audit R06). Cloud-metadata / link-local addresses
    # are ALWAYS blocked for outbound webhook / HTTP-poll targets. Set this
    # true to additionally block private + loopback ranges — off by default
    # because internal destinations (the container network, an SMS gateway,
    # an MQTT broker) are a supported use case.
    block_private_egress: bool = False
    # Resource budgets for input-driven state (audit D1-01/D1-02). A wildcard
    # aggregate buffers one entry per matching topic; evicting stale members
    # bounds the churn case, and this caps the no-TTL case. On overflow the
    # aggregate is invalidated (None) and flagged in health — never silently
    # trimmed while presenting a complete sum. 0 disables the cap.
    max_aggregate_members: int = Field(default=1000, ge=0, le=1000000)
    # Finite MQTT incoming queue (aiomqtt default is unbounded → OOM under a
    # burst). Messages beyond this are dropped by the client (QoS0); a missed
    # update degrades to staleness, and a reconnect re-subscribe redelivers
    # retained state.
    mqtt_queue_max: int = Field(default=10000, ge=16, le=1000000)
    # Drop (and count) an MQTT payload larger than this many bytes before
    # decode, so one oversized message can't blow up memory.
    mqtt_max_payload_bytes: int = Field(default=262144, ge=1024, le=67108864)
    # Byte budgets for inbound/outbound HTTP (audit A-08). The global request
    # cap is enforced by an ASGI middleware before any handler buffers the body
    # (Content-Length fast-reject + streamed cap → 413). The webhook-ingress
    # cap is tighter for that public, token-gated endpoint. The response cap
    # bounds a (possibly compressed→huge) upstream body for poll + webhook.
    max_request_bytes: int = Field(default=1048576, ge=1024, le=268435456)
    max_webhook_bytes: int = Field(default=65536, ge=256, le=268435456)
    # Alertmanager / Grafana groups are larger than plain webhook values.
    max_alertmanager_bytes: int = Field(default=1048576, ge=1024, le=268435456)
    max_response_bytes: int = Field(default=4194304, ge=1024, le=268435456)
    # Reject a config YAML/JSON nested deeper than this (billion-laughs / deep
    # recursion). Aliases are rejected outright by the import loader.
    max_config_depth: int = Field(default=50, ge=4, le=1000)
    # Auto-disable rules after N consecutive eval errors. Defends against
    # silent decay when a var binding goes stale and the rule never fires
    # again (e.g. topic renamed in an upstream cutover). Set to 0 to
    # disable the safety net entirely.
    eval_error_disable_threshold: int = Field(default=50, ge=0, le=100000)
    # Escalation: re-page a dispatched critical that is still
    # unacknowledged after N minutes, once, via escalation_channel.
    # 0 — or no channel (the default: no install has a channel by a fixed
    # name) — disables escalation entirely.
    escalation_after_min: int = Field(default=15, ge=0, le=1440)
    escalation_channel: str = ""
    # Daily suppressed-alerts digest, fired at this local hour
    # (settings.tz). -1 disables.
    digest_hour: int = Field(default=21, ge=-1, le=23)
    # "Snooze until morning" (Telegram buttons): this local hour (settings.tz).
    snooze_morning_hour: int = Field(default=8, ge=0, le=23)

    # ── Legacy delivery-gate variable (deprecated) ────────────
    # Before migration 0030 every template's ``require_pv_kw`` compared
    # against this one variable. Templates now name their own
    # ``gate_variable``; this is read only by migration 0030 (to convert
    # existing rows) and when an old /v1 client writes ``require_pv_kw``
    # without a variable. Removed in /v2.
    pv_power_var: str = ""

    # ── Localization ──────────────────────────────────────────
    tz: str = "UTC"

    # ── Bootstrap ─────────────────────────────────────────────
    # Plaintext API key with admin scope to seed on first run if the
    # api_keys table is empty. Used to bootstrap admin access without
    # direct DB SQL on a fresh install.
    bootstrap_admin_key: str = ""

    # ── Admin UI / human auth (docs/AUTH_MODEL.md, migration 0008) ──
    # Mount the static admin SPA at /admin. The API (incl. /v1/auth) is
    # available regardless; this only controls the HTML/JS being served.
    admin_ui_enabled: bool = True
    # Plaintext password for the single ``admin`` user, used ONLY when
    # ``admin_users`` is empty (first boot). The account is created with
    # must_change_password=1; clear this variable after the first login.
    admin_bootstrap_password: str = ""
    # Sliding idle timeout and absolute lifetime of a browser session.
    session_idle_hours: int = Field(default=12, ge=1, le=24 * 30)
    session_max_days: int = Field(default=7, ge=1, le=365)
    # ``Secure`` flag on the session cookies. True in production (TLS
    # via traefik); false only for plain-HTTP development.
    cookie_secure: bool = True
    # Login lockout: N failed attempts for a username, or M for a source
    # IP, within the last ``login_lockout_min`` minutes → 423 until the
    # oldest counted failure ages out of the window.
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_max_failures_per_ip: int = Field(default=20, ge=1, le=1000)
    login_lockout_min: int = Field(default=15, ge=1, le=1440)
    # Retention for login_attempts + expired/revoked sessions.
    auth_history_days: int = Field(default=30, ge=1, le=3650)

    # Comma-separated CIDRs of trusted reverse proxies (e.g. traefik). When the
    # peer address is inside one of these, the real client IP is taken from the
    # rightmost non-trusted X-Forwarded-For entry so per-IP login throttling
    # targets the actual client, not the proxy (audit S-07). Empty = trust no
    # proxy and use the direct peer address. An invalid entry, or a /0, stops
    # the service at startup.
    trusted_proxy_cidrs: str = ""
    # Largest `context` POST /v1/fire accepts, as compact JSON in bytes
    # (utils/context_budget.py; nesting is capped at 16 levels too).
    fire_context_max_bytes: int = Field(default=16384, ge=1024, le=1_048_576)
    # ── Activity log (docs/ACTIVITY_LOG.md) ────────────────────
    # false: keep every activity row but no request / response bodies.
    activity_log_bodies: bool = True
    # Rows waiting for the background writer; beyond this a row is dropped
    # (and counted in klopot_activity_dropped_total) rather than block.
    activity_queue_max: int = Field(default=5000, ge=100, le=1_000_000)

    # ── Web Push (docs/WEB_PUSH.md) ────────────────────────────
    # A device's endpoint is a URL its browser chose; only these push
    # services are accepted (registration and every send). Extra hosts, e.g. a
    # self-hosted push service: comma-separated, "*.example.com" allowed.
    push_allowed_hosts: str = ""

    @property
    def push_allowed_host_list(self) -> list[str]:
        defaults = ["*.push.apple.com", "fcm.googleapis.com", "updates.push.services.mozilla.com",
                    "*.notify.windows.com"]
        return defaults + [h.strip().lower() for h in self.push_allowed_hosts.split(",") if h.strip()]

    # ── API surface exposure (audit S-12) ─────────────────────
    # /docs + /redoc + /openapi.json and the unauthenticated /v1/metrics are
    # convenient but leak the API shape / internal counters if exposed publicly.
    # Both are tri-state: None = auto by environment (treat cookie_secure=true,
    # i.e. a TLS/prod deploy, as "lock down"); set explicitly to override.
    # docs_enabled only decides whether the reference is PUBLIC: when off, an
    # authenticated caller (admin session or API key) still gets it (app.api.docs).
    docs_enabled: bool | None = None          # None → public only when NOT prod
    metrics_require_auth: bool | None = None   # None → require a read key in prod

    # ── Secret references ─────────────────────────────────────
    # `*_ref` channel/input config points at an environment variable holding a
    # secret. Resolution is default-DENY: only names on this allowlist resolve,
    # so a config author can't point a ref at ALERTD_DATABASE_URL (or any other
    # process secret) and exfiltrate it via a header to their own webhook (audit
    # S-04). The built-in set below covers the secrets documented in
    # .env.example; add site-specific names with
    #   ALERTD_SECRET_REF_ALLOW=MY_TOKEN,OTHER_SECRET
    secret_ref_allow: str = ""

    # ── CORS ──────────────────────────────────────────────────
    # Comma-separated list of allowed origins. Empty = no CORS
    # middleware installed (proxy-only mode; the consumer Flask
    # service relays requests). Set e.g.
    #   ALERTD_CORS_ORIGINS=https://ops.example.com,https://admin.example.com
    # to allow direct browser → alertd calls.
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_cidr_list(self) -> list[str]:
        return [c.strip() for c in self.trusted_proxy_cidrs.split(",") if c.strip()]

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def _trusted_proxies_parse(cls, v: str) -> str:
        # Fail closed at startup: a wrong entry must not be skipped silently,
        # since login lockout, the wrong-key budget and address allowlists all
        # key on the client address this list decides (utils/client_ip.py).
        from .utils.client_ip import parse_trusted_proxies

        parse_trusted_proxies(v)
        return v

    @field_validator("docs_enabled", "metrics_require_auth", mode="before")
    @classmethod
    def _blank_is_auto(cls, v: object) -> object:
        # docker-compose passes these as ${VAR:-} (empty when unset); an empty
        # string isn't a valid bool, so treat blank as "auto" (None).
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def docs_enabled_effective(self) -> bool:
        # Auto: disable the interactive docs on a TLS/prod deploy (cookie_secure).
        return (not self.cookie_secure) if self.docs_enabled is None else self.docs_enabled

    @property
    def metrics_require_auth_effective(self) -> bool:
        # Auto: require a read-scoped key for /v1/metrics on a TLS/prod deploy.
        return self.cookie_secure if self.metrics_require_auth is None else self.metrics_require_auth

    def secret_ref_allowed(self, name: str) -> bool:
        """May a ``*_ref`` resolve the env var ``name``? The allowlist below,
        or any ``KLOPOT_SECRET_<NAME>`` — that prefix can only name a secret the
        operator put there on purpose (secrets.env), never a process secret
        such as ALERTD_DATABASE_URL (audit S-04 stays default-deny)."""
        return name in self.secret_ref_allow_set or bool(SECRET_REF_PREFIX_RE.fullmatch(name))

    @property
    def secret_ref_allow_set(self) -> frozenset[str]:
        # Built-in defaults (the secrets documented in .env.example) plus any
        # operator-supplied names. Default-deny: anything not here is refused.
        extra = {o.strip() for o in self.secret_ref_allow.split(",") if o.strip()}
        return _DEFAULT_SECRET_REF_ALLOW | extra


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton. Pydantic reads env once, then in-memory.

    Tests can override by clearing the cache:
        get_settings.cache_clear()
    """
    return Settings()
