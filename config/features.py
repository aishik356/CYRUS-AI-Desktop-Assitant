import json

from config.settings import APP_DIRECTORY


FEATURES_CONFIG_PATH = APP_DIRECTORY / "features.json"
DEFAULT_FEATURES = {
    "alan_voice": True,
    "microphone_input": True,
    "web_news": True,
    "vlc_music": True,
    "screen_analysis": True,
}


def load_installed_features() -> dict[str, bool]:
    if not FEATURES_CONFIG_PATH.exists():
        return DEFAULT_FEATURES.copy()

    try:
        with FEATURES_CONFIG_PATH.open("r", encoding="utf-8") as feature_file:
            configured_features = json.load(feature_file)
    except (OSError, json.JSONDecodeError) as error:
        print(
            f"[Feature Configuration Error]: Could not read "
            f"{FEATURES_CONFIG_PATH}: {error}"
        )
        return {name: False for name in DEFAULT_FEATURES}

    if not isinstance(configured_features, dict):
        print(
            f"[Feature Configuration Error]: {FEATURES_CONFIG_PATH} "
            "must contain a JSON object."
        )
        return {name: False for name in DEFAULT_FEATURES}

    invalid_features = [
        name
        for name, enabled in configured_features.items()
        if name in DEFAULT_FEATURES and not isinstance(enabled, bool)
    ]
    if invalid_features:
        print(
            f"[Feature Configuration Error]: Feature values must be boolean: "
            f"{', '.join(invalid_features)}."
        )
        return {name: False for name in DEFAULT_FEATURES}

    return {
        name: configured_features.get(name, default)
        for name, default in DEFAULT_FEATURES.items()
    }


def is_feature_enabled(name: str) -> bool:
    if name not in DEFAULT_FEATURES:
        raise ValueError(f"Unknown CYRUS feature: {name}")
    return load_installed_features()[name]
