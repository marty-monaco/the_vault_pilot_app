"""
the_vault_pilot_app/pilot.py

Student-facing delivery layer for The Vault.
Reads curriculum content from a public Google Sheet (CMS), presents
pre/post assessments with randomised option ordering, embeds the video,
collects NPS ratings, and logs mastery data to a local CSV.
"""
import os
import re
import random
import logging
import streamlit as st
import pandas as pd
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
CMS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1sxxEyxjvicryUGJRMcd05Hcy6rIFLuXiTZPR_Mco7n8"
    "/export?format=csv&gid=0"
)
DATA_FILE              = os.path.join(os.getcwd(), "vault_mastery_logs.csv")
ADMIN_PASSWORD         = "vault2026"
VIDEO_COMPLETE_RATIO   = 0.9     # 90% of video length = "Completed"
DEFAULT_VIDEO_LEN_SEC  = 85
NY_TZ                  = pytz.timezone("US/Eastern")

NPS_RATINGS = [
    ("😴 Boring", 2),
    ("😐 Okay",   5),
    ("😎 Cool",   8),
    ("🔥 Fire",   9),
    ("🏆 Epic",  10),
]

# YouTube URL pattern — handles watch, shorts, share, and embed links
YT_PATTERN = re.compile(
    r'(?:v=|youtu\.be\/|\/shorts\/|\/embed\/)([0-9A-Za-z_-]{11})'
)

LOG_COLUMNS = [
    "Timestamp", "Class", "Student", "Topic",
    "Pre_Score", "Post_Score", "Lift", "NPS", "Duration", "Status",
]

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
# DATA LOADING
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_cms() -> pd.DataFrame | None:
    """Load CMS content from the public Google Sheet."""
    try:
        df = pd.read_csv(CMS_CSV_URL)
        if df.empty:
            logger.warning("CMS sheet loaded but contains no rows.")
            return None
        return df
    except Exception as e:
        logger.error("CMS load failed: %s", e)
        return None


def load_logs() -> pd.DataFrame | None:
    """Load the local mastery log CSV if it exists."""
    if not os.path.exists(DATA_FILE):
        return None
    try:
        df = pd.read_csv(DATA_FILE)
        return df if not df.empty else None
    except Exception as e:
        st.error(f"Failed to read log file: {e}")
        return None


def append_log(record: dict) -> None:
    """Append one result row to the local CSV, writing headers if needed."""
    pd.DataFrame([record]).to_csv(
        DATA_FILE,
        mode="a",
        header=not os.path.exists(DATA_FILE),
        index=False,
        columns=LOG_COLUMNS,
    )

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def resolve_video_url(raw_url: str) -> str | None:
    """Return a clean YouTube watch URL, a direct URL, or None if invalid."""
    raw_url = raw_url.strip()
    match = YT_PATTERN.search(raw_url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    if raw_url.startswith("http"):
        return raw_url
    return None


def build_shuffled_questions(row: pd.Series, stage: str) -> list[dict]:
    """Build and shuffle question pool for pre or post stage.

    Args:
        row:   CMS row for the active topic.
        stage: 'pre' or 'post'

    Returns:
        List of 2 question dicts with shuffled options, order randomised.
    """
    if stage == "pre":
        pool = [
            {
                "id": "q1",
                "text": row["Pre_Q1"],
                "options": random.sample(
                    [row["Pre_Opt1"], row["Pre_Opt2"], row["Pre_Opt3"]], 3
                ),
            },
            {
                "id": "q2",
                "text": row["Pre_Q2"],
                "options": random.sample(
                    [row["Pre_Opt1_Q2"], row["Pre_Opt2_Q2"], row["Pre_Opt3_Q2"]], 3
                ),
            },
        ]
    else:
        pool = [
            {
                "id": "q1",
                "text": row["Post_Q1"],
                "options": random.sample(
                    [row["Post_Opt1"], row["Post_Opt2"], row["Post_Opt3"]], 3
                ),
            },
            {
                "id": "q2",
                "text": row["Post_Q2"],
                "options": random.sample(
                    [row["Post_Opt1_Q2"], row["Post_Opt2_Q2"], row["Post_Opt3_Q2"]], 3
                ),
            },
        ]
    random.shuffle(pool)
    return pool


def score_answers(answers: dict, row: pd.Series, stage: str) -> int:
    """Return number of correct answers (0, 1, or 2) for pre or post stage."""
    if stage == "pre":
        return (
            (1 if answers.get("q1") == row["Pre_A1"] else 0)
            + (1 if answers.get("q2") == row["Pre_A2"] else 0)
        )
    return (
        (1 if answers.get("q1") == row["Post_A1"] else 0)
        + (1 if answers.get("q2") == row["Post_A2"] else 0)
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
    st.title("🔐 Admin Dashboard")
    pw = st.text_input("Access Key", type="password")

    if not pw:
        return
    if pw != ADMIN_PASSWORD:
        st.error("Incorrect access key.")
        return

    st.success("Access granted.")
    df_logs = load_logs()

    if df_logs is None:
        st.info("No submissions yet. Logs will appear here after the first student completes a story.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Learners",     len(df_logs))
    c2.metric("Avg Lift",     f"+{df_logs['Lift'].mean():.2f}")
    c3.metric("Avg Duration", f"{int(df_logs['Duration'].mean())}s")
    c4.metric("Avg NPS",      f"{df_logs['NPS'].mean():.1f}")

    st.dataframe(df_logs.sort_values("Timestamp", ascending=False), use_container_width=True)
    st.download_button(
        label="📥 Download Pilot CSV",
        data=df_logs.to_csv(index=False),
        file_name=f"vault_pilot_{datetime.now(NY_TZ).strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

# ---------------------------------------------------------------------------
# LEARNING PORTAL — STEP 1: PRE-TEST
# ---------------------------------------------------------------------------

def render_pre_test(row: pd.Series) -> None:
    st.title(f"🔍 Pre-Assessment: {st.session_state.active_topic}")

    # Initialise shuffled questions once per topic selection
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

    # Initialise shuffled post questions once
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
    """Score, log, and render the mastery result."""
    now     = datetime.now(NY_TZ)
    elapsed = (now - st.session_state.start_time).total_seconds()

    pre_answers = {"q1": st.session_state.ans_pre1, "q2": st.session_state.ans_pre2}
    s_pre  = score_answers(pre_answers, row, "pre")
    s_post = score_answers(pst_ans, row, "post")
    lift   = s_post - s_pre

    video_len = float(row.get("Video_Length_Sec", DEFAULT_VIDEO_LEN_SEC))
    status    = "Completed" if elapsed >= video_len * VIDEO_COMPLETE_RATIO else "Skimmed"

    record = {
        "Timestamp":  now.strftime("%Y-%m-%d %H:%M:%S"),
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
        st.error(f"❌ Failed to save results: {e}")
        return

    if status == "Completed":
        st.balloons()
        render_mastery_badge(st.session_state.student_id, lift)
    else:
        st.warning(
            f"Mastery logged! (Lift: {lift:+d}) "
            "Try watching the full video next time to earn a badge."
        )

# ---------------------------------------------------------------------------
# LEARNING PORTAL — TOPIC SELECTOR
# ---------------------------------------------------------------------------

def render_learning_portal(df_cms: pd.DataFrame) -> None:
    topic_list = df_cms["Topic"].tolist()

    st.markdown("### 🏛️ Select Your Vault Story")

    # Render topics in a 3-column grid — scales to any number of topics
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
    if df_cms is None:
        st.error("❌ Could not load CMS content. Check the Google Sheet URL and sharing settings.")
        st.stop()

    render_learning_portal(df_cms)


main()
