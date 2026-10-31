import os
from dataclasses import dataclass

import requests
import sounddevice
import speech_recognition as sr
import vlc

from core.speaker import voice_asset_paths
from config.settings import (
    LLM_MODEL,
    get_user_data_dir,
    load_api_settings,
)
from config.features import load_installed_features
from config.user_state import load_user_state


@dataclass(frozen=True)
class StartupCheck:
    name: str
    ready: bool
    details: str


def check_startup_requirements() -> list[StartupCheck]:
    checks = []
    features = load_installed_features()

    if features["alan_voice"]:
        model_path, config_path = voice_asset_paths()
        if model_path.is_file() and config_path.is_file():
            checks.append(
                StartupCheck("Alan voice", True, "Voice model and configuration found.")
            )
        else:
            missing = [
                path.name for path in (model_path, config_path) if not path.is_file()
            ]
            checks.append(
                StartupCheck(
                    "Alan voice",
                    False,
                    f"Missing {', '.join(missing)}. Use the optional installer download "
                    f"or put both files in {model_path.parent}.",
                )
            )

    if features["vlc_music"]:
        try:
            vlc_instance = vlc.Instance("--no-video", "--quiet")
            if vlc_instance is None:
                raise OSError("VLC could not create a media instance.")
            vlc_instance.release()
            checks.append(
                StartupCheck("VLC player", True, "VLC runtime is available.")
            )
        except (vlc.VLCException, OSError, AttributeError) as error:
            checks.append(
                StartupCheck(
                    "VLC player",
                    False,
                    f"{error} Install VLC and restart CYRUS.",
                )
            )

    if features["microphone_input"]:
        try:
            microphones = sr.Microphone.list_microphone_names()
            if microphones:
                checks.append(
                    StartupCheck(
                        "Microphone",
                        True,
                        f"Found {len(microphones)} input device(s); CYRUS keeps the mic muted at startup.",
                    )
                )
            else:
                checks.append(
                    StartupCheck(
                        "Microphone",
                        False,
                        "No input device found. Voice input is unavailable; typed chat can still be used.",
                    )
                )
        except (OSError, AttributeError, ImportError) as error:
            checks.append(
                StartupCheck(
                    "Microphone",
                    False,
                    f"Could not check input devices: {error} Check your microphone and audio drivers.",
                )
            )

    if features["alan_voice"]:
        try:
            sounddevice.query_devices(kind="output")
            checks.append(
                StartupCheck("Speakers", True, "An audio output device is available.")
            )
        except (sounddevice.PortAudioError, OSError, AttributeError) as error:
            checks.append(
                StartupCheck(
                    "Speakers",
                    False,
                    f"Could not find an audio output device: {error} Check Windows sound settings.",
                )
            )

    try:
        api_settings = load_api_settings()
    except (OSError, ValueError) as error:
        checks.append(
            StartupCheck(
                "AI configuration",
                False,
                f"Could not read the AI configuration: {error} Check "
                f"{get_user_data_dir() / 'api_keys.json'}.",
            )
        )
        return checks

    backend_value = os.getenv("CYRUS_AI_BACKEND")
    if backend_value is None:
        backend_value = api_settings.get("ai_backend", "ollama")
    backend = str(backend_value).strip().lower()
    offline = os.getenv("CYRUS_OFFLINE_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    } or bool(load_user_state().get("offline_mode", False))
    if offline and backend == "openrouter":
        backend = "ollama"

    if backend == "openrouter":
        api_key = (
            os.getenv("OPENROUTER_API_KEY", "").strip()
            or str(api_settings.get("openrouter_api_key", "")).strip()
        )
        if api_key:
            checks.append(
                StartupCheck("AI backend", True, "OpenRouter is selected and an API key is configured.")
            )
        else:
            checks.append(
                StartupCheck(
                    "AI backend",
                    False,
                    "OpenRouter is selected but has no API key. Configure OPENROUTER_API_KEY in .env.",
                )
            )
    elif backend == "ollama":
        try:
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            response.raise_for_status()
            models = response.json().get("models", [])
            available_models = {
                model.get("name", "").strip()
                for model in models
                if isinstance(model, dict)
            }
            if LLM_MODEL in available_models:
                checks.append(
                    StartupCheck("AI backend", True, f"Ollama and {LLM_MODEL} are ready.")
                )
            else:
                checks.append(
                    StartupCheck(
                        "AI backend",
                        False,
                        f"Ollama is running, but {LLM_MODEL} is missing. Run `ollama pull {LLM_MODEL}`.",
                    )
                )
        except (requests.RequestException, ValueError, AttributeError, TypeError) as error:
            checks.append(
                StartupCheck(
                    "AI backend",
                    False,
                    f"Could not reach Ollama: {error} Start Ollama and run `ollama pull {LLM_MODEL}`.",
                )
            )
    else:
        checks.append(
            StartupCheck(
                "AI backend",
                False,
                f"Unsupported backend {backend!r}. Choose `ollama` or `openrouter`.",
            )
        )

    return checks


def startup_check_warnings(checks: list[StartupCheck]) -> list[StartupCheck]:
    return [check for check in checks if not check.ready]
