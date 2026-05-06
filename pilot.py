import streamlit as st
import pandas as pd
import os
import random
from datetime import datetime
import pytz

# --- 1. APP CONFIG ---
st.set_page_config(page_title="The Vault Pilot", page_icon="⚡", layout="wide")

# --- FILE PATH FOR LOCAL STORAGE ---
DATA_FILE = os.path.join(os.getcwd(), "vault_mastery_logs.csv")

# Custom UI Styling
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

# --- 2. DATA LOADING (CMS) ---
@st.cache_data(ttl=60)
def load_vault_data():
    url = "https://docs.google.com/spreadsheets/d/1sxxEyxjvicryUGJRMcd05Hcy6rIFLuXiTZPR_Mco7n8/export?format=csv&gid=0"
    return pd.read_csv(url)

df_cms = load_vault_data()

# --- 3. SESSION STATE ---
defaults = {
    "step": "pre_test",
    "active_topic": None,
    "start_time": None,
    "nps_score": None,
    "ans_pre1": None,
    "ans_pre2": None,
    "class_code": "",
    "student_id": "",
    "ny_tz": pytz.timezone("US/Eastern"),
    "shuffled_pre": None,
    "shuffled_post": None
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# --- 4. NAVIGATION ---
st.sidebar.title("⚡ THE VAULT")
nav = st.sidebar.radio("Navigation", ["Learning Portal", "Pilot Summary (Admin)"])

# ===========================================================================
# ADMIN PANEL (LOCAL DOWNLOAD)
# ===========================================================================
if nav == "Pilot Summary (Admin)":
    st.title("🔐 Admin Dashboard")
    pw = st.text_input("Access Key", type="password")

    if pw == "vault2026":
        if os.path.exists(DATA_FILE):
            df_logs = pd.read_csv(DATA_FILE)
            if df_logs.empty:
                st.info("No submissions yet.")
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Learners", len(df_logs))
                c2.metric("Avg Lift", f"+{df_logs['Lift'].mean():.2f}")
                c3.metric("Avg Duration", f"{int(df_logs['Duration'].mean())}s")
                c4.metric("Avg NPS", f"{df_logs['NPS'].mean():.1f}")
                st.dataframe(df_logs.sort_values("Timestamp", ascending=False), use_container_width=True)
                
                st.download_button(
                    label="📥 Download Pilot CSV",
                    data=df_logs.to_csv(index=False),
                    file_name=f"vault_pilot_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        else:
            st.info("No data file found yet. Logs will be created after the first submission.")
    elif pw:
        st.error("Incorrect access key.")

# ===========================================================================
# LEARNING PORTAL
# ===========================================================================
elif nav == "Learning Portal":
    if df_cms is None:
        st.error("Could not load CMS data.")
        st.stop()

    topic_list = df_cms["Topic"].tolist()
    st.markdown("### 🏛️ Select Your Vault Story")
    
    n_cols = 3
    for i in range(0, len(topic_list), n_cols):
        grid_cols = st.columns(n_cols)
        for j, t in enumerate(topic_list[i:i+n_cols]):
            if grid_cols[j].button(f"📖 {t}", use_container_width=True):
                st.session_state.update({
                    "active_topic": t, "step": "pre_test", "nps_score": None,
                    "ans_pre1": None, "ans_pre2": None,
                    "shuffled_pre": None,
                    "shuffled_post": None
                })
                st.rerun()

    st.divider()

    if not st.session_state.active_topic:
        st.info("Select a story above to begin.")
        st.stop()

    row = df_cms[df_cms["Topic"] == st.session_state.active_topic].iloc[0]

    # --- RANDOMIZATION ENGINE ---
    if st.session_state.shuffled_pre is None:
        pre_opts_q1 = [row["Pre_Opt1"], row["Pre_Opt2"], row["Pre_Opt3"]]
        pre_opts_q2 = [row["Pre_Opt1_Q2"], row["Pre_Opt2_Q2"], row["Pre_Opt3_Q2"]]
        
        random.shuffle(pre_opts_q1)
        random.shuffle(pre_opts_q2)
        
        q_pool = [
            {"id": "q1", "text": row["Pre_Q1"], "options": pre_opts_q1},
            {"id": "q2", "text": row["Pre_Q2"], "options": pre_opts_q2}
        ]
        random.shuffle(q_pool)
        st.session_state.shuffled_pre = q_pool

    if st.session_state.shuffled_post is None:
        post_opts_q1 = [row["Post_Opt1"], row["Post_Opt2"], row["Post_Opt3"]]
        post_opts_q2 = [row["Post_Opt1_Q2"], row["Post_Opt2_Q2"], row["Post_Opt3_Q2"]]
        
        random.shuffle(post_opts_q1)
        random.shuffle(post_opts_q2)
        
        qp_pool = [
            {"id": "q1", "text": row["Post_Q1"], "options": post_opts_q1},
            {"id": "q2", "text": row["Post_Q2"], "options": post_opts_q2}
        ]
        random.shuffle(qp_pool)
        st.session_state.shuffled_post = qp_pool

    # --- STEP 1: PRE-TEST ---
    if st.session_state.step == "pre_test":
        st.title(f"🔍 Pre-Assessment: {st.session_state.active_topic}")
        
        p_ans = {}
        for idx, q in enumerate(st.session_state.shuffled_pre):
            p_ans[q["id"]] = st.radio(
                f"Question {idx+1}: {q['text']}", 
                q["options"], 
                index=None, 
                key=f"p_{q['id']}"
            )

        st.divider()
        c1, c2 = st.columns(2)
        with c1: class_code = st.text_input("Class Code")
        with c2: student_id = st.text_input("Your Initials")

        if st.button("ENTER THE VAULT ⚡", use_container_width=True):
            if not class_code or not student_id or p_ans["q1"] is None or p_ans["q2"] is None:
                st.warning("Please complete all questions.")
            else:
                st.session_state.update({
                    "class_code": class_code, "student_id": student_id,
                    "ans_pre1": p_ans["q1"], "ans_pre2": p_ans["q2"],
                    "start_time": datetime.now(st.session_state.ny_tz),
                    "step": "vault_content",
                })
                st.rerun()

    # --- STEP 2: VIDEO + PULSE CHECK ---
    elif st.session_state.step == "vault_content":
        st.title(f"🎬 {st.session_state.active_topic}")
        v_url = str(row.get("Video_URL", "")).strip()
        if v_url.startswith("http"):
            st.video(v_url)
        
        st.divider()
        st.write("### 🧠 Pulse Check")
        
        pst_ans = {}
        for idx, q in enumerate(st.session_state.shuffled_post):
            pst_ans[q["id"]] = st.radio(
                f"Question {idx+1}: {q['text']}", 
                q["options"], 
                index=None, 
                key=f"pst_{q['id']}"
            )

        st.divider()
        st.write("### ⚡ Rate this Vault Story")
        n_cols = st.columns(5)
        ratings = {"😴 Boring": 2, "😐 Okay": 5, "😎 Cool": 8, "🔥 Fire": 9, "🏆 Epic": 10}
        for i, (label, val) in enumerate(ratings.items()):
            if n_cols[i].button(label, use_container_width=True): st.session_state.nps_score = val

        if st.session_state.nps_score:
            st.success(f"Selected Rating: {st.session_state.nps_score}/10")

        if st.button("LOG MASTERY & FINISH 🚀", use_container_width=True):
            if pst_ans["q1"] is None or pst_ans["q2"] is None or st.session_state.nps_score is None:
                st.error("Complete all questions and select a rating.")
            else:
                now = datetime.now(st.session_state.ny_tz)
                elapsed = (now - st.session_state.start_time).total_seconds()
                s_pre = (1 if st.session_state.ans_pre1 == row["Pre_A1"] else 0) + (1 if st.session_state.ans_pre2 == row["Pre_A2"] else 0)
                s_post = (1 if pst_ans["q1"] == row["Post_A1"] else 0) + (1 if pst_ans["q2"] == row["Post_A2"] else 0)
                lift = s_post - s_pre
                status = "Completed" if elapsed >= (float(row.get("Video_Length_Sec", 85)) * 0.9) else "Skimmed"
                
                res = pd.DataFrame([{
                    "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "Class": st.session_state.class_code,
                    "Student": st.session_state.student_id,
                    "Topic": st.session_state.active_topic,
                    "Pre_Score": s_pre, "Post_Score": s_post, "Lift": lift,
                    "NPS": st.session_state.nps_score, "Duration": int(elapsed),
                    "Status": status
                }])

                # --- LOCAL CSV WRITING ---
                res.to_csv(DATA_FILE, mode='a', header=not os.path.exists(DATA_FILE), index=False)
                
                # --- BACKUP: PERSISTENT SECRETS LOGGING ---
                try:
                    log_line = f"{now.strftime('%Y-%m-%d %H:%M:%S')},{st.session_state.class_code},{st.session_state.student_id},{st.session_state.active_topic},{s_pre},{s_post},{lift},{st.session_state.nps_score},{int(elapsed)},{status}\n"
                    if "raw_logs" not in st.secrets:
                        st.secrets["raw_logs"] = "Timestamp,Class,Student,Topic,Pre_Score,Post_Score,Lift,NPS,Duration,Status\n"
                    st.secrets["raw_logs"] += log_line
                except Exception:
                    pass
                
                st.balloons()
                st.success("Mastery logged locally and backed up!")
