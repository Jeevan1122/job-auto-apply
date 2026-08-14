from __future__ import annotations

import os

from supabase import create_client, Client

_client: Client | None = None        # anon key — for auth
_admin_client: Client | None = None  # service role — for data operations


def _keys() -> tuple[str, str, str]:
    """Read keys lazily so Streamlit secrets are already injected into env."""
    return (
        os.environ.get("SUPABASE_URL", ""),
        os.environ.get("SUPABASE_KEY", ""),
        os.environ.get("SUPABASE_SERVICE_KEY", ""),
    )


def get_supabase() -> Client:
    """Anon key client — used for login/signup/session."""
    global _client
    if _client is None:
        url, anon, _ = _keys()
        if not url or not anon:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")
        _client = create_client(url, anon)
    return _client


def get_admin_supabase() -> Client:
    """Service role client — bypasses RLS, used for server-side data ops.
    Always filter by user_id manually when using this client."""
    global _admin_client
    if _admin_client is None:
        url, anon, service = _keys()
        key = service or anon
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
        _admin_client = create_client(url, key)
    return _admin_client
