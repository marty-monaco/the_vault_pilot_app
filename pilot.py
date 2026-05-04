import streamlit as st
import pandas as pd
import os
from datetime import datetime
import pytz

# --- 1. APP CONFIG ---
st.set_page_config(page_title="The Vault Pilot", page_icon="⚡", layout="wide")

# --- FILE PATH FOR LOCAL STORAGE ---
DATA_FILE = "vault_mastery_logs.csv"

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
    # Public CSV Export of your CMS tab
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
                
                # DOWNLOAD BUTTON
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
                    "ans_pre1": None, "ans_pre2": None
                })
                st.rerun()

    st.divider()

    if not st.session_state.active_topic:
        st.info("Select a story above to begin.")
        st.stop()

    row = df_cms[df_cms["Topic"] == st.session_state.active_topic].iloc[0]

    # --- STEP 1: PRE-TEST ---
    if st.session_state.step == "pre_test":
        st.title(f"🔍 Pre-Assessment: {st.session_state.active_topic}")
        p1 = st.radio(row["Pre_Q1"], [row["Pre_Opt1"], row["Pre_Opt2"], row["Pre_Opt3"]], index=None, key="p1")
        p2 = st.radio(row["Pre_Q2"], [row["Pre_Opt1_Q2"], row["Pre_Opt2_Q2"], row["Pre_Opt3_Q2"]], index=None, key="p2")

        st.divider()
        c1, c2 = st.columns(2)
        with c1: class_code = st.text_input("Class Code")
        with c2: student_id = st.text_input("Your Initials")

        if st.button("ENTER THE VAULT ⚡", use_container_width=True):
            if not class_code or not student_id or p1 is None or p2 is None:
                st.warning("Please complete all questions.")
            else:
                st.session_state.update({
                    "class_code": class_code, "student_id": student_id,
                    "ans_pre1": p1, "ans_pre2": p2,
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
        pst1 = st.radio(row["Post_Q1"], [row["Post_Opt1"], row["Post_Opt2"], row["Post_Opt3"]], index=None, key="pst1")
        pst2 = st.radio(row["Post_Q2"], [row["Post_Opt1_Q2"], row["Post_Opt2_Q2"], row["Post_Opt3_Q2"]], index=None, key="pst2")

        st.divider()
        st.write("### ⚡ Rate this Vault Story")
        n_cols = st.columns(5)
        ratings = {"😴 Boring": 2, "😐 Okay": 5, "😎 Cool": 8, "🔥 Fire": 9, "🏆 Epic": 10}
        for i, (label, val) in enumerate(ratings.items()):
            if n_cols[i].button(label, use_container_width=True): st.session_state.nps_score = val

        if st.button("LOG MASTERY & FINISH 🚀", use_container_width=True):
            if pst1 is None or pst2 is None or st.session_state.nps_score is None:
                st.error("Complete all questions and select a rating.")
            else:
                now = datetime.now(st.session_state.ny_tz)
                elapsed = (now - st.session_state.start_time).total_seconds()
                s_pre = (1 if st.session_state.ans_pre1 == row["Pre_A1"] else 0) + (1 if st.session_state.ans_pre2 == row["Pre_A2"] else 0)
                s_post = (1 if pst1 == row["Post_A1"] else 0) + (1 if pst2 == row["Post_A2"] else 0)
                
                res = pd.DataFrame([{
                    "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "Class": st.session_state.class_code,
                    "Student": st.session_state.student_id,
                    "Topic": st.session_state.active_topic,
                    "Pre_Score": s_pre, "Post_Score": s_post, "Lift": s_post - s_pre,
                    "NPS": st.session_state.nps_score, "Duration": int(elapsed),
                    "Status": "Completed" if elapsed >= (float(row.get("Video_Length_Sec", 85)) * 0.9) else "Skimmed"
                }])

                # --- LOCAL CSV WRITING ---
                res.to_csv(DATA_FILE, mode='a', header=not os.path.exists(DATA_FILE), index=False)
                
                st.balloons()
                st.success("Mastery logged locally! You can download results in the Admin panel.")
