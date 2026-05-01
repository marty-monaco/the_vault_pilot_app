import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import pytz

# --- 1. APP CONFIG ---
st.set_page_config(page_title="The Vault Pilot", page_icon="⚡", layout="wide")

# --- 2. DATA CONNECTION ---
# Pointing directly to your new repo file
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_vault_data():
    # Direct CSV read to bypass the connection manager for a second
    url = "https://docs.google.com/spreadsheets/d/1MsDmw8Rc3ikacwll3o8JMo2w4qI0GFeYrsoXAIAXlDg/export?format=csv&gid=0"
    return pd.read_csv(url)

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

        if st.session_state.active_topic:
            row = df_cms[df_cms["Topic"] == st.session_state.active_topic].iloc[0]

            # --- STEP 1: PRE-TEST ---
            if st.session_state.step == "pre_test":
                st.title(f"🔍 Pre-Assessment: {st.session_state.active_topic}")
                p1 = st.radio(row["Pre_Q1"], [row["Pre_Opt1"], row["Pre_Opt2"], row["Pre_Opt3"]], index=None, key="p1")
                p2 = st.radio(row["Pre_Q2"], [row["Pre_Opt1_Q2"], row["Pre_Opt2_Q2"], row["Pre_Opt3_Q2"]], index=None, key="p2")
                
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
                            "step": "vault_content"
                        })
                        st.rerun()

            # --- STEP 2: CONTENT & WRITING TO SHEET ---
            elif st.session_state.step == "vault_content":
                st.title(f"🎬 {st.session_state.active_topic}")
                st.video(str(row.get("Video_URL", "")))
                
                st.write("### ⚡ Rate this Vault Story")
                nps = st.select_slider("Rating", options=list(range(1, 11)))

                if st.button("LOG MASTERY & FINISH 🚀", use_container_width=True):
                    now = datetime.now(st.session_state.ny_tz)
                    elapsed = (now - st.session_state.start_time).total_seconds()
                    
                    # Create result row
                    res = pd.DataFrame([{
                        "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "Class": st.session_state.class_code,
                        "Student": st.session_state.student_id,
                        "Topic": st.session_state.active_topic,
                        "Lift": 1, # Placeholder for logic
                        "NPS": nps, 
                        "Duration": int(elapsed)
                    }])

                    # THE WRITE STEP
                    try:
                        # Append to the 'logs' tab in your specific sheet
                        conn.create(worksheet="logs", data=res)
                        st.balloons()
                        st.success("Mastery Logged to your Sheet! 📈")
                    except Exception as e:
                        st.error(f"Write Error: {e}. Check permissions!")
