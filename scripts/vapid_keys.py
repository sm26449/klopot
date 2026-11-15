#!/usr/bin/env python3
"""Print a fresh VAPID key pair for the Web Push channel (docs/WEB_PUSH.md).

    .venv/bin/python scripts/vapid_keys.py            # on the host, from the repo
    docker compose exec alertd python scripts/vapid_keys.py   # in the container

Put the private key in secrets.env as KLOPOT_SECRET_VAPID_PRIVATE, restart, and
point the push channel's vapid_private_ref at that name. The public key is
derived from it (GET /v1/push/config) — it is printed only for reference.
Rotating the key invalidates every registered device: each one has to enable
notifications again.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def main() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    private = _b64(key.private_numbers().private_value.to_bytes(32, "big"))
    public = _b64(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))
    print("# secrets.env (never commit this)")
    print(f"KLOPOT_SECRET_VAPID_PRIVATE={private}")
    print(f"# public key (derived automatically, for reference): {public}")


if __name__ == "__main__":
    main()
