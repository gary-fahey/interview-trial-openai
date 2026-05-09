# interview_logic.py
# Manages module state, system prompt assembly, and safety screening.
# The app.py calls these functions — it does not manage state directly.

import streamlit as st
import config

# ── Module sequence ───────────────────────────────────────────────────────────
MODULE_SEQUENCE = [
    "orientation",
    "module1",
    "module2",
    "module3",
    "summary",
]

def initialise_interview_state():
    """Called once at session start to set up all interview state."""
    if "current_module" not in st.session_state:
        st.session_state.current_module = "orientation"
    if "module_turn_count" not in st.session_state:
        st.session_state.module_turn_count = 0
    if "interview_complete" not in st.session_state:
        st.session_state.interview_complete = False
    if "safety_triggered" not in st.session_state:
        st.session_state.safety_triggered = False
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "model_label" not in st.session_state:
        st.session_state.model_label = ""


def build_system_prompt(model_label: str) -> str:
    """
    Assembles the system prompt for the current module.
    Includes general instructions, current module instructions,
    and explicit turn count context so the AI knows when to move on.
    """
    module_key = st.session_state.current_module
    module = config.INTERVIEW_MODULES[module_key]
    turn_limit = module["turns"]
    turns_used = st.session_state.module_turn_count
    turns_remaining = max(0, turn_limit - turns_used)

    # Explicit transition instruction based on turns remaining
    if turns_remaining <= 1:
        transition_instruction = (
            "IMPORTANT: You have reached the turn limit for this module. "
            "Do NOT ask any further follow-up questions on this topic. "
            "Acknowledge what the participant has shared briefly, then "
            "move immediately to the next topic or module."
        )
    elif turns_remaining == 2:
        transition_instruction = (
            "You have one follow-up question remaining in this module. "
            "Make it count — then move on. Do not open new threads of inquiry."
        )
    else:
        transition_instruction = (
            f"You have {turns_remaining} exchanges remaining in this module "
            f"before you must move on. Use them selectively."
        )

    system = f"""{config.GENERAL_INSTRUCTIONS}

--- CURRENT MODULE: {module_key.upper()} ---
{module['prompt']}

--- TURN MANAGEMENT ---
{transition_instruction}

--- CONTEXT ---
You are operating as the AI interviewer in a research trial.
Model in use: {model_label}
Do not reveal the model name to the participant unless directly asked.
"""
    return system


def check_safety(text: str) -> bool:
    """
    Screens participant input for safety keywords BEFORE sending to the API.
    Returns True if a safety keyword is detected.
    """
    text_lower = text.lower()
    for keyword in config.SAFETY_KEYWORDS:
        if keyword in text_lower:
            return True
    return False


def advance_module_if_needed(ai_response: str):
    """
    Checks whether the AI has signalled completion of the current module
    or whether the turn limit has been reached, and advances accordingly.
    Also detects the INTERVIEW_COMPLETE signal.
    """
    # Check for interview completion signal
    if "INTERVIEW_COMPLETE" in ai_response:
        st.session_state.interview_complete = True
        return

    # Increment turn counter for current module
    st.session_state.module_turn_count += 1

    current = st.session_state.current_module
    turn_limit = config.INTERVIEW_MODULES[current]["turns"]

    # Advance if turn limit reached
    if st.session_state.module_turn_count >= turn_limit:
        _go_to_next_module()


def _go_to_next_module():
    """Moves to the next module in the sequence."""
    current = st.session_state.current_module
    idx = MODULE_SEQUENCE.index(current)

    if idx < len(MODULE_SEQUENCE) - 1:
        st.session_state.current_module = MODULE_SEQUENCE[idx + 1]
        st.session_state.module_turn_count = 0
    else:
        # Already at last module — mark complete
        st.session_state.interview_complete = True


def get_module_label() -> str:
    """Returns a display label for the current module, for the UI header."""
    current = st.session_state.current_module
    module = config.INTERVIEW_MODULES[current]
    return module.get("label", current.replace("_", " ").title())


def get_api_messages() -> list:
    """
    Returns the message list stripped to role + content only.
    Removes any extra fields (e.g. timestamps) that would cause API errors.
    """
    clean = []
    for msg in st.session_state.messages:
        clean.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    return clean
