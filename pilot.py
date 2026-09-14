"""
the_vault_pilot_app/pilot.py

Master Entry Point & Router for The Vault.
Delegates views to modular components in the views/ package.
"""
import os
import sys
import hmac
import logging
import streamlit as st
import pandas as pd
from supabase import create_client, Client

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from views.student_portal import render_student_portal
from views.admin_analytics import render_admin_analytics
from views.curriculum_studio import render_curriculum_studio

logger = logging.getLogger("TheVault")

CMS_TABLE_NAME   = "TheVault_CMS_Core"
DEFAULT_PILOT_ID = "WIRAPIDS_12"

st.set_page_config(page_title="The Vault Platform", page_icon="⚡", layout="wide")

st.markdown("""
    
""", unsafe_allow_html=True)

# Session State Setup
SESSION_DEFAULTS = {
    "active_pilot_id":  DEFAULT_PILOT_ID,
    "admin_authed":     False,
    "studio_authed":    False,
}
for k, v in SESSION_DEFAULTS.items():
    st.session_state.setdefault(k, v)

# Check query parameter overrides
url_pilot = st.query_params.get("pilot")
if url_pilot:
    st.session_state.active_pilot_id = str(url_pilot)


@st.cache_resource
def get_supabase_client() -> Client | None:
    url, key = None, None
    try:
        if "supabase" in st.secrets:
            url = st.secrets["supabase"].get("SUPABASE_URL")
            key = st.secrets["supabase"].get("SUPABASE_KEY")
    except Exception:
        pass

    if not url:
        url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    if not key:
        key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")

    if not url or not key:
        logger.warning("Supabase credentials not found in secrets.")
        return None

    try:
        return create_client(str(url).strip(), str(key).strip())
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        return None


def verify_admin_password(candidate_pw: str) -> bool:
    configured = st.secrets.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD") or "vault2026"
    return hmac.compare_digest(candidate_pw.strip(), configured.strip())


@st.cache_data(ttl=60)
def load_cms_for_pilot(pilot_id: str) -> pd.DataFrame | None:
    client = get_supabase_client()
    if not client:
        return None
    try:
        res = client.table(CMS_TABLE_NAME).select("*").eq("pilot_id", pilot_id).execute()
        if res.data:
            return pd.DataFrame(res.data)
        return None
    except Exception as e:
        logger.error(f"Error loading CMS for pilot '{pilot_id}': {e}")
        return None


def main():
    client = get_supabase_client()
    st.sidebar.title("⚡ THE VAULT")

    if client:
        st.sidebar.success("⚡ Database: Connected")
    else:
        st.sidebar.error("⚠️ Database: Disconnected")

    new_pilot = st.sidebar.text_input("Cohort ID:", value=st.session_state.active_pilot_id)
    if new_pilot != st.session_state.active_pilot_id:
        st.session_state.active_pilot_id = new_pilot
        st.session_state.pop("active_topic", None)
        st.rerun()

    nav = st.sidebar.radio("Navigation", ["Learning Portal", "Pilot Summary (Admin)", "Curriculum Studio (CMS)"])

    if nav == "Pilot Summary (Admin)":
        render_admin_analytics(client, verify_admin_password)
    elif nav == "Curriculum Studio (CMS)":
        render_curriculum_studio(client, verify_admin_password)
    else:
        df_cms = load_cms_for_pilot(st.session_state.active_pilot_id)
        if df_cms is None or df_cms.empty:
            st.warning(f"⚠️ No topics found for Cohort '{st.session_state.active_pilot_id}'.")
            st.stop()
        render_student_portal(df_cms, client)


if __name__ == "__main__":
    main()
