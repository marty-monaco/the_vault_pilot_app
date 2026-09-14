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
