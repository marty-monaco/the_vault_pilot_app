"""
cms_authoring_app.py

Interactive Curriculum Studio & Psychometric Validator for The Vault.
Imports Utils/vault_curriculum_prompts.py and Utils/generate_and_ingest.py
to deliver visual module generation, previewing, and live publishing.
"""

import streamlit as st
import pandas as pd
from Utils.vault_curriculum_prompts import (
    VaultModuleSchema,
    AssessmentQuestion
)
from Utils.generate_and_ingest import (
    generate_vault_module,
    ingest_module_to_supabase
)

st.set_page_config(
    page_title="The Vault - Curriculum Studio",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ The Vault: Curriculum Studio & Ingestion")
st.caption("AI Orchestrator with Built-In Psychometric Calibration (Anti-Ceiling & Domain-Locked).")

# ---------------------------------------------------------------------------
# SIDEBAR CONFIG
# ---------------------------------------------------------------------------
st.sidebar.header("Target Pilot Configuration")
pilot_id = st.sidebar.text_input("Cohort / Pilot ID", value="WIRAPIDS_12")
video_len_sec = st.sidebar.number_input("Target Video Length (Seconds)", value=85, min_value=30, max_value=300)

# Preset learning templates for instant prototyping
PRESET_TEMPLATES = {
    "Price Controls & Scarcity": {
        "topic": "Desert of Thirst: Price Controls & Incentives",
        "objective": "Demonstrate how government-mandated price ceilings destroy producer profit incentives, creating acute shortages and black markets rather than affordable distribution.",
        "video_url": "https://youtube.com/shorts/w5kCRb99CFA"
    },
    "Opportunity Cost in Digital Media": {
        "topic": "Scarcity & Trade-Offs: The Creator Economy",
        "objective": "Illustrate that even with unlimited cloud storage and infinite ideas, human attention and creative hours remain scarce, requiring constant economic trade-offs.",
        "video_url": "https://youtube.com/shorts/qqwS9f5J4Jo"
    },
    "Assets vs. Expenses": {
        "topic": "The Drop Game: Assets & Capital Preservation",
        "objective": "Contrast disposable consumption expenses with assets that retain or grow resale capital, emphasizing risk management to avoid counterfeit depreciation.",
        "video_url": "https://youtube.com/shorts/SCrBVm60Bl0"
    }
}

selected_template = st.sidebar.selectbox("Load Example Template", ["None"] + list(PRESET_TEMPLATES.keys()))

# ---------------------------------------------------------------------------
# FORM INPUTS
# ---------------------------------------------------------------------------
c1, c2 = st.columns([1, 1])

with c1:
    st.subheader("1. Module Metadata")
    
    default_topic = ""
    default_obj = ""
    default_url = ""
    if selected_template != "None":
        default_topic = PRESET_TEMPLATES[selected_template]["topic"]
        default_obj = PRESET_TEMPLATES[selected_template]["objective"]
        default_url = PRESET_TEMPLATES[selected_template]["video_url"]

    topic = st.text_input("Module Title", value=default_topic, placeholder="e.g., Desert of Thirst")
    video_url = st.text_input("Video Watch/Shorts URL", value=default_url, placeholder="https://youtube.com/...")
    objective = st.text_area(
        "Core Learning Objective & Naive Misconception to Target",
        value=default_obj,
        height=140,
        placeholder="Explain what intuition breaks down and the exact economic mechanism to dramatize..."
    )

    generate_btn = st.button("Generate Calibrated Curriculum 🧠", type="primary", use_container_width=True)

with c2:
    st.subheader("2. Psychometric Rules Enforced")
    st.markdown("""
    * **Pre-Test Diagnostic (No Ceiling Effect):** Banned from testing dictionary definitions. Probes baseline intuition to target **40%–60% baseline pass rate**.
    * **Post-Test Retrieval (No Domain Jumps):** Strictly locked inside the generated narrative. Targets **80%–95% post pass rate**.
    * **Distractor Hygiene:** Eliminates confusing modern buzzwords; maps cleanly to the `_Q2` database schema.
    """)

# ---------------------------------------------------------------------------
# GENERATION LOGIC
# ---------------------------------------------------------------------------
if generate_btn:
    if not topic or not objective:
        st.error("Please provide both a Module Title and a Learning Objective.")
    else:
        with st.spinner("Invoking Gemini Orchestrator with psychometric constraints..."):
            try:
                module_data: VaultModuleSchema = generate_vault_module(
                    topic=topic,
                    pilot_id=pilot_id,
                    learning_objective=objective
                )
                module_data.video_length_sec = int(video_len_sec)
                st.session_state["staging_module"] = module_data
                st.session_state["staging_video_url"] = video_url
                st.session_state["staging_pilot_id"] = pilot_id
                st.success("Module generated and validated against Pydantic schema!")
            except Exception as e:
                st.error(f"Generation failed: {e}")

# ---------------------------------------------------------------------------
# STAGING & PUBLISHING PREVIEW
# ---------------------------------------------------------------------------
if "staging_module" in st.session_state:
    st.divider()
    mod: VaultModuleSchema = st.session_state["staging_module"]

    st.subheader(f"3. Staging Review: {mod.topic}")
    
    with st.expander("🎬 View 85-Second Video Script", expanded=True):
        st.write(mod.video_script)

    col_pre, col_post = st.columns(2)

    with col_pre:
        st.markdown("#### 🔍 Pre-Assessment (Diagnostic)")
        st.markdown(f"**Q1:** {mod.pre_q1.question}")
        st.caption(f"A: {mod.pre_q1.opt1} | B: {mod.pre_q1.opt2} | C: {mod.pre_q1.opt3}")
        st.info(f"Key: {mod.pre_q1.correct_answer}")

        st.markdown(f"**Q2:** {mod.pre_q2.question}")
        st.caption(f"A: {mod.pre_q2.opt1} | B: {mod.pre_q2.opt2} | C: {mod.pre_q2.opt3}")
        st.info(f"Key: {mod.pre_q2.correct_answer}")

    with col_post:
        st.markdown("#### 🧠 Post-Assessment (Narrative-Anchored)")
        st.markdown(f"**Q1:** {mod.post_q1.question}")
        st.caption(f"A: {mod.post_q1.opt1} | B: {mod.post_q1.opt2} | C: {mod.post_q1.opt3}")
        st.success(f"Key: {mod.post_q1.correct_answer}")

        st.markdown(f"**Q2:** {mod.post_q2.question}")
        st.caption(f"A: {mod.post_q2.opt1} | B: {mod.post_q2.opt2} | C: {mod.post_q2.opt3}")
        st.success(f"Key: {mod.post_q2.correct_answer}")

    st.write("")
    if st.button("🚀 Confirm & Publish to TheVault_CMS_Core", type="primary", use_container_width=True):
        with st.spinner("Upserting record to Supabase..."):
            try:
                res = ingest_module_to_supabase(
                    module=mod,
                    pilot_id=st.session_state["staging_pilot_id"],
                    video_url=st.session_state.get("staging_video_url", "")
                )
                st.balloons()
                st.success(f"🎉 Successfully published '{mod.topic}' for pilot '{st.session_state['staging_pilot_id']}'!")
                # Clear staging state
                del st.session_state["staging_module"]
            except Exception as e:
                st.error(f"Failed to publish to database: {e}")
