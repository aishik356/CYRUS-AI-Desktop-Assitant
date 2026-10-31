import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
import vlc

from services.startup_check import (
    StartupCheck,
    check_startup_requirements,
    startup_check_warnings,
)
from config.settings import load_api_settings


class StartupCheckTests(unittest.TestCase):
    def test_reports_ready_when_runtime_requirements_are_available(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            voice_directory = root / "voices"
            voice_directory.mkdir()
            model_path = voice_directory / "en_GB-alan-medium.onnx"
            config_path = voice_directory / "en_GB-alan-medium.onnx.json"
            model_path.touch()
            config_path.touch()
            vlc_instance = MagicMock()
            response = MagicMock()
            response.json.return_value = {
                "models": [{"name": "llama3.2:3b"}]
            }
            with (
                patch(
                    "services.startup_check.voice_asset_paths",
                    return_value=(model_path, config_path),
                ),
                patch("services.startup_check.vlc.Instance", return_value=vlc_instance),
                patch(
                    "services.startup_check.sr.Microphone.list_microphone_names",
                    return_value=["Default microphone"],
                ),
                patch("services.startup_check.sounddevice.query_devices"),
                patch("services.startup_check.load_api_settings", return_value={}),
                patch("services.startup_check.requests.get", return_value=response),
            ):
                checks = check_startup_requirements()

        self.assertEqual(len(checks), 5)
        self.assertTrue(all(check.ready for check in checks))
        vlc_instance.release.assert_called_once()

    def test_setup_only_checks_features_that_were_selected(self):
        features = {
            "alan_voice": False,
            "microphone_input": False,
            "web_news": True,
            "vlc_music": False,
            "screen_analysis": True,
        }
        response = MagicMock()
        response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
        with (
            patch("services.startup_check.load_installed_features", return_value=features),
            patch("services.startup_check.load_api_settings", return_value={}),
            patch("services.startup_check.requests.get", return_value=response),
            patch(
                "services.startup_check.sr.Microphone.list_microphone_names"
            ) as microphone_check,
            patch("services.startup_check.vlc.Instance") as vlc_check,
            patch("services.startup_check.sounddevice.query_devices") as speakers_check,
        ):
            checks = check_startup_requirements()

        self.assertEqual({check.name for check in checks}, {"AI backend"})
        microphone_check.assert_not_called()
        vlc_check.assert_not_called()
        speakers_check.assert_not_called()

    def test_reports_missing_assets_and_devices_as_actionable_warnings(self):
        vlc_instance = MagicMock(return_value=None)
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            patch(
                "services.startup_check.voice_asset_paths",
                return_value=(
                    Path(temporary_directory) / "missing.onnx",
                    Path(temporary_directory) / "missing.onnx.json",
                ),
            ),
            patch("services.startup_check.vlc.Instance", vlc_instance),
            patch(
                "services.startup_check.sr.Microphone.list_microphone_names",
                return_value=[],
            ),
            patch(
                "services.startup_check.sounddevice.query_devices",
                side_effect=OSError("no output device"),
            ),
            patch("services.startup_check.load_api_settings", return_value={}),
            patch(
                "services.startup_check.requests.get",
                side_effect=requests.ConnectionError("Ollama is offline"),
            ),
        ):
            checks = check_startup_requirements()

        warnings = startup_check_warnings(checks)
        self.assertEqual(
            {check.name for check in warnings},
            {"Alan voice", "VLC player", "Microphone", "Speakers", "AI backend"},
        )
        self.assertTrue(all(check.details for check in warnings))

    def test_openrouter_configuration_is_checked_without_network_access(self):
        with (
            patch("services.startup_check.vlc.Instance", return_value=MagicMock()),
            patch(
                "services.startup_check.sr.Microphone.list_microphone_names",
                return_value=["Default microphone"],
            ),
            patch("services.startup_check.sounddevice.query_devices"),
            patch(
                "services.startup_check.load_api_settings",
                return_value={"ai_backend": "openrouter", "openrouter_api_key": ""},
            ),
            patch.dict(
                "os.environ",
                {
                    "CYRUS_AI_BACKEND": "openrouter",
                    "OPENROUTER_API_KEY": "",
                },
                clear=False,
            ),
            patch("services.startup_check.requests.get") as request,
        ):
            checks = check_startup_requirements()

        ai_check = next(check for check in checks if check.name == "AI backend")
        self.assertFalse(ai_check.ready)
        self.assertIn("OPENROUTER_API_KEY", ai_check.details)
        request.assert_not_called()

    def test_vlc_load_error_becomes_an_actionable_setup_warning(self):
        with (
            patch(
                "services.startup_check.vlc.Instance",
                side_effect=vlc.VLCException("VLC runtime missing"),
            ),
            patch(
                "services.startup_check.sr.Microphone.list_microphone_names",
                return_value=["Default microphone"],
            ),
            patch("services.startup_check.sounddevice.query_devices"),
            patch(
                "services.startup_check.load_api_settings",
                return_value={
                    "ai_backend": "openrouter",
                    "openrouter_api_key": "test-key",
                },
            ),
        ):
            checks = check_startup_requirements()

        vlc_check = next(check for check in checks if check.name == "VLC player")
        self.assertFalse(vlc_check.ready)
        self.assertIn("Install VLC", vlc_check.details)

    def test_startup_warning_filter_preserves_only_failed_checks(self):
        ready = StartupCheck("Speakers", True, "Available.")
        missing = StartupCheck("Microphone", False, "No microphone found.")

        self.assertEqual(startup_check_warnings([ready, missing]), [missing])

    def test_api_settings_prefer_user_config_without_dropping_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            user_config = root / "user" / "api_keys.json"
            legacy_config = root / "project" / "api_keys.json"
            user_config.parent.mkdir()
            legacy_config.parent.mkdir()
            user_config.write_text(
                json.dumps({"ai_backend": "openrouter"}), encoding="utf-8"
            )
            legacy_config.write_text(
                json.dumps({"ai_backend": "ollama"}), encoding="utf-8"
            )

            with (
                patch("config.settings.USER_CONFIG_PATH", user_config),
                patch("config.settings.CONFIG_PATH", legacy_config),
            ):
                self.assertEqual(
                    load_api_settings()["ai_backend"], "openrouter"
                )
                user_config.unlink()
                self.assertEqual(load_api_settings()["ai_backend"], "ollama")


if __name__ == "__main__":
    unittest.main()
