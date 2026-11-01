import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from main import process_query
from services.greetings import contextual_greeting, holiday_greeting
from core.brain import CyrusBrain


class GreetingTests(unittest.TestCase):
    def test_greeting_uses_local_hour_and_only_the_preferred_name(self):
        local_time = datetime(
            2026, 11, 1, 15, 9, tzinfo=timezone(timedelta(hours=5, minutes=30))
        )

        with patch("services.greetings.holiday_greeting", return_value=""):
            result = contextual_greeting("Alex", local_time, "IN")

        self.assertEqual(result, "Good afternoon, Alex. How can I help?")
        self.assertNotIn("sir", result.lower())

    def test_greeting_uses_local_night_for_the_configured_timezone(self):
        local_time = datetime(2026, 11, 1, 23, 9, tzinfo=timezone.utc)

        with patch("services.greetings.holiday_greeting", return_value=""):
            result = contextual_greeting("Sam", local_time, "GB")

        self.assertEqual(result, "Good night, Sam. How can I help?")

    def test_holiday_greeting_uses_selected_country_calendar(self):
        local_time = datetime(
            2026, 12, 25, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
        )
        with patch(
            "services.greetings.holidays.country_holidays",
            return_value={local_time.date(): "Christmas Day"},
        ) as calendar:
            result = holiday_greeting(local_time, "IN")

        self.assertEqual(result, "Merry Christmas")
        calendar.assert_called_once_with("IN", years=[2026])

    def test_installed_holiday_data_recognizes_christmas(self):
        local_time = datetime(2026, 12, 25, 10, 0, tzinfo=timezone.utc)

        self.assertEqual(holiday_greeting(local_time, "US"), "Merry Christmas")

    def test_yo_is_handled_as_a_time_and_name_aware_greeting(self):
        hud = MagicMock()
        speaker = MagicMock()
        with (
            patch("main.load_user_state", return_value={"preferred_name": "Alex"}),
            patch(
                "main.contextual_greeting",
                return_value="Good afternoon, Alex. How can I help?",
            ),
            patch("main.speak_with_barge_in") as speak,
        ):
            result = process_query(
                "yo", speaker, None, MagicMock(), MagicMock(), hud
            )

        self.assertEqual(result, "Good afternoon, Alex. How can I help?")
        speak.assert_called_once_with(result, speaker, None, hud)

    @patch("core.brain.ollama.Client")
    @patch("core.brain.format_memory_for_prompt", return_value="")
    @patch(
        "core.brain.load_user_state",
        return_value={"preferred_name": "Alex", "holiday_country": "IN"},
    )
    @patch("core.brain.load_api_settings", return_value={"ai_backend": "ollama"})
    def test_brain_prompt_requires_the_exact_local_preferred_name_without_country_setting(
        self, _settings, _state, _memory, _ollama_client
    ):
        brain = CyrusBrain()

        system_prompt = brain.messages[0]["content"]
        self.assertIn("Address the user only as 'Alex'", system_prompt)
        self.assertIn("Current local date and time:", system_prompt)
        self.assertIn("spelling and typing mistakes", system_prompt)
        self.assertNotIn("holiday country", system_prompt.lower())
        self.assertNotIn("sir", system_prompt.lower())


if __name__ == "__main__":
    unittest.main()
