from __future__ import annotations

import streamlit as st
from supabase_client import get_supabase

_PARAM = "sid"   # URL query param name


# ── Session helpers ────────────────────────────────────────────────────────────

def get_user() -> dict | None:
    return st.session_state.get("user")


def is_logged_in() -> bool:
    return get_user() is not None


def logout():
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass
    st.query_params.clear()
    for key in ["user", "access_token", "refresh_token"]:
        st.session_state.pop(key, None)
    st.rerun()


def _save_session(user, session):
    st.session_state["user"]          = {"id": user.id, "email": user.email}
    st.session_state["access_token"]  = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    # Persist refresh token in URL — survives hard refresh natively
    st.query_params[_PARAM] = session.refresh_token


def _restore_session():
    """Try restoring session from URL param on page reload."""
    if st.session_state.get("user"):
        return
    token = st.query_params.get(_PARAM)
    if not token:
        return
    try:
        res = get_supabase().auth.refresh_session(token)
        if res and res.user:
            st.session_state["user"]          = {"id": res.user.id, "email": res.user.email}
            st.session_state["access_token"]  = res.session.access_token
            st.session_state["refresh_token"] = res.session.refresh_token
            st.query_params[_PARAM] = res.session.refresh_token
    except Exception:
        st.query_params.clear()


# ── Auth page UI ───────────────────────────────────────────────────────────────

def show_auth_page():
    """Blocks with st.stop() until the user is logged in."""

    _restore_session()
    if is_logged_in():
        return

    st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stHeader"]  { background: transparent !important; }
    .auth-card {
        background: #161B27;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 20px;
        padding: 48px 40px;
        max-width: 440px;
        margin: 60px auto 0 auto;
        box-shadow: 0 24px 64px rgba(0,0,0,0.4);
    }
    .auth-logo {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #3B82F6, #8B5CF6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 4px;
    }
    .auth-tagline {
        text-align: center;
        color: #64748B;
        font-size: 0.9rem;
        margin-bottom: 32px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="auth-card">', unsafe_allow_html=True)
    st.markdown('<div class="auth-logo">JobAgent AI</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="auth-tagline">Find your next role — powered by AI</div>',
        unsafe_allow_html=True,
    )

    tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

    # ── Login ──────────────────────────────────────────────────────────────────
    with tab_login:
        with st.form("form_login"):
            email    = st.text_input("Email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Login", use_container_width=True,
                                              type="primary")
        if submitted:
            if not email or not password:
                st.error("Please enter your email and password.")
            else:
                try:
                    res = get_supabase().auth.sign_in_with_password({
                        "email": email, "password": password
                    })
                    _save_session(res.user, res.session)
                    st.rerun()
                except Exception as e:
                    msg = str(e).lower()
                    if "invalid" in msg or "credentials" in msg:
                        st.error("Incorrect email or password.")
                    else:
                        st.error(f"Login failed: {e}")

    # ── Sign Up ────────────────────────────────────────────────────────────────
    with tab_signup:
        with st.form("form_signup"):
            new_email = st.text_input("Email", placeholder="you@example.com")
            new_pass  = st.text_input("Password", type="password",
                                      placeholder="Min 6 characters")
            new_pass2 = st.text_input("Confirm Password", type="password",
                                      placeholder="Repeat password")
            submitted = st.form_submit_button("Create Account", use_container_width=True,
                                              type="primary")
        if submitted:
            if not new_email or not new_pass or not new_pass2:
                st.error("Please fill in all fields.")
            elif new_pass != new_pass2:
                st.error("Passwords do not match.")
            elif len(new_pass) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                try:
                    res = get_supabase().auth.sign_up({
                        "email": new_email, "password": new_pass
                    })
                    if res.user and res.session:
                        _save_session(res.user, res.session)
                        st.rerun()
                    else:
                        st.info("Check your email to confirm your account, then log in.")
                except Exception as e:
                    msg = str(e).lower()
                    if "already" in msg:
                        st.error("An account with this email already exists.")
                    else:
                        st.error(f"Sign up failed: {e}")

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()
