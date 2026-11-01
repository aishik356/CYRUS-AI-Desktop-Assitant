import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from config.settings import load_api_settings, save_api_settings
from core.brain import CyrusBrain
from services.system_tools import (
    DEFAULT_OPENROUTER_FREE_MODEL,
    DEFAULT_OPENROUTER_PAID_MODEL,
    configure_ollama,
    configure_openrouter,
    verify_openrouter_key,
)


class ProviderConfigurationTests(unittest.TestCase):
    @patch("services.system_tools.requests.get")
    def test_openrouter_key_verification_uses_bearer_auth_and_detects_free_tier(
        self, get
    ):
        response = MagicMock()
        response.json.return_value = {
            "data": {"limit_remaining": 0, "usage": 1}
        }
        get.return_value = response

        self.assertEqual(verify_openrouter_key("test-key"), "free")
        get.assert_called_once_with(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": "Bearer test-key"},
            timeout=10,
        )
        response.raise_for_status.assert_called_once()

    @patch("services.system_tools.save_api_settings")
    @patch("services.system_tools.load_api_settings")
    @patch("services.system_tools.verify_openrouter_key", return_value="free")
    def test_free_key_is_saved_with_free_model_lock(
        self, verify, load_settings, save_settings
    ):
        load_settings.return_value = {
            "openrouter_chat_model": DEFAULT_OPENROUTER_PAID_MODEL
        }

        settings = configure_openrouter("test-key")

        self.assertEqual(settings["ai_backend"], "openrouter")
        self.assertEqual(settings["openrouter_key_tier"], "free")
        self.assertEqual(
            settings["openrouter_chat_model"], DEFAULT_OPENROUTER_FREE_MODEL
        )
        self.assertEqual(settings["openrouter_api_key"], "test-key")
        verify.assert_called_once_with("test-key")
        save_settings.assert_called_once_with(settings)

    @patch("services.system_tools.save_api_settings")
    @patch("services.system_tools.load_api_settings", return_value={})
    @patch("services.system_tools.verify_openrouter_key", return_value="paid")
    def test_paid_key_uses_premium_default_model(
        self, _verify, _load_settings, _save_settings
    ):
        with patch.dict("os.environ", {"OPENROUTER_CHAT_MODEL": ""}):
            settings = configure_openrouter("test-key")

        self.assertEqual(settings["openrouter_key_tier"], "paid")
        self.assertEqual(
            settings["openrouter_chat_model"], DEFAULT_OPENROUTER_PAID_MODEL
        )

    @patch("services.system_tools.save_api_settings")
    @patch("services.system_tools.load_api_settings", return_value={})
    @patch("services.system_tools.requests.get")
    def test_ollama_is_checked_and_host_is_saved(
        self, get, _load_settings, save_settings
    ):
        response = MagicMock()
        get.return_value = response

        settings = configure_ollama()

        get.assert_called_once_with("http://localhost:11434", timeout=3)
        response.raise_for_status.assert_called_once()
        self.assertEqual(settings["ollama_host"], "http://localhost:11434")
        save_settings.assert_called_once_with(settings)

    def test_portable_api_settings_are_saved_in_runtime_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime_directory = Path(temporary_directory)
            with (
                patch("config.settings.PORTABLE_MODE", True),
                patch("config.settings.APP_DIRECTORY", runtime_directory),
            ):
                save_api_settings({"ai_backend": "openrouter"})
                self.assertEqual(
                    load_api_settings(), {"ai_backend": "openrouter"}
                )
                self.assertTrue((runtime_directory / "config.json").is_file())

    @patch("core.brain.ollama.Client")
    @patch("core.brain.format_memory_for_prompt", return_value="")
    @patch("core.brain.load_user_state", return_value={})
    @patch("core.brain.load_api_settings")
    def test_portable_brain_locks_model_to_free_tier(
        self, load_settings, _user_state, _memory, _ollama_client
    ):
        load_settings.return_value = {
            "ai_backend": "ollama",
            "openrouter_api_key": "test-key",
            "openrouter_key_tier": "free",
            "openrouter_chat_model": DEFAULT_OPENROUTER_PAID_MODEL,
        }
        with patch("core.brain.PORTABLE_MODE", True):
            brain = CyrusBrain()

        self.assertEqual(brain.backend, "openrouter")
        self.assertEqual(brain.openrouter_model, DEFAULT_OPENROUTER_FREE_MODEL)

    @patch("core.brain.ollama.Client")
    @patch("core.brain.format_memory_for_prompt", return_value="")
    @patch("core.brain.load_user_state", return_value={})
    @patch("core.brain.load_api_settings")
    @patch("core.brain.requests.post")
    def test_openrouter_chat_uses_configured_bearer_key(
        self, post, load_settings, _user_state, _memory, _ollama_client
    ):
        load_settings.return_value = {
            "ai_backend": "openrouter",
            "openrouter_api_key": "test-key",
            "openrouter_key_tier": "paid",
        }
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": "Ready."}}]
        }
        post.return_value = response
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            brain = CyrusBrain()

        self.assertEqual(brain._think_with_openrouter(), "Ready.")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-key",
        )

    @patch("core.brain.ollama.Client")
    @patch("core.brain.format_memory_for_prompt", return_value="")
    @patch("core.brain.load_user_state", return_value={})
    @patch("core.brain.load_api_settings")
    @patch(
        "core.brain.requests.post",
        side_effect=requests.ConnectionError("endpoint unreachable"),
    )
    def test_openrouter_connection_error_notifies_offline_handler(
        self, _post, load_settings, _user_state, _memory, _ollama_client
    ):
        load_settings.return_value = {
            "ai_backend": "openrouter",
            "openrouter_api_key": "test-key",
            "openrouter_key_tier": "paid",
        }
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            brain = CyrusBrain()
        network_errors = []
        brain.on_network_error = network_errors.append

        brain.think("Hello")

        self.assertEqual(len(network_errors), 1)
        self.assertIsInstance(network_errors[0], requests.ConnectionError)
        self.assertTrue(brain.offline_mode)

    @patch("core.brain.ollama.Client")
    @patch("core.brain.format_memory_for_prompt", return_value="")
    @patch("core.brain.load_user_state", return_value={"offline_mode": True})
    @patch("core.brain.load_api_settings", return_value={})
    def test_portable_offline_brain_can_start_without_a_verified_key(
        self, _load_settings, _user_state, _memory, _ollama_client
    ):
        with (
            patch("core.brain.PORTABLE_MODE", True),
            patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}),
        ):
            brain = CyrusBrain()

        self.assertEqual(brain.backend, "openrouter")
        self.assertTrue(brain.offline_mode)
        self.assertEqual(brain.openrouter_api_key, "")


if __name__ == "__main__":
    unittest.main()
