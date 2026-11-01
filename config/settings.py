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
PORTABLE_MODE = bool(
    getattr(sys, "frozen", False)
    and not (APP_DIRECTORY / "features.json").is_file()
)
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


def get_api_settings_path() -> Path:
    if PORTABLE_MODE:
        return APP_DIRECTORY / "config.json"
    return USER_CONFIG_PATH


def has_saved_api_settings() -> bool:
    return get_api_settings_path().is_file()


def load_api_settings() -> dict:
    saved_config_path = get_api_settings_path()
    config_path = saved_config_path if saved_config_path.exists() else CONFIG_PATH
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as config_file:
        settings = json.load(config_file)
    if not isinstance(settings, dict):
        raise ValueError(f"{config_path} must contain a JSON object.")
    return settings


def save_api_settings(settings: dict) -> Path:
    if not isinstance(settings, dict):
        raise ValueError("API settings must be a JSON object.")
    config_path = get_api_settings_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(config_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as config_file:
        json.dump(settings, config_file, indent=2)
        config_file.write("\n")
    temporary_path.replace(config_path)
    return config_path


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