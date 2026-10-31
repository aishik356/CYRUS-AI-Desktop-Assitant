import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from config.settings import get_user_data_dir


USER_STATE_FILE = get_user_data_dir() / "preferences.json"


def load_user_state() -> dict:
    if not USER_STATE_FILE.exists():
        return {}
    try:
        with USER_STATE_FILE.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        if not isinstance(state, dict):
            raise ValueError(f"{USER_STATE_FILE} must contain a JSON object.")
        return state
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"[User Settings Error]: Could not read {USER_STATE_FILE}: {error}")
        return {}


def save_user_state(state: dict) -> bool:
    USER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=USER_STATE_FILE.parent,
            delete=False,
            suffix=".tmp",
        ) as temporary_file:
            json.dump(state, temporary_file, indent=2)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, USER_STATE_FILE)
        return True
    except OSError as error:
        if temporary_path and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError as cleanup_error:
                print(f"[User Settings Error]: Could not clean temporary file: {cleanup_error}")
        print(f"[User Settings Error]: Could not save {USER_STATE_FILE}: {error}")
        return False
