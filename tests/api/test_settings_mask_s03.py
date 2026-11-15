"""S-03: the /v1/settings DB-URL mask must hide the whole password, including
one containing URL metacharacters like '/'. The old regex stopped at the '/',
leaking the password tail to a read-scoped caller."""
from __future__ import annotations

from app.api.v1.settings import _mask_db_url


def test_masks_simple_password():
    assert _mask_db_url("mysql+aiomysql://u:secret@host:3306/db") == \
        "mysql+aiomysql://u:***@host:3306/db"


def test_masks_password_containing_slash():
    masked = _mask_db_url("mysql+aiomysql://u:pa/ss@host:3306/db")
    assert "pa/ss" not in masked
    assert "ss@host" not in masked
    assert masked == "mysql+aiomysql://u:***@host:3306/db"


def test_no_password_is_unchanged_host():
    masked = _mask_db_url("sqlite+aiosqlite:///./alertd.db")
    assert "://" in masked


def test_unparseable_falls_back_to_mask():
    assert _mask_db_url("not a url") == "***"
