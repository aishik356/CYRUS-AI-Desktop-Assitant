import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.features import DEFAULT_FEATURES, load_installed_features


class InstalledFeatureTests(unittest.TestCase):
    def test_source_and_portable_default_enables_optional_features(self):
        with patch("config.features.FEATURES_CONFIG_PATH", Path("missing.json")):
            self.assertEqual(load_installed_features(), DEFAULT_FEATURES)

    def test_installer_feature_selection_is_loaded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            features_path = Path(temporary_directory) / "features.json"
            features_path.write_text(
                json.dumps(
                    {
                        "alan_voice": True,
                        "microphone_input": False,
                        "web_news": True,
                        "vlc_music": False,
                        "screen_analysis": True,
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "config.features.FEATURES_CONFIG_PATH", features_path
            ):
                features = load_installed_features()

        self.assertTrue(features["alan_voice"])
        self.assertFalse(features["microphone_input"])
        self.assertFalse(features["vlc_music"])
        self.assertTrue(features["screen_analysis"])

    def test_invalid_installer_settings_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            features_path = Path(temporary_directory) / "features.json"
            features_path.write_text("{", encoding="utf-8")
            with (
                patch("config.features.FEATURES_CONFIG_PATH", features_path),
                patch("builtins.print") as print_error,
            ):
                features = load_installed_features()

        self.assertFalse(any(features.values()))
        print_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
