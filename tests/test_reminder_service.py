import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.reminder_service import (
    ReminderService,
    parse_absolute_reminder_command,
)


class AbsoluteReminderTests(unittest.TestCase):
    def test_iso_date_and_time_are_parsed_with_message(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        due_at, message = parse_absolute_reminder_command(
            "remind me on 2026-10-15 at 3:00 PM that my interview is there",
            now=now,
        )

        self.assertEqual(due_at, datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(message, "my interview is there")

    def test_written_date_defaults_to_nine_am_local(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        due_at, message = parse_absolute_reminder_command(
            "remind me on 15th of October 2026 that I have an interview",
            now=now,
        )

        self.assertEqual(due_at, datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(message, "I have an interview")

    def test_month_first_date_with_comma_and_compact_time(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        due_at, message = parse_absolute_reminder_command(
            "set a reminder for October 15th, 2026 at 3PM: call the dentist",
            now=now,
        )

        self.assertEqual(due_at, datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(message, "call the dentist")

    def test_time_only_uses_the_next_local_occurrence(self):
        now = datetime(2026, 11, 1, 19, 45, tzinfo=timezone.utc)

        due_at, message = parse_absolute_reminder_command(
            "set a reminder for 7:45 to call home",
            now=now,
        )

        self.assertEqual(due_at, datetime(2026, 11, 2, 7, 45, tzinfo=timezone.utc))
        self.assertEqual(message, "call home")

    def test_duration_reminder_keeps_its_label_and_message(self):
        from services.reminder_service import parse_reminder_command

        self.assertEqual(
            parse_reminder_command("set a reminder for 5 seconds to check the oven"),
            (5, "check the oven"),
        )

    def test_short_named_duration_command_is_parsed_without_losing_its_name(self):
        from services.reminder_service import parse_reminder_command

        self.assertEqual(
            parse_reminder_command("set a reminder for 10 secs named inner"),
            (10, "inner"),
        )
        self.assertEqual(
            parse_reminder_command("set a timer for five minutes"),
            (300, "Timer"),
        )

    def test_invalid_and_past_dates_are_rejected(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with self.assertRaises(ValueError):
            parse_absolute_reminder_command("remind me on 2026-02-30 to call Alex", now)
        with self.assertRaisesRegex(ValueError, "already passed"):
            parse_absolute_reminder_command(
                "remind me on 2025-12-31 at 9 AM to call Alex", now
            )

    def test_absolute_reminder_persists_timezone_aware_due_time(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "reminders.json"
            service = ReminderService(reminder_file=path, start=False)
            due_at = datetime.now().astimezone() + timedelta(days=2)

            response = service.schedule_at(due_at, "Dentist appointment")
            stored = service.list_reminders()

            self.assertIn("Dentist appointment", response)
            self.assertEqual(len(stored), 1)
            self.assertEqual(
                datetime.fromisoformat(stored[0]["due_at"]), due_at
            )
            self.assertEqual(stored[0]["kind"], "reminder")

    def test_started_service_delivers_due_reminder_to_callback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "reminders.json"
            delivered = threading.Event()
            messages = []
            service = ReminderService(
                on_due=lambda message: (messages.append(message), delivered.set()),
                reminder_file=path,
                start=False,
            )
            service.schedule(1, "Call home", kind="reminder")
            service._reminders[0]["due_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat()

            service.start()
            try:
                self.assertTrue(delivered.wait(2), "Reminder service did not fire.")
                self.assertEqual(messages, ["Reminder: Call home"])
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()
