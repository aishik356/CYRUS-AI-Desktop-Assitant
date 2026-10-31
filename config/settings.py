import os
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = (
    Path(sys._MEIPASS)
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
APP_DIRECTORY = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else PROJECT_ROOT
)
CONFIG_PATH = PROJECT_ROOT / "config" / "api_keys.json"
load_dotenv(APP_DIRECTORY / ".env", override=False)


def get_user_data_dir() -> Path:
    configured_directory = os.getenv("CYRUS_MEMORY_DIR")
    if configured_directory:
        return Path(configured_directory).expanduser()
    if os.name == "nt":
        base_directory = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base_directory:
            return Path(base_directory) / "CYRUS"
    base_directory = os.getenv("XDG_DATA_HOME")
    if base_directory:
        return Path(base_directory) / "cyrus"
    return Path.home() / ".local" / "share" / "cyrus"


def get_user_voice_dir() -> Path:
    if os.name == "nt":
        base_directory = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base_directory:
            return Path(base_directory) / "CYRUS" / "voices"
    return get_user_data_dir() / "voices"


USER_CONFIG_PATH = get_user_data_dir() / "api_keys.json"


def load_api_settings() -> dict:
    config_path = (
        USER_CONFIG_PATH if USER_CONFIG_PATH.exists() else CONFIG_PATH
    )
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as config_file:
        settings = json.load(config_file)
    if not isinstance(settings, dict):
        raise ValueError(f"{config_path} must contain a JSON object.")
    return settings


WAKE_WORD = "cyrus"
SAMPLE_RATE = 24000
RECORD_SECONDS = 4
LLM_MODEL = "llama3.2:3b"
OLLAMA_MODEL = LLM_MODEL

SYSTEM_PROMPT = (
    "You are CYRUS, a tactical military-grade operating system assistant. "
    "Maintain an even, calm, professional, and consistent tone at all times. "
    "Do not use poetic or overly dramatic phrasing. "
    "Keep responses concise (1 to 2 sentences max) and grounded."
)