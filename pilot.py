import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. APP CONFIG & UI ---
st.set_page_config(page_title="The Nostalgia Vault", page_icon="⚡", layout="wide")

# Custom CSS for the "Forced-Choice" NPS Buttons and Mastery Badge
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

# --- 2. DATA LOADING ---
@st.cache_data(ttl=60)
def load_cms_data():
    try:
        raw_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        csv_url = raw_url.replace('/edit?usp=sharing', '/export?format=csv').split('/edit')[0] + '/export?format=csv&gid=0'
        return pd.read_csv(csv_url)
    except Exception as e:
        st.error(f"CMS Connection Error: {e}")
        return None

df_cms = load_cms_data()

# --- 3. SESSION STATE ---
if 'step' not in st.session_state: st.session_state.step = "pre_test"
if 'active_topic' not in st.session_state: st.session_state.active_topic = None
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'nps_score' not in st.session_state: st.session_state.nps_score = None

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
                st.session_state.nps_score = None # Reset NPS for new story
                st.rerun()

        st.divider()

        if st.session_state.active_topic:
            row = df_cms[df_cms["Topic"] == st.session_state.active_topic].iloc[0]

            # --- STEP 1: PRE-TEST ---
            if st.session_state.step == "pre_test":
                st.title(f"🔍 Pre-Assessment: {st.session_state.active_topic}")
                p1 = st.radio(row["Pre_Q1"], [row["Pre_Opt1"], row["Pre_Opt2"], row["Pre_Opt3"]], index=None, key="p1")
                p2 = st.radio(row["Pre_Q2"], [row["Pre_Opt1_Q2"], row["Pre_Opt2_Q2"], row["Pre_Opt3_Q2"]], index=None, key="p2")
                
                st.divider()
                c1, c2 = st.columns(2)
                with c1: class_code = st.text_input("Class Code (CRIM171)")
                with c2: student_id = st.text_input("Your Initials")

                if st.button("ENTER THE VAULT ⚡", use_container_width=True):
                    if not class_code or not student_id or p1 is None or p2 is None:
                        st.warning("Please complete all questions to proceed.")
                    else:
                        # NY Time Offset logic
                        ny_now = datetime.utcnow() - timedelta(hours=4)
                        st.session_state.update({
                            "class_code": class_code, "student_id": student_id,
                            "ans_pre1": p1, "ans_pre2": p2, 
                            "start_time": ny_now, "step": "vault_content"
                        })
                        st.rerun()

            # --- STEP 2: VIDEO & FEEDBACK ---
            elif st.session_state.step == "vault_content":
                st.title(f"🎬 {st.session_state.active_topic}")
                v_url = str(row.get("Video_URL", "")).strip()
                st.video(v_url if v_url.startswith("http") else "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                
                st.divider()
                st.write("### 🧠 Pulse Check")
                pst1 = st.radio(row["Post_Q1"], [row["Post_Opt1"], row["Post_Opt2"], row["Post_Opt3"]], index=None, key="pst1")
                pst2 = st.radio(row["Post_Q2"], [row["Post_Opt1_Q2"], row["Post_Opt2_Q2"], row["Post_Opt3_Q2"]], index=None, key="pst2")
                
                st.divider()
                # NEW DISCRETE NPS SELECTOR
                st.write("### ⚡ Rate this Vault Story")
                n_cols = st.columns(5)
                if n_cols[0].button("😴\nBoring", use_container_width=True): st.session_state.nps_score = 2
                if n_cols[1].button("😐\nOkay", use_container_width=True): st.session_state.nps_score = 5
                if n_cols[2].button("😎\nCool", use_container_width=True): st.session_state.nps_score = 8
                if n_cols[3].button("🔥\nFire", use_container_width=True): st.session_state.nps_score = 9
                if n_cols[4].button("🏆\nEpic", use_container_width=True): st.session_state.nps_score = 10

                if st.session_state.nps_score:
                    st.success(f"Selected Rating: {st.session_state.nps_score}/10")

                if st.button("LOG MASTERY & FINISH 🚀", use_container_width=True):
                    if pst1 is None or pst2 is None or st.session_state.nps_score is None:
                        st.error("Please answer the Pulse Check and select a rating.")
                    else:
                        # CALC ENGAGEMENT
                        ny_end = datetime.utcnow() - timedelta(hours=4)
                        elapsed = (ny_end - st.session_state.start_time).total_seconds()
                        target_len = float(row.get("Video_Length_Sec", 85)) 
                        status = "Completed" if elapsed >= (target_len * 0.9) else "Skimmed"

                        # SCORE & LOG
                        s_pre = (1 if st.session_state.ans_pre1 == row["Pre_A1"] else 0) + (1 if st.session_state.ans_pre2 == row["Pre_A2"] else 0)
                        s_post = (1 if pst1 == row["Post_A1"] else 0) + (1 if pst2 == row["Post_A2"] else 0)
                        
                        res = {"Timestamp": [ny_end], "Class": [st.session_state.class_code], 
                               "Student": [st.session_state.student_id], "Topic": [st.session_state.active_topic],
                               "Pre_Score": [s_pre], "Post_Score": [s_post], "Lift": [s_post - s_pre], 
                               "NPS": [st.session_state.nps_score], "Duration_Sec": [int(elapsed)], "Status": [status]}
                        
                        pd.DataFrame(res).to_csv("vault_data.csv", mode='a', header=not os.path.exists("vault_data.csv"), index=False)
                        
                        if status == "Completed":
                            st.balloons()
                            st.markdown(f'<div class="mastery-badge"><div class="badge-initials">{st.session_state.student_id.upper()}</div>CERTIFIED MASTER<br>LIFT: +{s_post - s_pre}</div>', unsafe_allow_html=True)
                        else:
                            st.warning("Mastery Logged! (Try watching the full video next time for a badge!)")
        else:
            st.info("Select a story above to begin.")

    # --- 5. ADMIN (PASSWORD: vault2026) ---
    elif nav == "Pilot Summary (Admin)":
        st.title("🔐 Admin Dashboard")
        if st.text_input("Access Key", type="password") == "vault2026":
            if os.path.isfile("vault_data.csv"):
                df = pd.read_csv("vault_data.csv")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Learners", len(df))
                c2.metric("Avg Lift", f"+{df['Lift'].mean():.2f}")
                c3.metric("Avg Time", f"{int(df['Duration_Sec'].mean())}s")
                c4.metric("NPS", int(df['NPS'].mean()))
                st.dataframe(df.sort_values(by="Timestamp", ascending=False), use_container_width=True)
                st.download_button("Export CSV", df.to_csv(index=False), "vault_pilot_data.csv")
            else: st.info("No data yet.")
