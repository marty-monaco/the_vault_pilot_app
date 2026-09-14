"""
the_vault_pilot_app/views/student_portal.py

Student delivery experience: Pre-test diagnostics, video playback,
Pulse Check post-test, NPS rating, and certified mastery badges.
"""
import re
import random
from datetime import datetime
import pytz
import pandas as pd
import streamlit as st
from supabase import Client

NY_TZ = pytz.timezone("US/Eastern")
VIDEO_COMPLETE_RATIO = 0.9
DEFAULT_VIDEO_LEN_SEC = 85

NPS_RATINGS = [
    ("😴 Boring", 2),
    ("😐 Okay", 5),
    ("😎 Cool", 8),
    ("🔥 Fire", 9),
    ("🏆 Epic", 10),
]

YT_PATTERN = re.compile(
    r'(?:v=|\/([0-9A-Za-z_-]{11})|youtu\.be\/|\/shorts\/|\/embed\/)([0-9A-Za-z_-]{11})'
)


def resolve_video_url(raw_url: str) -> str | None:
    raw_url = str(raw_url).strip()
    match = YT_PATTERN.search(raw_url)
    if match:
        video_id = match.group(1) or match.group(2)
        return f"https://www.youtube.com/watch?v={video_id}"
    if raw_url.startswith("http"):
        return raw_url
    return None


def build_shuffled_questions(row: pd.Series, stage: str) -> list[dict]:
    p = "Pre" if stage == "pre" else "Post"
    opts_q1 = [row.get(f"{p}_Opt1"), row.get(f"{p}_Opt2"), row.get(f"{p}_Opt3")]
    opts_q2 = [row.get(f"{p}_Opt1_Q2"), row.get(f"{p}_Opt2_Q2"), row.get(f"{p}_Opt3_Q2")]

    opts_q1 = [str(o) for o in opts_q1 if pd.notna(o) and str(o).strip()]
    opts_q2 = [str(o) for o in opts_q2 if pd.notna(o) and str(o).strip()]

    pool = [
        {"id": "q1", "text": str(row.get(f"{p}_Q1", "")), "options": random.sample(opts_q1, len(opts_q1))},
        {"id": "q2", "text": str(row.get(f"{p}_Q2", "")), "options": random.sample(opts_q2, len(opts_q2))},
    ]
    random.shuffle(pool)
    return pool


def score_answers(answers: dict, row: pd.Series, stage: str) -> int:
    p = "Pre" if stage == "pre" else "Post"
    score = 0
    if str(answers.get("q1", "")).strip() == str(row.get(f"{p}_A1", "")).strip():
        score += 1
    if str(answers.get("q2", "")).strip() == str(row.get(f"{p}_A2", "")).strip():
        score += 1
    return score


def render_mastery_badge(initials: str, lift: int) -> None:
    badge_html = f"""
if st.button("ENTER THE VAULT ⚡", type="primary", use_container_width=True):
        if not code.strip() or not initials.strip() or answers.get("q1") is None or answers.get("q2") is None:
            st.warning("Please enter your initials, class code, and answer all questions.")
        else:
            st.session_state.class_code = code.strip()
            st.session_state.student_id = initials.strip().upper()
            st.session_state.pre_answers = answers
            st.session_state.start_time = datetime.now(NY_TZ)
            st.session_state.portal_step = "video"
            st.rerun()

    # 3. Stage: Video & Pulse Check
    elif st.session_state.portal_step == "video":
        if st.session_state.completed_result:
            res = st.session_state.completed_result
            if res.get("status") == "Completed":
                st.balloons()
                render_mastery_badge(res.get("student_id"), res.get("lift"))
            else:
                st.warning(
                    f"Mastery recorded! Lift: {res.get('lift'):+d}. "
                    "Watch the full video next time to earn a badge."
                )

            if st.button("⬅️ Choose Another Story", use_container_width=True):
                st.session_state.active_topic = None
                st.session_state.portal_step = "pre_test"
                st.session_state.completed_result = None
                st.rerun()
            return

        st.title(f"🎬 {st.session_state.active_topic}")
        v_url = resolve_video_url(row.get("Video_URL") or row.get("video_url", ""))
        if v_url:
            st.video(v_url)
        else:
            st.warning("⚠️ Video URL missing or invalid for this topic.")

        st.divider()
        st.write("### 🧠 Pulse Check")

        if st.session_state.shuffled_post is None:
            st.session_state.shuffled_post = build_shuffled_questions(row, "post")

        post_answers = {}
        for idx, q in enumerate(st.session_state.shuffled_post):
            post_answers[q["id"]] = st.radio(
                f"Question {idx+1}: {q['text']}",
                q["options"],
                index=None,
                key=f"post_{q['id']}",
            )

        st.divider()
        st.write("### ⚡ Rate this Vault Story")
        rate_cols = st.columns(len(NPS_RATINGS))
        for col, (label, val) in zip(rate_cols, NPS_RATINGS):
            if col.button(label, use_container_width=True):
                st.session_state.nps_score = val

        if st.session_state.nps_score is not None:
            st.success(f"Selected Rating: {st.session_state.nps_score}/10")

        if st.button("LOG MASTERY & FINISH 🚀", type="primary", use_container_width=True):
            if post_answers.get("q1") is None or post_answers.get("q2") is None:
                st.error("Please answer both Pulse Check questions.")
            elif st.session_state.nps_score is None:
                st.error("Please select a rating before finishing.")
            else:
                now = datetime.now(NY_TZ)
                duration = int((now - st.session_state.start_time).total_seconds())

                s_pre = score_answers(st.session_state.pre_answers, row, "pre")
                s_post = score_answers(post_answers, row, "post")
                lift = s_post - s_pre

                v_len = float(row.get("Video_Length_Sec") or row.get("video_length_sec") or DEFAULT_VIDEO_LEN_SEC)
                status = "Completed" if duration >= v_len * VIDEO_COMPLETE_RATIO else "Skimmed"

                raw_responses = {
                    "pre": {
                        "q1": {
                            "question": str(row.get("Pre_Q1", "")),
                            "selected": st.session_state.pre_answers.get("q1"),
                            "correct_answer": str(row.get("Pre_A1", "")).strip(),
                            "is_correct": st.session_state.pre_answers.get("q1") == str(row.get("Pre_A1", "")).strip(),
                        },
                        "q2": {
                            "question": str(row.get("Pre_Q2", "")),
                            "selected": st.session_state.pre_answers.get("q2"),
                            "correct_answer": str(row.get("Pre_A2", "")).strip(),
                            "is_correct": st.session_state.pre_answers.get("q2") == str(row.get("Pre_A2", "")).strip(),
                        },
                    },
                    "post": {
                        "q1": {
                            "question": str(row.get("Post_Q1", "")),
                            "selected": post_answers.get("q1"),
                            "correct_answer": str(row.get("Post_A1", "")).strip(),
                            "is_correct": post_answers.get("q1") == str(row.get("Post_A1", "")).strip(),
                        },
                        "q2": {
                            "question": str(row.get("Post_Q2", "")),
                            "selected": post_answers.get("q2"),
                            "correct_answer": str(row.get("Post_A2", "")).strip(),
                            "is_correct": post_answers.get("q2") == str(row.get("Post_A2", "")).strip(),
                        },
                    },
                }

                if client:
                    payload = {
                        "pilot_id":       st.session_state.active_pilot_id,
                        "class_code":     st.session_state.class_code,
                        "student_id":     st.session_state.student_id,
                        "topic":          st.session_state.active_topic,
                        "pre_score":      s_pre,
                        "post_score":     s_post,
                        "lift":           lift,
                        "nps":            st.session_state.nps_score,
                        "duration":       duration,
                        "status":         status,
                        "raw_responses":  raw_responses,
                    }
                    try:
                        client.table("pilot_mastery_logs").upsert(
                            payload,
                            on_conflict="pilot_id,student_id,topic"
                        ).execute()
                    except Exception as e:
                        logger.error(f"Error logging mastery to Supabase: {e}")

                st.session_state.completed_result = {
                    "status": status,
                    "student_id": st.session_state.student_id,
                    "lift": lift,
                }
                st.rerun()
