import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import pytz

# --- 1. APP CONFIG ---
st.set_page_config(page_title="The Vault Pilot", page_icon="⚡", layout="wide")

# Custom UI Styling
st.markdown("""
    <style>
    div.stButton > button:first-child { border-radius: 10px; font-weight: bold; height: 3em; }
    .mastery-badge {
        background: linear-gradient(135deg, #FFD700 0%, #B8860B 100%);
        color: #1A1A1A; padding: 25px; border-radius: 15px;
        text-align: center; border: 2px solid #B8860B;
        font-family: 'Courier New', Courier, monospace; margin-top: 20px;
    }
    .badge-initials { font-size: 40px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. DATA CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_vault_data():
    # Reads the 'cms' tab for content
    return conn.read(worksheet="cms")

df_cms = load_vault_data()

# --- 3. SESSION STATE ---
if 'step' not in st.session_state: st.session_state.step = "pre_test"
if 'active_topic' not in st.session_state: st.session_state.active_topic = None
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'nps_score' not in st.session_state: st.session_state.nps_score = None
if 'ny_tz' not in st.session_state: st.session_state.ny_tz = pytz.timezone('US/Eastern')

# --- 4. NAVIGATION ---
st.sidebar.title("⚡ THE VAULT")
nav = st.sidebar.radio("Navigation", ["Learning Portal", "Pilot Summary (Admin)"])

if df_cms is not None:
    topic_list = df_cms["Topic"].tolist()

    if nav == "Learning Portal":
        st.markdown("### 🏛️ Select Your Vault Story")
        cols = st.columns(len(topic_list))
        for i, t in enumerate(topic_list):
            if cols[i].button(f"📖 {t}", use_container_width=True):
                st.session_state.active_topic = t
                st.session_state.step = "pre_test"
                st.session_state.nps_score = None 
                st.rerun()

        st.divider()

        if st.session_state.active_topic:
            row = df_cms[df_cms["Topic"] == st.session_state.active_topic].iloc[0]

            # STEP 1: PRE-TEST
            if st.session_state.step == "pre_test":
                st.title(f"🔍 Pre-Assessment: {st.session_state.active_topic}")
                p1 = st.radio(row["Pre_Q1"], [row["Pre_Opt1"], row["Pre_Opt2"], row["Pre_Opt3"]], index=None, key="p1")
                p2 = st.radio(row["Pre_Q2"], [row["Pre_Opt1_Q2"], row["Pre_Opt2_Q2"], row["Pre_Opt3_Q2"]], index=None, key="p2")
                
                c1, c2 = st.columns(2)
                with c1: class_code = st.text_input("Class Code (e.g. CRIM171)")
                with c2: student_id = st.text_input("Your Initials")

                if st.button("ENTER THE VAULT ⚡", use_container_width=True):
                    if not class_code or not student_id or p1 is None or p2 is None:
                        st.warning("Please complete all fields to enter.")
                    else:
                        st.session_state.update({
                            "class_code": class_code, "student_id": student_id,
                            "ans_pre1": p1, "ans_pre2": p2, 
                            "start_time": datetime.now(st.session_state.ny_tz), 
                            "step": "vault_content"
                        })
                        st.rerun()

            # STEP 2: CONTENT & LOGGING
            elif st.session_state.step == "vault_content":
                st.title(f"🎬 {st.session_state.active_topic}")
                
                # Handling empty URLs
                v_url = str(row.get("Video_URL", "")).strip()
                st.video(v_url if v_url.startswith("http") else "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                
                st.divider()
                st.write("### 🧠 Pulse Check")
                pst1 = st.radio(row["Post_Q1"], [row["Post_Opt1"], row["Post_Opt2"], row["Post_Opt3"]], index=None, key="pst1")
                pst2 = st.radio(row["Post_Q2"], [row["Post_Opt1_Q2"], row["Post_Opt2_Q2"], row["Post_Opt3_Q2"]], index=None, key="pst2")
                
                st.write("### ⚡ Rate this Vault Story")
                n_cols = st.columns(5)
                ratings = {"😴\nBoring": 2, "😐\nOkay": 5, "😎\nCool": 8, "🔥\nFire": 9, "🏆\nEpic": 10}
                for i, (label, val) in enumerate(ratings.items()):
                    if n_cols[i].button(label, use_container_width=True): 
                        st.session_state.nps_score = val

                if st.button("LOG MASTERY & FINISH 🚀", use_container_width=True):
                    if pst1 is None or pst2 is None or st.session_state.nps_score is None:
                        st.error("Please complete the Pulse Check and Rating.")
                    else:
                        now = datetime.now(st.session_state.ny_tz)
                        elapsed = (now - st.session_state.start_time).total_seconds()
                        target_len = float(row.get("Video_Length_Sec", 85))
                        status = "Completed" if elapsed >= (target_len * 0.9) else "Skimmed"

                        s_pre = (1 if st.session_state.ans_pre1 == row["Pre_A1"] else 0) + (1 if st.session_state.ans_pre2 == row["Pre_A2"] else 0)
                        s_post = (1 if pst1 == row["Post_A1"] else 0) + (1 if pst2 == row["Post_A2"] else 0)

                        res = pd.DataFrame([{
                            "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                            "Class": st.session_state.class_code,
                            "Student": st.session_state.student_id,
                            "Topic": st.session_state.active_topic,
                            "Pre_Score": s_pre, "Post_Score": s_post, "Lift": s_post - s_pre,
                            "NPS": st.session_state.nps_score, "Duration": int(elapsed), "Status": status
                        }])

                        try:
                            # Read logs, append, and push back to 'logs' tab
                            current_logs = conn.read(worksheet="logs")
                            updated_logs = pd.concat([current_logs, res], ignore_index=True)
                            conn.update(worksheet="logs", data=updated_logs)
                            
                            st.balloons()
                            st.markdown(f'<div class="mastery-badge"><div class="badge-initials">{st.session_state.student_id.upper()}</div>CERTIFIED MASTER<br>LIFT: +{s_post - s_pre}</div>', unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"Data Sync Error: {e}")

    elif nav == "Pilot Summary (Admin)":
        st.title("📊 Vault Analytics")
        try:
            logs = conn.read(worksheet="logs")
            if not logs.empty:
                st.dataframe(logs, use_container_width=True)
                st.metric("Total Masteries Logged", len(logs))
                st.metric("Avg Score Lift", round(logs["Lift"].mean(), 2))
            else:
                st.info("No logs found yet.")
        except:
            st.error("Could not load the 'logs' tab. Ensure it exists in your Google Sheet.")
