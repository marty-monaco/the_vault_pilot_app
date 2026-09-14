"""
the_vault_pilot_app/views/student_portal.py
Student delivery experience: Pre-test, video playback, Pulse Check, NPS, and telemetry.
"""
import re, random, logging
from datetime import datetime
import pytz, pandas as pd, streamlit as st
from supabase import Client

logger = logging.getLogger(__name__)
NY_TZ = pytz.timezone("US/Eastern")
VIDEO_COMPLETE_RATIO, DEFAULT_VIDEO_LEN_SEC = 0.9, 85
NPS_RATINGS = [("😴 Boring", 2), ("😐 Okay", 5), ("😎 Cool", 8), ("🔥 Fire", 9), ("🏆 Epic", 10)]
YT_RE = re.compile(r'(?:v=|\/([0-9A-Za-z_-]{11})|youtu\.be\/|\/shorts\/|\/embed\/)([0-9A-Za-z_-]{11})')

def resolve_video_url(raw_url: str) -> str | None:
    m = YT_RE.search(str(raw_url).strip())
    return f"https://www.youtube.com/watch?v={m.group(1) or m.group(2)}" if m else (raw_url if str(raw_url).startswith("http") else None)

def get_questions(row: pd.Series, prefix: str) -> list[dict]:
    p = "Pre" if prefix == "pre" else "Post"
    def _opts(q_suf=""):
        return [str(row[f"{p}_Opt{i}{q_suf}"]) for i in (1, 2, 3) if pd.notna(row.get(f"{p}_Opt{i}{q_suf}")) and str(row[f"{p}_Opt{i}{q_suf}"]).strip()]
    q1_opts, q2_opts = _opts(""), _opts("_Q2")
    pool = [
        {"id": "q1", "text": str(row[f"{p}_Q1"]), "options": random.sample(q1_opts, len(q1_opts)), "ans": str(row[f"{p}_A1"]).strip()},
        {"id": "q2", "text": str(row[f"{p}_Q2"]), "options": random.sample(q2_opts, len(q2_opts)), "ans": str(row[f"{p}_A2"]).strip()}
    ]
    random.shuffle(pool)
    return pool

def render_student_portal(df_cms: pd.DataFrame, client: Client | None) -> None:
    for k, v in [("portal_step", "pre_test"), ("active_topic", None), ("shuffled_pre", None), ("shuffled_post", None), ("nps_score", None), ("completed_res", None)]:
        st.session_state.setdefault(k, v)

    # 1. Topic Grid
    topic_col = "Topic" if "Topic" in df_cms.columns else "topic"
    topics = df_cms[topic_col].tolist()
    st.markdown(f"### 🏛️ Select Your Story ({st.session_state.active_pilot_id})")
    cols = st.columns(3)
    for i, t in enumerate(topics):
        if cols[i % 3].button(f"📖 {t}", use_container_width=True):
            st.session_state.update({"active_topic": t, "portal_step": "pre_test", "shuffled_pre": None, "shuffled_post": None, "completed_res": None})
            st.rerun()

    st.divider()
    if not st.session_state.active_topic:
        st.info("Select a story above to begin.")
        return

    row = df_cms[df_cms[topic_col] == st.session_state.active_topic].iloc[0]

    # 2. Stage: Pre-Test
    if st.session_state.portal_step == "pre_test":
        st.title(f"🔍 Pre-Assessment: {st.session_state.active_topic}")
        if not st.session_state.shuffled_pre:
            st.session_state.shuffled_pre = get_questions(row, "pre")

        answers = {q["id"]: st.radio(f"Question {i+1}: {q['text']}", q["options"], index=None, key=f"pre_{q['id']}") for i, q in enumerate(st.session_state.shuffled_pre)}
        c1, c2 = st.columns(2)
        code, initials = c1.text_input("Class Code", value=st.session_state.active_pilot_id), c2.text_input("Your Initials")

        if st.button("ENTER THE VAULT ⚡", type="primary", use_container_width=True):
            if not code.strip() or not initials.strip() or any(v is None for v in answers.values()):
                st.warning("Please provide your initials, class code, and answer all questions.")
            else:
                st.session_state.update({"class_code": code.strip(), "student_id": initials.strip().upper(), "pre_ans": answers, "start_time": datetime.now(NY_TZ), "portal_step": "video"})
                st.rerun()

    # 3. Stage: Video & Pulse Check
    elif st.session_state.portal_step == "video":
        if st.session_state.completed_res:
            res = st.session_state.completed_res
            if res["status"] == "Completed":
                st.balloons()
                st.markdown(f'
{res["student_id"]}

CERTIFIED MASTER


LIFT: {res["lift"]:+d}

', unsafe_allow_html=True)
else:
st.warning(f"Mastery logged! Lift: {res['lift']:+d}. Watch the full video next time to earn a badge.")
if st.button("⬅️ Choose Another Story", use_container_width=True):
st.session_state.update({"active_topic": None, "portal_step": "pre_test", "completed_res": None})
st.rerun()
return
    st.title(f"🎬 {st.session_state.active_topic}")
    v_url = resolve_video_url(row.get("Video_URL") or row.get("video_url", ""))
    if v_url: st.video(v_url)
    else: st.warning("⚠️ Video URL missing or invalid.")

    st.divider()
    st.write("### 🧠 Pulse Check")
    if not st.session_state.shuffled_post:
        st.session_state.shuffled_post = get_questions(row, "post")

    post_ans = {q["id"]: st.radio(f"Question {i+1}: {q['text']}", q["options"], index=None, key=f"post_{q['id']}") for i, q in enumerate(st.session_state.shuffled_post)}

    st.divider()
    st.write("### ⚡ Rate this Vault Story")
    rate_cols = st.columns(len(NPS_RATINGS))
    for col, (label, val) in zip(rate_cols, NPS_RATINGS):
        if col.button(label, use_container_width=True):
            st.session_state.nps_score = val
    if st.session_state.nps_score:
        st.success(f"Selected Rating: {st.session_state.nps_score}/10")

    if st.button("LOG MASTERY & FINISH 🚀", type="primary", use_container_width=True):
        if any(v is None for v in post_ans.values()) or st.session_state.nps_score is None:
            st.error("Please answer both questions and select a rating.")
        else:
            duration = int((datetime.now(NY_TZ) - st.session_state.start_time).total_seconds())
            s_pre = sum(1 for q in st.session_state.shuffled_pre if st.session_state.pre_ans.get(q["id"]) == q["ans"])
            s_post = sum(1 for q in st.session_state.shuffled_post if post_ans.get(q["id"]) == q["ans"])
            lift = s_post - s_pre

            v_len = float(row.get("Video_Length_Sec") or row.get("video_length_sec") or DEFAULT_VIDEO_LEN_SEC)
            status = "Completed" if duration >= v_len * VIDEO_COMPLETE_RATIO else "Skimmed"

            raw_data = {
                stage: {q["id"]: {"question": q["text"], "selected": answers.get(q["id"]), "correct_answer": q["ans"], "is_correct": answers.get(q["id"]) == q["ans"]}
                        for q in pool}
                for stage, answers, pool in [("pre", st.session_state.pre_ans, st.session_state.shuffled_pre), ("post", post_ans, st.session_state.shuffled_post)]
            }

            if client:
                payload = {
                    "pilot_id": st.session_state.active_pilot_id, "class_code": st.session_state.class_code,
                    "student_id": st.session_state.student_id, "topic": st.session_state.active_topic,
                    "pre_score": s_pre, "post_score": s_post, "lift": lift,
                    "nps": st.session_state.nps_score, "duration": duration, "status": status,
                    "raw_responses": raw_data
                }
                try:
                    client.table("pilot_mastery_logs").upsert(payload, on_conflict="pilot_id,student_id,topic").execute()
                except Exception as e:
                    logger.error(f"Supabase logging error: {e}")

            st.session_state.completed_res = {"status": status, "student_id": st.session_state.student_id, "lift": lift}
            st.rerun()

