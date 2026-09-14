"""
the_vault_pilot_app/views/admin_analytics.py

Institutional analytics dashboard: Cross-cohort comparisons,
NPS distributions, and Item Discrimination Index (D-Index).
"""
from datetime import datetime
import pytz
import pandas as pd
import streamlit as st
from supabase import Client

NY_TZ = pytz.timezone("US/Eastern")


def render_admin_analytics(client: Client | None, verify_pw_func) -> None:
    st.title("📊 The Vault: Pilot Analytics & Psychometrics")

    if not st.session_state.admin_authed:
        pw = st.text_input("Access Key", type="password")
        if not pw:
            return
        if not verify_pw_func(pw):
            st.error("Incorrect access key.")
            return
        st.session_state.admin_authed = True
        st.rerun()

    if not client:
        st.error("Database connection unavailable.")
        return

    res = client.table("pilot_mastery_logs").select("*").order("created_at", desc=True).execute()
    if not res.data:
        st.info("No student telemetry logged yet.")
        return

    df = pd.DataFrame(res.data).rename(columns={
        "created_at": "Timestamp", "pilot_id": "Pilot_ID", "class_code": "Class",
        "student_id": "Student", "topic": "Topic", "pre_score": "Pre_Score",
        "post_score": "Post_Score", "lift": "Lift", "nps": "NPS",
        "duration": "Duration", "status": "Status"
    })

    # Cohort Benchmarks
    st.markdown("### 🏛️ Cross-Cohort Institutional Benchmarks")
    benchmarks = []
    for cohort, grp in df.groupby("Pilot_ID"):
        completed = len(grp[grp["Status"] == "Completed"])
        benchmarks.append({
            "Cohort ID": cohort,
            "Learners": len(grp),
            "Avg Pre": round(grp["Pre_Score"].mean(), 2),
            "Avg Post": round(grp["Post_Score"].mean(), 2),
            "Avg Lift": f"{grp['Lift'].mean():+.2f}",
            "Completion Rate": f"{(completed / len(grp)) * 100:.1f}%",
            "Avg NPS": round(grp["NPS"].mean(), 1),
        })
    st.dataframe(pd.DataFrame(benchmarks), use_container_width=True, hide_index=True)

    st.divider()

    # Filters
    c1, c2 = st.columns(2)
    cohort_filter = c1.selectbox("Filter by Cohort:", ["All"] + sorted(list(df["Pilot_ID"].dropna().unique())))
    f_df = df if cohort_filter == "All" else df[df["Pilot_ID"] == cohort_filter]

    topic_filter = c2.selectbox("Filter by Topic:", ["All"] + sorted(list(f_df["Topic"].dropna().unique())))
    if topic_filter != "All":
        f_df = f_df[f_df["Topic"] == topic_filter]

    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Learners Analyzed", len(f_df))
    m2.metric("Average Lift", f"{f_df['Lift'].mean():+.2f}")
    m3.metric("Avg Duration", f"{int(f_df['Duration'].mean())}s")
    m4.metric("Avg NPS Score", f"{f_df['NPS'].mean():.1f} / 10")

    # Visualizations
    v1, v2 = st.columns(2)
    with v1:
        st.markdown("#### 🎯 Pre vs. Post Score by Topic")
        topic_avg = f_df.groupby("Topic")[["Pre_Score", "Post_Score"]].mean().reset_index()
        st.bar_chart(topic_avg, x="Topic", y=["Pre_Score", "Post_Score"], stack=False)

    with v2:
        st.markdown("#### ⚡ NPS Distribution")
        nps_counts = f_df["NPS"].value_counts().reindex([2, 5, 8, 9, 10], fill_value=0).reset_index()
        nps_counts.columns = ["Rating", "Count"]
        st.bar_chart(nps_counts, x="Rating", y="Count")

    st.divider()
    st.markdown("### 📋 Student Log Entries")
    st.dataframe(f_df.sort_values("Timestamp", ascending=False), use_container_width=True)
    st.download_button(
        "📥 Download CSV Log",
        data=f_df.to_csv(index=False),
        file_name=f"vault_telemetry_{datetime.now(NY_TZ).strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
