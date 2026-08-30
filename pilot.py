"""
the_vault_pilot_app/pilot.py

Multi-Pilot Student Delivery & Telemetry Layer for The Vault.
Reads curriculum scoped by pilot_id from Supabase, delivers assessments,
embeds video, and records student telemetry to Supabase.
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
ADMIN_PASSWORD         = "vault2026"
VIDEO_COMPLETE_RATIO   = 0.9     # 90% of video length = "Completed"
DEFAULT_VIDEO_LEN_SEC  = 85
DEFAULT_PILOT_ID       = "CRIM171"
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
# SESSION STATE & COHORT ROUTING
# ---------------------------------------------------------------------------
SESSION_DEFAULTS = {
    "step":            "pre_test",
    "active_topic":    None,
    "start_time":      None,
    "nps_score":       None,
    "ans_pre1":        None,
    "ans_pre2":        None,
    "class_code":      "",
    "student_id":      "",
    "shuffled_pre":    None,
    "shuffled_post":   None,
    "active_pilot_id": DEFAULT_PILOT_ID,
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
    """Append one result row directly into Supabase with itemized telemetry."""
    client = get_supabase_client()
    if not client:
        raise RuntimeError("Supabase client is not connected.")

    payload = {
        "pilot_id":       str(st.session_state.active_pilot_id),
        "class_code":     str(record.get("Class", "")),
        "student_id":     str(record.get("Student", "")),
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

    response = client.table("pilot_mastery_logs").insert(payload).execute()
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
        f'<div class="mastery-badge">'
        f'<div class="badge-initials">{initials.upper()}</div>'
        f'CERTIFIED MASTER<br>LIFT: +{lift}'
        f'</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# ADMIN ANALYTICS HELPERS
# ---------------------------------------------------------------------------

def compute_cohort_benchmarks(df_logs: pd.DataFrame) -> pd.DataFrame:
    """Generate side-by-side comparative KPI table across all cohorts."""
    rows = []
    for cohort, group in df_logs.groupby("Pilot_ID"):
        total_students = len(group)
        completed_count = len(group[group["Status"] == "Completed"])
        completion_rate = (completed_count / total_students * 100) if total_students > 0 else 0.0
        
        rows.append({
            "Cohort ID": str(cohort),
            "Learners": total_students,
            "Avg Pre-Score": round(group["Pre_Score"].mean(), 2),
            "Avg Post-Score": round(group["Post_Score"].mean(), 2),
            "Avg Lift": f"+{group['Lift'].mean():.2f}",
            "Completion Rate": f"{completion_rate:.1f}%",
            "Avg Duration (s)": int(group["Duration"].mean()),
            "Avg NPS (/10)": round(group["NPS"].mean(), 1),
        })
    
    # Add an All-Cohorts Aggregate Row
    total_all = len(df_logs)
    completed_all = len(df_logs[df_logs["Status"] == "Completed"])
    comp_rate_all = (completed_all / total_all * 100) if total_all > 0 else 0.0
    rows.append({
        "Cohort ID": "🌟 ALL COHORTS (Aggregate)",
        "Learners": total_all,
        "Avg Pre-Score": round(df_logs["Pre_Score"].mean(), 2),
        "Avg Post-Score": round(df_logs["Post_Score"].mean(), 2),
        "Avg Lift": f"+{df_logs['Lift'].mean():.2f}",
        "Completion Rate": f"{comp_rate_all:.1f}%",
        "Avg Duration (s)": int(df_logs["Duration"].mean()),
        "Avg NPS (/10)": round(df_logs["NPS"].mean(), 1),
    })
    return pd.DataFrame(rows)


def compute_item_discrimination(filtered_df: pd.DataFrame) -> pd.DataFrame:
    """
    Unpacks raw_responses JSON and computes Item Discrimination Index (D)
    and overall Difficulty (Pass Rate).
    Formula: D = P_Upper(27%) - P_Lower(27%)
    """
    json_col = "raw_responses" if "raw_responses" in filtered_df.columns else "Raw_Responses"
    if json_col not in filtered_df.columns:
        return pd.DataFrame()

    valid_records = filtered_df[filtered_df[json_col].notna()].copy()
    if len(valid_records) < 3:
        return pd.DataFrame()

    # Sort students by total combined score (Pre + Post) to segment upper/lower groups
    valid_records["total_score"] = valid_records["Pre_Score"] + valid_records["Post_Score"]
    sorted_records = valid_records.sort_values("total_score", ascending=False)
    
    n_sample = len(sorted_records)
    cutoff = max(1, int(round(n_sample * 0.27)))
    upper_group = sorted_records.head(cutoff)
    lower_group = sorted_records.tail(cutoff)

    # Flatten question-level items
    all_items = []
    for _, row in sorted_records.iterrows():
        resp = row[json_col]
        stu_id = row.get("Student", "anon")
        if not isinstance(resp, dict):
            continue
        
        # Parse Pre-Assessment items
        if "pre" in resp and isinstance(resp["pre"], dict):
            for q_k, q_v in resp["pre"].items():
                all_items.append({
                    "student_id": stu_id,
                    "stage": "Pre-Test",
                    "question": q_v.get("question", q_k),
                    "correct": 1 if q_v.get("is_correct") else 0,
                    "is_upper": stu_id in upper_group["Student"].values,
                    "is_lower": stu_id in lower_group["Student"].values,
                })
        # Parse Post-Assessment items
        if "post" in resp and isinstance(resp["post"], dict):
            for q_k, q_v in resp["post"].items():
                all_items.append({
                    "student_id": stu_id,
                    "stage": "Pulse Check",
                    "question": q_v.get("question", q_k),
                    "correct": 1 if q_v.get("is_correct") else 0,
                    "is_upper": stu_id in upper_group["Student"].values,
                    "is_lower": stu_id in lower_group["Student"].values,
                })

    if not all_items:
        return pd.DataFrame()

    df_items = pd.DataFrame(all_items)
    results = []

    for (stage, question), grp in df_items.groupby(["stage", "question"]):
        total_attempts = len(grp)
        overall_pass_rate = grp["correct"].mean()

        upper_sub = grp[grp["is_upper"]]
        lower_sub = grp[grp["is_lower"]]

        p_upper = upper_sub["correct"].mean() if not upper_sub.empty else 0.0
        p_lower = lower_sub["correct"].mean() if not lower_sub.empty else 0.0
        d_index = p_upper - p_lower

        # Evaluate discrimination quality rating
        if d_index >= 0.40:
            status = "🟢 Excellent"
        elif d_index >= 0.20:
            status = "🟡 Acceptable"
        elif d_index >= 0.0:
            status = "🟠 Poor / Revise"
        else:
            status = "🔴 Flawed / Miskeyed"

        results.append({
            "Stage": stage,
            "Question": question,
            "Attempts": total_attempts,
            "Difficulty (Pass Rate)": f"{overall_pass_rate * 100:.1f}%",
            "Upper 27% Pass": f"{p_upper * 100:.1f}%",
            "Lower 27% Pass": f"{p_lower * 100:.1f}%",
            "Discrimination (D)": f"{d_index:+.2f}",
            "Quality Rating": status,
        })

    return pd.DataFrame(results)

# ---------------------------------------------------------------------------
# ADMIN PANEL (EXPANDED BENCHMARKS & TELEMETRY)
# ---------------------------------------------------------------------------

def render_admin() -> None:
    st.title("📊 The Vault: Multi-Pilot Analytics & Psychometrics")
    pw = st.text_input("Access Key", type="password")

    if not pw:
        return
    if pw != ADMIN_PASSWORD:
        st.error("Incorrect access key.")
        return

    st.success("Access granted.")
    df_logs = load_logs()

    if df_logs is None or df_logs.empty:
        st.info("No student telemetry logged in Supabase yet.")
        return

    # -----------------------------------------------------------------------
    # 1. CROSS-COHORT BENCHMARKING TABLE
    # -----------------------------------------------------------------------
    st.markdown("### 🏛️ Cross-Cohort Institutional Benchmarking")
    st.caption("Side-by-side comparison across active pilots (e.g., Ivy Tech vs. High School vs. Standard).")
    df_benchmarks = compute_cohort_benchmarks(df_logs)
    st.dataframe(df_benchmarks, use_container_width=True, hide_index=True)

    st.divider()

    # -----------------------------------------------------------------------
    # 2. COHORT & TOPIC DRILL-DOWN FILTERS
    # -----------------------------------------------------------------------
    st.markdown("### 🔍 Filter Cohort & Topic Data")
    cohort_col, topic_col = st.columns(2)
    with cohort_col:
        available_pilots = ["All Cohorts"] + sorted(list(df_logs["Pilot_ID"].dropna().unique()))
        selected_cohort = st.selectbox("Cohort Filter:", available_pilots)
    
    filtered_df = df_logs if selected_cohort == "All Cohorts" else df_logs[df_logs["Pilot_ID"] == selected_cohort]

    with topic_col:
        available_topics = ["All Topics"] + sorted(list(filtered_df["Topic"].dropna().unique()))
        selected_topic = st.selectbox("Topic Filter:", available_topics)

    if selected_topic != "All Topics":
        filtered_df = filtered_df[filtered_df["Topic"] == selected_topic]

    if filtered_df.empty:
        st.warning("No records found matching the selected filters.")
        return

    # -----------------------------------------------------------------------
    # 3. HIGH-LEVEL KPI METRIC CARDS
    # -----------------------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Learners Analyzed", len(filtered_df))
    c2.metric("Average Lift", f"+{filtered_df['Lift'].mean():.2f}")
    c3.metric("Avg Duration", f"{int(filtered_df['Duration'].mean())}s")
    c4.metric("Avg NPS Score", f"{filtered_df['NPS'].mean():.1f} / 10")

    st.divider()

    # -----------------------------------------------------------------------
    # 4. VISUAL MASTERY & NPS CHARTS
    # -----------------------------------------------------------------------
    v1, v2 = st.columns(2)
    with v1:
        st.markdown("#### 🎯 Pre vs. Post Mastery by Topic")
        topic_scores = filtered_df.groupby("Topic")[["Pre_Score", "Post_Score"]].mean().reset_index()
        st.bar_chart(topic_scores, x="Topic", y=["Pre_Score", "Post_Score"], stack=False)

    with v2:
        st.markdown("#### ⚡ NPS Sentiment Distribution")
        nps_counts = filtered_df["NPS"].value_counts().reindex([2, 5, 8, 9, 10], fill_value=0).reset_index()
        nps_counts.columns = ["Rating", "Count"]
        st.bar_chart(nps_counts, x="Rating", y="Count")

    st.divider()

    # -----------------------------------------------------------------------
    # 5. PSYCHOMETRIC ITEM DISCRIMINATION (D-INDEX)
    # -----------------------------------------------------------------------
    st.markdown("### 🧠 Item Discrimination ($D$) & Distractor Diagnostic")
    st.caption("Evaluates how well questions separate top performers from struggling learners ($D = P_{Upper27\\%} - P_{Lower27\\%}$).")

    df_discrim = compute_item_discrimination(filtered_df)
    if not df_discrim.empty:
        st.dataframe(df_discrim, use_container_width=True, hide_index=True)
    else:
        st.info("Item discrimination requires at least 3 completed sessions with question telemetry.")

    st.divider()

    # -----------------------------------------------------------------------
    # 6. RAW TELEMETRY & EXPORT
    # -----------------------------------------------------------------------
    st.markdown("### 📋 Filtered Student Telemetry Log")
    st.dataframe(filtered_df.sort_values("Timestamp", ascending=False), use_container_width=True)
    st.download_button(
        label=f"📥 Export Telemetry CSV ({selected_cohort})",
        data=filtered_df.to_csv(index=False),
        file_name=f"vault_telemetry_{selected_cohort}_{datetime.now(NY_TZ).strftime('%Y%m%d')}.csv",
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
        class_code = st.text_input("Class Code", value=st.session_state.active_pilot_id)
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

    raw_responses = {
        "pre": {
            "q1": {
                "question": str(row.get("Pre_Q1", "")),
                "selected": st.session_state.ans_pre1,
                "correct_answer": str(row.get("Pre_A1", "")).strip(),
                "is_correct": st.session_state.ans_pre1 == str(row.get("Pre_A1", "")).strip(),
            },
            "q2": {
                "question": str(row.get("Pre_Q2", "")),
                "selected": st.session_state.ans_pre2,
                "correct_answer": str(row.get("Pre_A2", "")).strip(),
                "is_correct": st.session_state.ans_pre2 == str(row.get("Pre_A2", "")).strip(),
            },
        },
        "post": {
            "q1": {
                "question": str(row.get("Post_Q1", "")),
                "selected": pst_ans.get("q1"),
                "correct_answer": str(row.get("Post_A1", "")).strip(),
                "is_correct": pst_ans.get("q1") == str(row.get("Post_A1", "")).strip(),
            },
            "q2": {
                "question": str(row.get("Post_Q2", "")),
                "selected": pst_ans.get("q2"),
                "correct_answer": str(row.get("Post_A2", "")).strip(),
                "is_correct": pst_ans.get("q2") == str(row.get("Post_A2", "")).strip(),
            },
        },
    }

    record = {
        "Class":          st.session_state.class_code,
        "Student":        st.session_state.student_id,
        "Topic":          st.session_state.active_topic,
        "Pre_Score":      s_pre,
        "Post_Score":     s_post,
        "Lift":           lift,
        "NPS":            st.session_state.nps_score,
        "Duration":       int(elapsed),
        "Status":         status,
        "Raw_Responses":  raw_responses,
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

    st.markdown(f"### 🏛️ Select Your Story ({st.session_state.active_pilot_id})")

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
        st.error(f"Topic '{st.session_state.active_topic}' not found in active pilot.")
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
    client = get_supabase_client()
    
    st.sidebar.title("⚡ THE VAULT")
    if not client:
        st.sidebar.error("⚠️ Database: Disconnected")
    else:
        st.sidebar.success("⚡ Database: Connected")

    # Cohort switcher in sidebar
    new_pilot = st.sidebar.text_input(
        "Cohort ID:", 
        value=st.session_state.active_pilot_id,
        help="Change this to view topics from other pilots (e.g. CRIM171, ECON101)."
    )
    if new_pilot != st.session_state.active_pilot_id:
        st.session_state.active_pilot_id = new_pilot
        st.session_state.active_topic = None
        st.session_state.step = "pre_test"
        st.rerun()

    nav = st.sidebar.radio("Navigation", ["Learning Portal", "Pilot Summary (Admin)"])

    if nav == "Pilot Summary (Admin)":
        render_admin()
        return

    df_cms = load_cms_for_pilot(st.session_state.active_pilot_id)
    if df_cms is None or df_cms.empty:
        st.warning(f"⚠️ No topics found for Cohort '{st.session_state.active_pilot_id}'. Check the Cohort ID or add stories in Supabase.")
        st.stop()

    render_learning_portal(df_cms)


if __name__ == "__main__":
    main()
