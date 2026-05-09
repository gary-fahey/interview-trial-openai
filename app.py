# app.py
# Researcher Experience Trial Interview
# University of Sydney — Decision Making Differences Project
#
# Run locally:  streamlit run app.py
# Deploy:       Streamlit Community Cloud (connect GitHub repo)
# Note: OpenAI GPT-5.x models require the Responses API (client.responses.stream)
#       Older models (gpt-4o, gpt-4o-mini) use Chat Completions as fallback.

import time
import streamlit as st

import config
import interview_logic as logic
import gdrive

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Research Interview",
    page_icon=config.AVATAR_INTERVIEWER,
    layout="centered"
)

# ── Determine model from secrets ──────────────────────────────────────────────
try:
    INTERVIEW_MODEL = st.secrets["INTERVIEW_MODEL"].lower().strip()
except KeyError:
    st.error("INTERVIEW_MODEL not set in secrets. Please add it to your Streamlit secrets.")
    st.stop()

if "claude" in INTERVIEW_MODEL:
    API = "anthropic"
    MODEL_LABEL = "CLAUDE"
    MODEL_DISPLAY = "Claude (Anthropic)"
    import anthropic
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
elif "openai" in INTERVIEW_MODEL:
    API = "openai"
    MODEL_LABEL = "OPENAI"
    MODEL_DISPLAY = "ChatGPT (OpenAI)"
    from openai import OpenAI
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error(f"Unrecognised INTERVIEW_MODEL value: '{INTERVIEW_MODEL}'. Use 'claude' or 'openai'.")
    st.stop()

# ── Session state initialisation ──────────────────────────────────────────────
logic.initialise_interview_state()

if "session_start" not in st.session_state:
    st.session_state.session_start = time.time()
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 0
st.session_state.model_label = MODEL_LABEL

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_badge = st.columns([0.78, 0.22])
with col_title:
    st.markdown("#### Research Interview")
with col_badge:
    colour = "#7F77DD" if API == "anthropic" else "#10A37F"
    st.markdown(
        f'<div style="background:{colour};color:white;padding:4px 10px;'
        f'border-radius:12px;font-size:12px;text-align:center;margin-top:4px;">'
        f'{MODEL_DISPLAY}</div>',
        unsafe_allow_html=True
    )

st.divider()

# ── Safety triggered state ────────────────────────────────────────────────────
if st.session_state.safety_triggered:
    st.warning(config.SAFETY_MESSAGE)
    st.stop()

# ── Interview complete state ──────────────────────────────────────────────────
if st.session_state.interview_complete:
    st.success(config.COMPLETION_MESSAGE)
    st.stop()

# ── Display conversation history ──────────────────────────────────────────────
for message in st.session_state.messages:
    avatar = (
        config.AVATAR_INTERVIEWER
        if message["role"] == "assistant"
        else config.AVATAR_RESPONDENT
    )
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])


# ── Helper: OpenAI streaming (Responses API with Chat Completions fallback) ───
def openai_stream(system: str, messages: list) -> str:
    """
    Streams a response from OpenAI. Uses the Responses API for GPT-5.x models,
    falls back to Chat Completions for older models (gpt-4o, gpt-4o-mini).
    Must be called inside a st.chat_message block.
    Returns the full response text.
    """
    model = st.secrets.get("OPENAI_MODEL", "gpt-4o-mini")
    placeholder = st.empty()
    response_text = ""

    try:
        # Responses API — required for GPT-5.4, GPT-5.5 and newer
        input_messages = [{"role": "system", "content": system}] + messages
        with client.responses.stream(
            model=model,
            input=input_messages,
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
        ) as stream:
            for event in stream:
                if hasattr(event, "type"):
                    if event.type == "response.output_text.delta":
                        delta = event.delta
                        if delta:
                            response_text += delta
                            if "INTERVIEW_COMPLETE" not in response_text:
                                placeholder.markdown(response_text + "▌")

    except Exception:
        # Fallback: Chat Completions API for older models
        response_text = ""
        openai_messages = [{"role": "system", "content": system}] + messages
        stream = client.chat.completions.create(
            model=model,
            max_completion_tokens=config.MAX_OUTPUT_TOKENS,
            messages=openai_messages,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                response_text += delta
                if "INTERVIEW_COMPLETE" not in response_text:
                    placeholder.markdown(response_text + "▌")

    placeholder.markdown(
        response_text.replace("INTERVIEW_COMPLETE", "").strip()
    )
    return response_text


# ── First message: AI opens the interview ─────────────────────────────────────
if not st.session_state.messages:
    system_prompt = logic.build_system_prompt(MODEL_DISPLAY)

    with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):

        if API == "anthropic":
            placeholder = st.empty()
            opening_text = ""
            seed_messages = [{"role": "user", "content": "Please begin the interview."}]
            with client.messages.stream(
                model=st.secrets.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                max_tokens=config.MAX_OUTPUT_TOKENS,
                system=system_prompt,
                messages=seed_messages,
            ) as stream:
                for delta in stream.text_stream:
                    opening_text += delta
                    placeholder.markdown(opening_text + "▌")
            placeholder.markdown(opening_text)

        elif API == "openai":
            seed_messages = [{"role": "user", "content": "Please begin the interview."}]
            opening_text = openai_stream(system_prompt, seed_messages)

    st.session_state.messages.append({
        "role": "assistant",
        "content": opening_text
    })

# ── Main chat loop ────────────────────────────────────────────────────────────
if user_input := st.chat_input("Type your response here..."):

    # Safety screening — runs before anything else
    if logic.check_safety(user_input):
        st.session_state.safety_triggered = True
        metadata = gdrive.build_metadata(
            st.session_state.session_start,
            st.session_state.turn_count,
            safety_triggered=True,
            complete=False
        )
        gdrive.save_transcript(
            st.session_state.messages,
            MODEL_LABEL,
            metadata
        )
        st.rerun()

    # Add user message to history and display
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })
    st.session_state.turn_count += 1

    with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
        st.markdown(user_input)

    # Build system prompt for current module
    system_prompt = logic.build_system_prompt(MODEL_DISPLAY)
    api_messages = logic.get_api_messages()

    # Generate AI response
    with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):

        if API == "anthropic":
            placeholder = st.empty()
            ai_response = ""
            with client.messages.stream(
                model=st.secrets.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                max_tokens=config.MAX_OUTPUT_TOKENS,
                system=system_prompt,
                messages=api_messages,
            ) as stream:
                for delta in stream.text_stream:
                    ai_response += delta
                    if "INTERVIEW_COMPLETE" not in ai_response:
                        placeholder.markdown(ai_response + "▌")
            placeholder.markdown(
                ai_response.replace("INTERVIEW_COMPLETE", "").strip()
            )

        elif API == "openai":
            ai_response = openai_stream(system_prompt, api_messages)

    # Store AI response
    st.session_state.messages.append({
        "role": "assistant",
        "content": ai_response
    })

    # Check for module advancement or completion
    logic.advance_module_if_needed(ai_response)

    # If a new module has an opening question, inject it now
    new_module = st.session_state.current_module
    new_module_data = config.INTERVIEW_MODULES.get(new_module, {})
    opening_q = new_module_data.get("opening_question")

    if (
        opening_q
        and not st.session_state.interview_complete
        and new_module != "orientation"
        and new_module != "summary"
    ):
        already_injected = any(
            opening_q in m.get("content", "")
            for m in st.session_state.messages
        )
        if not already_injected:
            st.session_state.messages.append({
                "role": "assistant",
                "content": opening_q
            })
            with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
                st.markdown(opening_q)

    # Save transcript backup after every turn
    metadata = gdrive.build_metadata(
        st.session_state.session_start,
        st.session_state.turn_count,
        safety_triggered=False,
        complete=st.session_state.interview_complete
    )
    gdrive.save_transcript(
        st.session_state.messages,
        MODEL_LABEL,
        metadata
    )

    # If interview just completed, rerun to show completion screen
    if st.session_state.interview_complete:
        st.rerun()
