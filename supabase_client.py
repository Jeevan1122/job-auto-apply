from __future__ import annotations

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY

_client: Client | None = None        # anon key — for auth
_admin_client: Client | None = None  # service role — for data operations


def get_supabase() -> Client:
    """Anon key client — used for login/signup/session."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def get_admin_supabase() -> Client:
    """Service role client — bypasses RLS, used for server-side data ops.
    Always filter by user_id manually when using this client."""
    global _admin_client
    if _admin_client is None:
        key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
        if not SUPABASE_URL or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
        _admin_client = create_client(SUPABASE_URL, key)
    return _admin_client
