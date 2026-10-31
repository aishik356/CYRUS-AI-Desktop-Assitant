import getpass
import json
import os
from pathlib import Path

from config.settings import PROJECT_ROOT, get_user_data_dir


def _memory_directory() -> Path:
    return get_user_data_dir()


MEMORY_DIR = _memory_directory()
MEMORY_FILE = MEMORY_DIR / "memory.json"
LEGACY_MEMORY_FILE = PROJECT_ROOT / "data" / "cyrus_memory.json"


def _local_user_name() -> str:
    try:
        return os.getlogin()
    except OSError:
        return getpass.getuser() or "User"


DEFAULT_MEMORY = {
    "identity": {
        "user_name": _local_user_name(),
        "assistant_name": "CYRUS",
        "role": "Personal desktop assistant",
    },
    "preferences": {
        "conciseness": "balanced",
        "tone": "helpful",
    },
    "notes": [],
}


def load_memory() -> dict:
    """Loads this operating-system user's local memory, migrating legacy data once."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    if not MEMORY_FILE.exists():
        if LEGACY_MEMORY_FILE.exists():
            try:
                with LEGACY_MEMORY_FILE.open("r", encoding="utf-8") as memory_file:
                    legacy_memory = json.load(memory_file)
                if not isinstance(legacy_memory, dict):
                    raise ValueError(f"{LEGACY_MEMORY_FILE} must contain a JSON object.")
                save_memory(legacy_memory)
                return legacy_memory
            except (OSError, json.JSONDecodeError, ValueError) as e:
                print(f"[Memory Error]: Failed to migrate legacy memory ({e}).")
        save_memory(DEFAULT_MEMORY)
        return DEFAULT_MEMORY

    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as memory_file:
            memory = json.load(memory_file)
        if not isinstance(memory, dict):
            raise ValueError(f"{MEMORY_FILE} must contain a JSON object.")
        return memory
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"[Memory Error]: Failed to read memory file ({e}).")
        return DEFAULT_MEMORY


def save_memory(data: dict) -> None:
    """Writes user-specific memory to local storage."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with MEMORY_FILE.open("w", encoding="utf-8") as memory_file:
            json.dump(data, memory_file, indent=4)
    except OSError as e:
        print(f"[Memory Error]: Failed to save memory ({e}).")


def add_note(fact: str) -> str:
    """Appends a new note or personal fact to the persistent memory store."""
    mem = load_memory()
    notes = mem.setdefault("notes", [])
    fact_clean = fact.strip()
    if fact_clean and fact_clean not in notes:
        notes.append(fact_clean)
        save_memory(mem)
        return f"Stored in long-term memory: '{fact_clean}'."
    return "Memory already contains this information."


def format_memory_for_prompt() -> str:
    """Formats current memory entries into a structured prompt injection."""
    mem = load_memory()
    lines = ["\n[LONG-TERM MEMORY CONTEXT]"]

    for category, details in mem.items():
        if isinstance(details, dict):
            entries = ", ".join([f"{key}: {value}" for key, value in details.items()])
            lines.append(f"- {category.title()}: {entries}")
        elif isinstance(details, list) and details:
            lines.append(f"- {category.title()}: {'; '.join(details)}")

    lines.append("[END OF MEMORY]\n")
    return "\n".join(lines)
