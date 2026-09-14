"""
the_vault_pilot_app/views/curriculum_studio.py

AI Authoring Studio: Invokes Gemini with psychometric guardrails
and publishes structured modules directly into Supabase.
"""
import streamlit as st
from supabase import Client

try:
    from Utils.vault_curriculum_prompts import VaultModuleSchema
    from Utils.generate_and_ingest import generate_vault_module, ingest_module_to_supabase
    STUDIO_LOADED = True
except ImportError:
    STUDIO_LOADED = False


def clear_studio_state():
    st.session_state["studio_topic"] = ""
    st.session_state["studio_url"] = ""
    st.session_state["studio_obj"] = ""
    st.session_state.pop("staging_module", None)


def render_curriculum_studio(client: Client | None, verify_pw_func) -> None:
    st.title("⚡ Curriculum Studio & Generation")
    st.caption("Anti-Ceiling & Narrative-Anchored Module Creator.")

    if not STUDIO_LOADED:
        st.error("⚠️ Utils components could not be loaded. Please ensure the Utils/ directory exists.")
        return

    if not st.session_state.studio_authed:
        pw = st.text_input("Authoring Access Key", type="password", key="auth_studio_pw")
        if not pw:
            return
        if not verify_pw_func(pw):
            st.error("Incorrect key.")
            return
        st.session_state.studio_authed = True
        st.rerun()

    st.session_state.setdefault("studio_topic", "")
    st.session_state.setdefault("studio_url", "")
    st.session_state.setdefault("studio_obj", "")

    top1, top2 = st.columns([5, 1])
    top1.subheader("1. Module Configuration")
    if top2.button("🔄 Clear Form", use_container_width=True):
        clear_studio_state()
        st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        pilot_id = st.text_input("Target Cohort", value=st.session_state.active_pilot_id)
        topic = st.text_input("Story Title", key="studio_topic", placeholder="e.g. Desert of Thirst")
        video_url = st.text_input("Video URL", key="studio_url", placeholder="https://youtube.com/...")
        objective = st.text_area(
            "Learning Objective & Misconception",
            key="studio_obj",
            height=120,
            placeholder="Explain the intuitive fallacy to break down..."
        )
        gen_btn = st.button("Generate Module 🧠", type="primary", use_container_width=True)

    with c2:
        st.subheader("2. Psychometric Constraints")
        st.markdown(r"""
        * **Diagnostic Baseline:** No dictionary definitions. Target **40%-60% pass rate**.
        * **Domain-Locked:** Post-test questions strictly evaluate events from the story.
        * **Schema Conformance:** Mapped to Supabase column standards automatically.
        """)

    if gen_btn:
        if not topic.strip() or not objective.strip():
            st.error("Please enter a Topic and an Objective.")
        else:
            with st.spinner("Synthesizing script and psychometrics via Gemini..."):
                try:
                    mod = generate_vault_module(topic.strip(), pilot_id.strip(), objective.strip())
                    st.session_state.staging_module = mod
                    st.session_state.staging_video_url = video_url.strip()
                    st.session_state.staging_pilot_id = pilot_id.strip()
                    st.success("Module generated and validated against Pydantic schema!")
                except Exception as e:
                    st.error(f"Generation error: {e}")

    # Preview & Publish
    if "staging_module" in st.session_state:
        st.divider()
        mod: VaultModuleSchema = st.session_state.staging_module
        st.subheader(f"3. Preview: {mod.topic}")

        with st.expander("🎬 View 85s Script", expanded=True):
            st.write(mod.video_script)

        p1, p2 = st.columns(2)
        with p1:
            st.markdown("#### 🔍 Pre-Test (Diagnostic)")
            st.markdown(f"**Q1:** {mod.pre_q1.question}")
            st.caption(f"A: {mod.pre_q1.opt1} | B: {mod.pre_q1.opt2} | C: {mod.pre_q1.opt3}")
            st.info(f"Key: {mod.pre_q1.correct_answer}")

            st.markdown(f"**Q2:** {mod.pre_q2.question}")
            st.caption(f"A: {mod.pre_q2.opt1} | B: {mod.pre_q2.opt2} | C: {mod.pre_q2.opt3}")
            st.info(f"Key: {mod.pre_q2.correct_answer}")

        with p2:
            st.markdown("#### 🧠 Post-Test (Retrieval)")
            st.markdown(f"**Q1:** {mod.post_q1.question}")
            st.caption(f"A: {mod.post_q1.opt1} | B: {mod.post_q1.opt2} | C: {mod.post_q1.opt3}")
            st.success(f"Key: {mod.post_q1.correct_answer}")

            st.markdown(f"**Q2:** {mod.post_q2.question}")
            st.caption(f"A: {mod.post_q2.opt1} | B: {mod.post_q2.opt2} | C: {mod.post_q2.opt3}")
            st.success(f"Key: {mod.post_q2.correct_answer}")

        if st.button("🚀 Publish to TheVault_CMS_Core", type="primary", use_container_width=True):
            with st.spinner("Writing to Supabase..."):
                try:
                    ingest_module_to_supabase(
                        module=mod,
                        pilot_id=st.session_state.staging_pilot_id,
                        video_url=st.session_state.get("staging_video_url", "")
                    )
                    st.balloons()
                    st.success(f"Published '{mod.topic}' successfully!")
                    clear_studio_state()
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to publish: {e}")
