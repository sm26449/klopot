"""MQTT output validation and frozen broker defaults."""
from __future__ import annotations

import string
from typing import Any

from ..config import get_settings

TOPIC_FIELDS = frozenset({"type", "severity", "id", "instance", "channel"})


def validate_topic(topic: str) -> None:
    if not topic or any(c in topic for c in ("\x00", "+", "#")) or len(topic.encode("utf-8")) > 65535:
        raise ValueError("MQTT publish topic must be nonempty and contain no wildcards or NUL")


def validate_config(config: dict[str, Any]) -> None:
    qos = config.get("qos", 1)
    if isinstance(qos, bool) or not isinstance(qos, int) or qos not in (0, 1, 2):
        raise ValueError("MQTT qos must be 0, 1 or 2")
    for field in ("retain", "tls"):
        if field in config and not isinstance(config[field], bool):
            raise ValueError(f"MQTT {field} must be a boolean")
    port = config.get("port", 1883)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("MQTT port must be an integer between 1 and 65535")
    timeout = config.get("timeout_sec", 10)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or not 1 <= timeout <= 20:
        raise ValueError("MQTT timeout_sec must be between 1 and 20")
    host = config.get("host")
    if host is not None and (not isinstance(host, str) or not host.strip() or len(host) > 253 or any(c in host for c in ("/", "@", "\x00", " ", "\n", "\r"))):
        raise ValueError("MQTT host must be a hostname or IP without credentials")
    for key, default in (("topic_template", "klopot/notifications/{type}"),
                         ("availability_topic", "klopot/{instance}/outputs/{channel}/status"),
                         ("heartbeat_topic", "klopot/{instance}/outputs/{channel}/heartbeat")):
        template = config.get(key, default)
        if not isinstance(template, str) or len(template) > 2000:
            raise ValueError(f"MQTT {key} must be a topic template")
        if not template and key != "topic_template":
            continue
        try:
            for _, placeholder, spec, conversion in string.Formatter().parse(template):
                if placeholder is not None and (placeholder not in TOPIC_FIELDS or spec or conversion):
                    raise ValueError("unsupported topic placeholder")
            rendered = template.format_map(dict.fromkeys(TOPIC_FIELDS, "test"))
            validate_topic(rendered)
        except (KeyError, ValueError) as error:
            raise ValueError(f"MQTT {key}: invalid publish topic or placeholder") from error
    for key in ("availability_topic", "heartbeat_topic"):
        template = config.get(key)
        if template and any("{" + field + "}" in template for field in ("id", "type", "severity")):
            raise ValueError(f"MQTT {key} supports only instance/channel placeholders")
    if config.get("payload_template") is not None and not isinstance(config["payload_template"], str):
        raise ValueError("MQTT payload_template must be text")
    instance = config.get("instance_id")
    if instance is not None and (not isinstance(instance, str) or not instance or len(instance) > 128 or any(c in instance for c in ("/", "+", "#", "\x00"))):
        raise ValueError("MQTT instance_id must be a single nonempty topic level")


def freeze_defaults(config: dict[str, Any]) -> dict[str, Any]:
    """Freeze settings-backed destination before enqueue, just like explicit config."""
    result = dict(config)
    settings = get_settings()
    result.setdefault("host", settings.mqtt_host)
    result.setdefault("port", settings.mqtt_port)
    result.setdefault("instance_id", settings.mqtt_client_id)
    if "username" not in result and not result.get("username_ref"):
        result["username_ref"] = "ALERTD_MQTT_USERNAME"
    if "password" not in result and not result.get("password_ref"):
        result["password_ref"] = "ALERTD_MQTT_PASSWORD"
    return result
