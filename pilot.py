"""
the_vault_pilot_app/pilot.py

Unified Delivery, Telemetry & Curriculum Studio Layer for The Vault.
- Learning Portal: Pre/Post assessments, embedded video, student badges.
- Pilot Summary (Admin): Cross-cohort benchmarks, D-Index psychometrics.
- Curriculum Studio (CMS): Generates psychometrically guarded modules via Gemini
  and publishes directly to TheVault_CMS_Core.
"""
import os
import re
import sys
import random
import logging
import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from supabase import create_client, Client

# Add root directory to sys.path so Utils can be imported cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from Utils.vault_curriculum_prompts import VaultModuleSchema
    from Utils.generate_and_ingest import generate_vault_module, ingest_module_to_supabase
    STUDIO_AVAILABLE = True
except ImportError:
    STUDIO_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTS & CONFIG
# ---------------------------------------------------------------------------
CMS_TABLE_NAME         = "TheVault_CMS_Core"
ADMIN_PASSWORD         = "vault2026"
VIDEO_COMPLETE_RATIO   = 0.9     # 90% of video length = "Completed"
DEFAULT_VIDEO_LEN_SEC  = 85
DEFAULT_PILOT_ID       = "WIRAPIDS_12"
NY_TZ                  = pytz.timezone("US/Eastern")

NPS_RATINGS = [
    ("😴 Boring", 2),
    ("😐 Okay",   5),
    ("😎 Cool",   8),
    ("🔥 Fire",   9),
    ("🏆 Epic",  10),
]

YT_PATTERN = re.compile(
    r'(?:v=|\/([0-9A-Za-z_-]{11})|youtu\.be\/|\/shorts\/|\/embed\/)([0-9A-Za-z_-]{11})'
)

# ---------------------------------------------------------------------------
# PAGE CONFIG & STYLES
# ---------------------------------------------------------------------------
st.set_page_config(page_title="The Vault Platform", page_icon="⚡", layout="wide")

st.markdown("""
    
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SESSION STATE & COHORT ROUTING
# ---------------------------------------------------------------------------
SESSION_DEFAULTS = {
    "step":             "pre_test",
    "active_topic":     None,
    "start_time":       None,
    "nps_score":        None,
    "ans_pre1":         None,
    "ans_pre2":         None,
    "class_code":       "",
    "student_id":       "",
    "shuffled_pre":     None,
    "shuffled_post":    None,
    "active_pilot_id":  DEFAULT_PILOT_ID,
    "is_submitting":    False,
    "submission_done":  False,
    "completed_result": None,
    "studio_authed":    False,
}
for k, v in SESSION_DEFAULTS.items():
    st.session_state.setdefault(k, v)

# Override with URL parameter if passed (?pilot=...)
url_pilot = st.query_params.get("pilot")
if url_pilot:
    st.session_state.active_pilot_id = str(url_pilot)

# ---------------------------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------------------------

@st.cache_resource
def get_supabase_client() -> Client | None:
    """Connect to Supabase supporting nested, flat, and environment variable configurations."""
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
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


# ---------------------------------------------------------------------------
# DATA LOADING & PERSISTENCE
# ---------------------------------------------------------------------------

def _normalize_cms_df(df: pd.DataFrame) -> pd.DataFrame:
    """Map lowercase DB column names to PascalCase format."""
    col_map = {
        "topic": "Topic",
        "pilot_id": "Pilot_ID",
        "video_url": "Video_URL",
        "video_length_sec": "Video_Length_Sec",
        "pre_q1": "Pre_Q1",
        "pre_opt1": "Pre_Opt1",
        "pre_opt2": "Pre_Opt2",
        "pre_opt3": "Pre_Opt3",
        "pre_opt4": "Pre_Opt4",
        "pre_a1": "Pre_A1",
        "pre_q2": "Pre_Q2",
        "pre_opt1_q2": "Pre_Opt1_Q2",
        "pre_opt2_q2": "Pre_Opt2_Q2",
        "pre_opt3_q2": "Pre_Opt3_Q2",
        "pre_opt4_q2": "Pre_Opt4_Q2",
        "pre_a2": "Pre_A2",
        "post_q1": "Post_Q1",
        "post_opt1": "Post_Opt1",
        "post_opt2": "Post_Opt2",
        "post_opt3": "Post_Opt3",
        "post_opt4": "Post_Opt4",
        "post_a1": "Post_A1",
        "post_q2": "Post_Q2",
        "post_opt1_q2": "Post_Opt1_Q2",
        "post_opt2_q2": "Post_Opt2_Q2",
        "post_opt3_q2": "Post_Opt3_Q2",
        "post_opt4_q2": "Post_Opt4_Q2",
        "post_a2": "Post_A2",
    }
    return df.rename(columns=col_map)


@st.cache_data(ttl=60)
def load_cms_for_pilot(pilot_id: str) -> pd.DataFrame | None:
    """Fetch CMS curriculum rows filtered by pilot_id."""
    client = get_supabase_client()
    if not client:
        return None
    try:
        response = client.table(CMS_TABLE_NAME).select("*").eq("pilot_id", pilot_id).execute()
        if response.data and len(response.data) > 0:
            df = pd.DataFrame(response.data)
            return _normalize_cms_df(df)
        return None
    except Exception as e:
        logger.error(f"Failed to fetch CMS for pilot '{pilot_id}': {e}")
        return None


def load_logs() -> pd.DataFrame | None:
    """Fetch mastery logs from Supabase."""
    client = get_supabase_client()
    if not client:
        return None
    try:
        response = client.table("pilot_mastery_logs").select("*").order("created_at", desc=True).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            return df.rename(columns={
                "created_at": "Timestamp",
                "pilot_id":   "Pilot_ID",
                "class_code": "Class",
                "student_id": "Student",
                "topic":      "Topic",
                "pre_score":  "Pre_Score",
                "post_score": "Post_Score",
                "lift":       "Lift",
                "nps":        "NPS",
                "duration":   "Duration",
                "status":     "Status",
            })
        return None
    except Exception as e:
        logger.error(f"Supabase load error: {e}")
        return None


def append_log(record: dict) -> None:
    """Append or upsert one result row directly into Supabase with itemized telemetry."""
    client = get_supabase_client()
    if not client:
        raise RuntimeError("Supabase client is not connected.")

    payload = {
        "pilot_id":       str(st.session_state.active_pilot_id),
        "class_code":     str(record.get("Class", "")),
        "student_id":     str(record.get("Student", "")).strip().upper(),
        "topic":          str(record.get("Topic", "")),
        "pre_score":      int(record.get("Pre_Score", 0)),
        "post_score":     int(record.get("Post_Score", 0)),
        "lift":           int(record.get("Lift", 0)),
        "nps":            int(record.get("NPS", 0)),
        "duration":       int(record.get("Duration", 0)),
        "status":         str(record.get("Status", "Completed")),
    }

    if "Raw_Responses" in record and record["Raw_Responses"] is not None:
        payload["raw_responses"] = record["Raw_Responses"]

    try:
        client.table("pilot_mastery_logs").upsert(
            payload,
            on_conflict="pilot_id,student_id,topic"
        ).execute()
    except Exception as e:
        err_msg = str(e)
        if "23505" in err_msg or "unique_student_topic_per_pilot" in err_msg:
            logger.info("Duplicate submission caught gracefully.")
            return
        raise e


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def resolve_video_url(raw_url: str) -> str | None:
    """Return a clean YouTube watch URL, direct video link, or None."""
    raw_url = str(raw_url).strip()
    match = YT_PATTERN.search(raw_url)
    if match:
        video_id = match.group(1) or match.group(2)
        return f"https://www.youtube.com/watch?v={video_id}"
    if raw_url.startswith("http"):
        return raw_url
    return None


def build_shuffled_questions(row: pd.Series, stage: str) -> list[dict]:
    """Build and shuffle question pool for pre or post stage."""
    if stage == "pre":
        opts_q1 = [row.get("Pre_Opt1"), row.get("Pre_Opt2"), row.get("Pre_Opt3")]
        if pd.notna(row.get("Pre_Opt4")):
            opts_q1.append(row.get("Pre_Opt4"))
        opts_q1 = [str(o) for o in opts_q1 if pd.notna(o) and str(o).strip()]

        opts_q2 = [row.get("Pre_Opt1_Q2"), row.get("Pre_Opt2_Q2"), row.get("Pre_Opt3_Q2")]
        if pd.notna(row.get("Pre_Opt4_Q2")):
            opts_q2.append(row.get("Pre_Opt4_Q2"))
        opts_q2 = [str(o) for o in opts_q2 if pd.notna(o) and str(o).strip()]

        pool = [
            {"id": "q1", "text": str(row.get("Pre_Q1", "")), "options": random.sample(opts_q1, len(opts_q1))},
            {"id": "q2", "text": str(row.get("Pre_Q2", "")), "options": random.sample(opts_q2, len(opts_q2))},
        ]
    else:
        opts_q1 = [row.get("Post_Opt1"), row.get("Post_Opt2"), row.get("Post_Opt3")]
        if pd.notna(row.get("Post_Opt4")):
            opts_q1.append(row.get("Post_Opt4"))
        opts_q1 = [str(o) for o in opts_q1 if pd.notna(o) and str(o).strip()]

        opts_q2 = [row.get("Post_Opt1_Q2"), row.get("Post_Opt2_Q2"), row.get("Post_Opt3_Q2")]
        if pd.notna(row.get("Post_Opt4_Q2")):
            opts_q2.append(row.get("Post_Opt4_Q2"))
        opts_q2 = [str(o) for o in opts_q2 if pd.notna(o) and str(o).strip()]

        pool = [
            {"id": "q1", "text": str(row.get("Post_Q1", "")), "options": random.sample(opts_q1, len(opts_q1))},
            {"id": "q2", "text": str(row.get("Post_Q2", "")), "options": random.sample(opts_q2, len(opts_q2))},
        ]
    random.shuffle(pool)
    return pool


def score_answers(answers: dict, row: pd.Series, stage: str) -> int:
    """Calculate correct answers count."""
    if stage == "pre":
        return (
            (1 if str(answers.get("q1", "")).strip() == str(row.get("Pre_A1", "")).strip() else 0)
            + (1 if str(answers.get("q2", "")).strip() == str(row.get("Pre_A2", "")).strip() else 0)
        )
    return (
        (1 if str(answers.get("q1", "")).strip() == str(row.get("Post_A1", "")).strip() else 0)
        + (1 if str(answers.get("q2", "")).strip() == str(row.get("Post_A2", "")).strip() else 0)
    )


def render_mastery_badge(initials: str, lift: int) -> None:
    st.markdown(
        f'
