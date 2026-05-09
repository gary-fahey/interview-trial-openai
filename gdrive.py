# gdrive.py
# Saves interview transcripts to a Google Drive folder.
# Uses a service account — no OAuth flow required for participants.
# Credentials are loaded from Streamlit secrets, never from files.

import json
import time
import streamlit as st

def save_transcript(messages: list, model_label: str, metadata: dict) -> bool:
    """
    Saves the interview transcript as a JSON file to Google Drive.

    Args:
        messages:     Full message list from session state.
        model_label:  "CLAUDE" or "OPENAI" — included in the filename.
        metadata:     Dict of session metadata (start time, turn count, etc).

    Returns:
        True if saved successfully, False otherwise.
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload

        # Load credentials from Streamlit secrets
        service_account_info = json.loads(
            st.secrets["GDRIVE_SERVICE_ACCOUNT"]
        )
        folder_id = st.secrets["GDRIVE_FOLDER_ID"]

        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )

        service = build("drive", "v3", credentials=credentials)

        # Build transcript content
        transcript = {
            "metadata": metadata,
            "model": model_label,
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in messages
                if m["role"] in ("user", "assistant")
            ]
        }

        content = json.dumps(transcript, indent=2, ensure_ascii=False)

        # Filename includes model and timestamp for easy identification
        timestamp = time.strftime("%Y_%m_%d_%H_%M_%S")
        filename = f"{timestamp}_{model_label}_transcript.json"

        file_metadata = {
            "name": filename,
            "parents": [folder_id]
        }

        media = MediaInMemoryUpload(
            content.encode("utf-8"),
            mimetype="application/json",
            resumable=False
        )

        service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        return True

    except Exception as e:
        # Log to Streamlit — visible in app logs but not to participant
        print(f"[gdrive] Save failed: {e}")
        return False


def build_metadata(session_start: float, turn_count: int, 
                   safety_triggered: bool, complete: bool) -> dict:
    """Assembles session metadata for the transcript file."""
    return {
        "session_start": time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(session_start)
        ),
        "duration_seconds": round(time.time() - session_start),
        "turn_count": turn_count,
        "safety_triggered": safety_triggered,
        "interview_complete": complete,
        "study": "researcher-experience-trial",
        "ethics_ref": "2025/HE001756"
    }
