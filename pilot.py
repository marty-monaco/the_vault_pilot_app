"""
the_vault_pilot_app/pilot.py

Student-facing delivery layer for The Vault.
Reads curriculum content from Supabase (with Google Sheets fallback), runs
pre/post assessments, embeds normalized video, collects NPS, and logs mastery data to Supabase.
"""
import os
import re
import random
import logging
import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTS & CONFIG
# ---------------------------------------------------------------------------
CMS_TABLE_NAME         = "TheVault_CMS_Core"
CMS_CSV_URL            = (
    "https://docs.google.com/spreadsheets/d/"
    "1sxxEyxjvicryUGJRMcd05Hcy6rIFLuXiTZPR_Mco7n8"
    "/export?format=csv&gid=0"
)
ADMIN_PASSWORD         = "vault2026"
VIDEO_COMPLETE_RATIO   = 0.9
DEFAULT_VIDEO_LEN_SEC  = 85
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
st.set_page_config(page_title="The Vault Pilot", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    div.stButton > button:first-child { border-radius: 10px; font-weight: bold; }
    .mastery-badge {
        background-color: #FFD700; color: #1A1A1A; padding: 20px;
        border-radius: 15px; text-align: center; border: 4px solid #B8860B;
        font-family: 'Courier New', Courier, monospace; margin-top: 20px;
    }
    .badge-initials { font-size: 40px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------------
SESSION_DEFAULTS = {
    "step":          "pre_test",
    "active_topic":  None,
    "start_time":    None,
    "nps_score":     None,
    "ans_pre1":      None,
    "ans_pre2":      None,
    "class_code":    "",
    "student_id":    "",
    "shuffled_pre":  None,
    "shuffled_post": None,
}
for k, v in SESSION_DEFAULTS.items():
    st.session_state.setdefault(k, v)

# ---------------------------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------------------------

@st.cache_resource
def get_supabase_client() -> Client | None:
    """Connect to Supabase supporting nested, flat, and environment variable configurations."""
    url, key = None, None

    # 1. Nested [supabase] section in secrets
    try:
        if "supabase" in st.secrets:
            url = st.secrets["supabase"].get("SUPABASE_URL")
            key = st.secrets["supabase"].get("SUPABASE_KEY")
    except Exception:
        pass

    # 2. Flat root keys in st.secrets
    if not url:
        try:
            url = st.secrets.get("SUPABASE_URL")
        except Exception:
            pass
    if not key:
        try:
            key = st.secrets.get("SUPABASE_KEY")
        except Exception:
            pass

    # 3. Environment variables fallback
    if not url:
        url = os.environ.get("SUPABASE_URL")
    if not key:
        key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        logger.error("Supabase URL or Key could not be resolved from secrets or environment.")
        return None

    try:
        return create_client(str(url).strip(), str(key).strip())
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None

st.write("DEBUG — record being sent:", record)
client = get_supabase_client()
st.write("DEBUG — Supabase client:", "Connected" if client else "NOT CONNECTED")
try:
    response = client.table("pilot_mastery_logs").insert({
        "class_code": str(record["Class"]),
        "student_id": str(record["Student"]),
        "topic":      str(record["Topic"]),
        "pre_score":  int(record["Pre_Score"]),
        "post_score": int(record["Post_Score"]),
        "lift":       int(record["Lift"]),
        "nps":        int(record["NPS"]),
        "duration":   int(record["Duration"]),
        "status":     str(record["Status"]),
    }).execute()
    st.write("DEBUG — Supabase response:", response)
except Exception as e:
    st.write("DEBUG — Supabase error:", str(e))
    
def append_log(record: dict) -> None:
    """Append one result row directly into Supabase."""
    client = get_supabase_client()
    if not client:
        raise RuntimeError("Supabase client is not connected. Check your SUPABASE_URL and SUPABASE_KEY secrets.")

    payload = {
        "class_code": str(record["Class"]),
        "student_id": str(record["Student"]),
        "topic":      str(record["Topic"]),
        "pre_score":  int(record["Pre_Score"]),
        "post_score": int(record["Post_Score"]),
        "lift":       int(record["Lift"]),
        "nps":        int(record["NPS"]),
        "duration":   int(record["Duration"]),
        "status":     str(record["Status"]),
    }
    response = client.table("pilot_mastery_logs").insert(payload).execute()
    if not response.data:
        raise RuntimeError("Supabase accepted request but returned no data.")


def load_logs() -> pd.DataFrame | None:
    """Fetch mastery logs from Supabase."""
    client = get_supabase_client()
    if not client:
        st.error("⚠️ Supabase credentials not found or client failed to connect.")
        return None
    try:
        response = client.table("pilot_mastery_logs").select("*").order("created_at", desc=True).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            return df.rename(columns={
                "created_at": "Timestamp",
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


supabase = get_supabase_client()

# ---------------------------------------------------------------------------
# DATA LOADING & PERSISTENCE
# ---------------------------------------------------------------------------

def _normalize_cms_df(df: pd.DataFrame) -> pd.DataFrame:
    """Map lowercase DB column names to the PascalCase format used across UI."""
    col_map = {
        "topic": "Topic",
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
def load_cms() -> pd.DataFrame | None:
    """Load CMS stories from Supabase (TheVault_CMS_Core) with Google Sheets fallback."""
    # 1. Attempt load from Supabase
    if supabase:
        try:
            response = supabase.table(CMS_TABLE_NAME).select("*").execute()
            if response.data and len(response.data) > 0:
                df = pd.DataFrame(response.data)
                return _normalize_cms_df(df)
            else:
                logger.info(f"Supabase '{CMS_TABLE_NAME}' empty. Falling back to Google Sheet.")
        except Exception as e:
            logger.warning(f"Supabase CMS fetch error on '{CMS_TABLE_NAME}': {e}. Falling back to Google Sheet.")

    # 2. Fallback to Google Sheets CSV export
    try:
        df = pd.read_csv(CMS_CSV_URL)
        if not df.empty:
            return _normalize_cms_df(df)
    except Exception as e:
        logger.error(f"Google Sheet fetch failed: {e}")

    return None

    # 2. Fallback to Google Sheets CSV export
    try:
        df = pd.read_csv(CMS_CSV_URL)
        if not df.empty:
            return _normalize_cms_df(df)
    except Exception as e:
        logger.error(f"Google Sheet fetch failed: {e}")

    return None


def load_logs() -> pd.DataFrame | None:
    """Fetch mastery logs from Supabase."""
    if not supabase:
        st.error("⚠️ Supabase credentials not found in secrets.")
        return None
    try:
        response = supabase.table("pilot_mastery_logs").select("*").order("created_at", desc=True).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            return df.rename(columns={
                "created_at": "Timestamp",
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
    """Append one result row directly into Supabase."""
    if not supabase:
        raise RuntimeError("Supabase client is not connected.")

    payload = {
        "class_code": str(record["Class"]),
        "student_id": str(record["Student"]),
        "topic":      str(record["Topic"]),
        "pre_score":  int(record["Pre_Score"]),
        "post_score": int(record["Post_Score"]),
        "lift":       int(record["Lift"]),
        "nps":        int(record["NPS"]),
        "duration":   int(record["Duration"]),
        "status":     str(record["Status"]),
    }
    response = supabase.table("pilot_mastery_logs").insert(payload).execute()
    if not response.data:
        raise RuntimeError("Failed to insert record into Supabase.")

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
            {"id": "q1", "text": row["Pre_Q1"], "options": random.sample(opts_q1, len(opts_q1))},
            {"id": "q2", "text": row["Pre_Q2"], "options": random.sample(opts_q2, len(opts_q2))},
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
            {"id": "q1", "text": row["Post_Q1"], "options": random.sample(opts_q1, len(opts_q1))},
            {"id": "q2", "text": row["Post_Q2"], "options": random.sample(opts_q2, len(opts_q2))},
        ]
    random.shuffle(pool)
    return pool


def score_answers(answers: dict, row: pd.Series, stage: str) -> int:
    """Calculate correct answers count."""
    if stage == "pre":
        return (
            (1 if answers.get("q1") == str(row["Pre_A1"]).strip() else 0)
            + (1 if answers.get("q2") == str(row["Pre_A2"]).strip() else 0)
        )
    return (
        (1 if answers.get("q1") == str(row["Post_A1"]).strip() else 0)
        + (1 if answers.get("q2") == str(row["Post_A2"]).strip() else 0)
    )


def render_mastery_badge(initials: str, lift: int) -> None:
    st.markdown(
        f'<div class="mastery-badge">'
        f'<div class="badge-initials">{initials.upper()}</div>'
        f'CERTIFIED MASTER<br>LIFT: +{lift}'
        f'</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# ADMIN PANEL
# ---------------------------------------------------------------------------

def render_admin() -> None:
    st.title("🔐 Admin Dashboard (Supabase Real-Time)")
    pw = st.text_input("Access Key", type="password")

    if not pw:
        return
    if pw != ADMIN_PASSWORD:
        st.error("Incorrect access key.")
        return

    st.success("Access granted.")
    df_logs = load_logs()

    if df_logs is None or df_logs.empty:
        st.info("No submissions found in Supabase yet.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Learners",     len(df_logs))
    c2.metric("Avg Lift",     f"+{df_logs['Lift'].mean():.2f}")
    c3.metric("Avg Duration", f"{int(df_logs['Duration'].mean())}s")
    c4.metric("Avg NPS",      f"{df_logs['NPS'].mean():.1f}")

    st.dataframe(df_logs.sort_values("Timestamp", ascending=False), use_container_width=True)
    st.download_button(
        label="📥 Download Supabase Pilot CSV",
        data=df_logs.to_csv(index=False),
        file_name=f"vault_pilot_supabase_{datetime.now(NY_TZ).strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

# ---------------------------------------------------------------------------
# LEARNING PORTAL — STEP 1: PRE-TEST
# ---------------------------------------------------------------------------

def render_pre_test(row: pd.Series) -> None:
    st.title(f"🔍 Pre-Assessment: {st.session_state.active_topic}")

    if st.session_state.shuffled_pre is None:
        st.session_state.shuffled_pre = build_shuffled_questions(row, "pre")

    p_ans = {}
    for idx, q in enumerate(st.session_state.shuffled_pre):
        p_ans[q["id"]] = st.radio(
            f"Question {idx + 1}: {q['text']}",
            q["options"],
            index=None,
            key=f"p_{q['id']}",
        )

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        class_code = st.text_input("Class Code")
    with c2:
        student_id = st.text_input("Your Initials")

    if st.button("ENTER THE VAULT ⚡", use_container_width=True, type="primary"):
        if not class_code or not student_id:
            st.warning("Please enter your Class Code and Initials.")
        elif p_ans.get("q1") is None or p_ans.get("q2") is None:
            st.warning("Please answer both questions before proceeding.")
        else:
            st.session_state.update({
                "class_code": class_code,
                "student_id": student_id,
                "ans_pre1":   p_ans["q1"],
                "ans_pre2":   p_ans["q2"],
                "start_time": datetime.now(NY_TZ),
                "step":       "vault_content",
            })
            st.rerun()

# ---------------------------------------------------------------------------
# LEARNING PORTAL — STEP 2: VIDEO + PULSE CHECK
# ---------------------------------------------------------------------------

def render_vault_content(row: pd.Series) -> None:
    st.title(f"🎬 {st.session_state.active_topic}")

    video_url = resolve_video_url(str(row.get("Video_URL", "")))
    if video_url:
        st.video(video_url)
    else:
        st.warning("⚠️ Video URL missing or invalid for this topic.")

    st.divider()
    st.write("### 🧠 Pulse Check")

    if st.session_state.shuffled_post is None:
        st.session_state.shuffled_post = build_shuffled_questions(row, "post")

    pst_ans = {}
    for idx, q in enumerate(st.session_state.shuffled_post):
        pst_ans[q["id"]] = st.radio(
            f"Question {idx + 1}: {q['text']}",
            q["options"],
            index=None,
            key=f"pst_{q['id']}",
        )

    st.divider()
    st.write("### ⚡ Rate this Vault Story")
    rating_cols = st.columns(len(NPS_RATINGS))
    for col, (label, val) in zip(rating_cols, NPS_RATINGS):
        if col.button(label, use_container_width=True):
            st.session_state.nps_score = val

    if st.session_state.nps_score is not None:
        st.success(f"Selected Rating: {st.session_state.nps_score}/10")

    if st.button("LOG MASTERY & FINISH 🚀", use_container_width=True, type="primary"):
        if pst_ans.get("q1") is None or pst_ans.get("q2") is None:
            st.error("Please answer both Pulse Check questions.")
        elif st.session_state.nps_score is None:
            st.error("Please select a rating before finishing.")
        else:
            _submit_results(row, pst_ans)


def _submit_results(row: pd.Series, pst_ans: dict) -> None:
    """Score, persist to Supabase, and render results."""
    now     = datetime.now(NY_TZ)
    elapsed = (now - st.session_state.start_time).total_seconds()

    pre_answers = {"q1": st.session_state.ans_pre1, "q2": st.session_state.ans_pre2}
    s_pre  = score_answers(pre_answers, row, "pre")
    s_post = score_answers(pst_ans, row, "post")
    lift   = s_post - s_pre

    video_len = float(row.get("Video_Length_Sec", DEFAULT_VIDEO_LEN_SEC))
    status    = "Completed" if elapsed >= video_len * VIDEO_COMPLETE_RATIO else "Skimmed"

    record = {
        "Class":      st.session_state.class_code,
        "Student":    st.session_state.student_id,
        "Topic":      st.session_state.active_topic,
        "Pre_Score":  s_pre,
        "Post_Score": s_post,
        "Lift":       lift,
        "NPS":        st.session_state.nps_score,
        "Duration":   int(elapsed),
        "Status":     status,
    }

    try:
        append_log(record)
    except Exception as e:
        st.error(f"❌ Failed to persist results to Supabase: {e}")
        return

    if status == "Completed":
        st.balloons()
        render_mastery_badge(st.session_state.student_id, lift)
    else:
        st.warning(
            f"Mastery logged to cloud! (Lift: {lift:+d}) "
            "Try watching the full video next time to earn a badge."
        )

# ---------------------------------------------------------------------------
# LEARNING PORTAL — TOPIC SELECTOR
# ---------------------------------------------------------------------------

def render_learning_portal(df_cms: pd.DataFrame) -> None:
    topic_list = df_cms["Topic"].tolist()

    st.markdown("### 🏛️ Select Your Vault Story")

    n_cols = 3
    for i in range(0, len(topic_list), n_cols):
        grid_cols = st.columns(n_cols)
        for j, t in enumerate(topic_list[i:i + n_cols]):
            if grid_cols[j].button(f"📖 {t}", use_container_width=True):
                st.session_state.update({
                    **SESSION_DEFAULTS,
                    "active_topic": t,
                })
                st.rerun()

    st.divider()

    if not st.session_state.active_topic:
        st.info("Select a story above to begin.")
        st.stop()

    topic_rows = df_cms[df_cms["Topic"] == st.session_state.active_topic]
    if topic_rows.empty:
        st.error(f"Topic '{st.session_state.active_topic}' not found in CMS.")
        st.stop()

    row = topic_rows.iloc[0]

    if st.session_state.step == "pre_test":
        render_pre_test(row)
    elif st.session_state.step == "vault_content":
        render_vault_content(row)

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    st.sidebar.title("⚡ THE VAULT")
    nav = st.sidebar.radio("Navigation", ["Learning Portal", "Pilot Summary (Admin)"])

    if nav == "Pilot Summary (Admin)":
        render_admin()
        return

    df_cms = load_cms()
    if df_cms is None or df_cms.empty:
        st.error("❌ Could not load CMS content from Supabase or Google Sheets. Check database table and Sheet sharing permissions.")
        st.stop()

    render_learning_portal(df_cms)


if __name__ == "__main__":
    main()
