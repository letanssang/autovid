from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_loaded = False


def load_env() -> None:
    """Load .env from the repo root once. Safe to call from every entrypoint
    (cli/main.py, dashboard/server.py) and from adapters that need a key —
    idempotent, so it never re-reads or overwrites already-loaded values."""
    global _loaded
    if _loaded:
        return
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
    _loaded = True


def require_key(var_name: str, provider_id: str, config_hint: str = "") -> str:
    """Fetch an env var or raise with a message naming the missing var, the
    provider that needs it, and where to fix it — see AutoVid plan/phase-1."""
    load_env()
    value = os.environ.get(var_name)
    if not value:
        hint = f" ({config_hint})" if config_hint else ""
        raise RuntimeError(
            f"Thiếu {var_name} (cần bởi provider '{provider_id}'{hint}). "
            f"Thêm vào file .env ở thư mục gốc repo."
        )
    return value
