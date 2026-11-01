import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import requests

from memory import memory_manager
from services.system_tools import SystemTools
from services.reminder_service import ReminderService, parse_reminder_command
from services.telemetry_history import TelemetryHistory


class LiveOnlineToolsTests(unittest.TestCase):
    def setUp(self):
        self.tools = SystemTools.__new__(SystemTools)

    @staticmethod
    def response(payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @patch("services.system_tools.requests.get")
    def test_weather_reports_live_precipitation_for_named_location(self, get):
        get.side_effect = [
            self.response(
                {
                    "results": [
                        {
                            "name": "London",
                            "admin1": "England",
                            "country": "United Kingdom",
                            "latitude": 51.5,
                            "longitude": -0.12,
                        }
                    ]
                }
            ),
            self.response(
                {
                    "current": {
                        "temperature_2m": 12.4,
                        "apparent_temperature": 11.0,
                        "relative_humidity_2m": 74,
                        "precipitation": 0.6,
                        "weather_code": 61,
                        "wind_speed_10m": 9.0,
                    },
                    "daily": {
                        "temperature_2m_max": [14.0],
                        "temperature_2m_min": [8.0],
                        "precipitation_probability_max": [60],
                    },
                }
            ),
        ]

        result = self.tools.get_weather("What's the weather in London?")

        self.assertIn("Current weather in London, England, United Kingdom", result)
        self.assertIn("humidity 74%", result)
        self.assertIn("precipitation 0.6 mm", result)
        self.assertIn("Chance of precipitation: 60%", result)
        self.assertNotIn("time", get.call_args_list[1].kwargs["params"]["daily"])

    @patch("services.system_tools.requests.get")
    def test_automatic_weather_location_falls_back_when_primary_provider_is_limited(self, get):
        get.side_effect = [
            requests.RequestException("HTTP 429"),
            self.response(
                {
                    "success": True,
                    "city": "Pune",
                    "region": "Maharashtra",
                    "country": "India",
                    "latitude": 18.52,
                    "longitude": 73.86,
                }
            ),
            self.response(
                {
                    "current": {
                        "temperature_2m": 29,
                        "apparent_temperature": 31,
                        "relative_humidity_2m": 55,
                        "precipitation": 0,
                        "weather_code": 1,
                        "wind_speed_10m": 8,
                    },
                    "daily": {},
                }
            ),
        ]
        result = self.tools.get_weather("weather right now")
        self.assertIn("Current weather in Pune, Maharashtra, India", result)
        self.assertEqual(get.call_args_list[0].args[0], "https://ipapi.co/json/")
        self.assertEqual(get.call_args_list[1].args[0], "https://ipwho.is/")

    @patch("services.system_tools.DDGS")
    def test_news_search_includes_publisher_date_and_source_link(self, ddgs_type):
        ddgs = ddgs_type.return_value.__enter__.return_value
        ddgs.news.return_value = [
            {
                "title": "Latest update",
                "body": "A current event summary.",
                "source": "Example News",
                "date": "2026-10-31",
                "url": "https://example.test/news",
            }
        ]

        result = self.tools.search_web("latest news")

        self.assertIn("Latest update", result)
        self.assertIn("A current event summary.", result)
        self.assertIn("Example News", result)
        self.assertIn("2026-10-31", result)
        self.assertIn("https://example.test/news", result)
        ddgs.news.assert_called_once_with("latest news", max_results=5)

    @patch("services.system_tools.DDGS")
    def test_general_search_uses_web_results(self, ddgs_type):
        ddgs = ddgs_type.return_value.__enter__.return_value
        ddgs.text.return_value = [
            {
                "title": "Useful information",
                "body": "A general web result.",
                "href": "https://example.test/info",
            }
        ]

        result = self.tools.search_web("search for photosynthesis")

        self.assertIn("Useful information", result)
        self.assertIn("https://example.test/info", result)
        ddgs.text.assert_called_once_with("photosynthesis", max_results=5)
        ddgs.news.assert_not_called()

    @patch("services.system_tools.DDGS")
    def test_disabled_web_component_does_not_make_network_search(self, ddgs_type):
        self.tools.features = {"web_news": False}

        result = self.tools.search_web("latest news")

        self.assertIn("not selected during CYRUS setup", result)
        ddgs_type.assert_not_called()

    @patch.object(SystemTools, "search_web", return_value="live results")
    def test_current_events_route_to_live_search(self, search):
        for query in (
            "What are the current events?",
            "What's the latest news?",
            "What's the latest on the election?",
        ):
            with self.subTest(query=query):
                handled, result = self.tools.system_controls(query)

                self.assertTrue(handled)
                self.assertEqual(result, "live results")
        self.assertEqual(search.call_count, 3)

    @patch("services.system_tools.webbrowser.open")
    def test_open_url_preserves_original_case_and_query(self, open_url):
        query = "open https://Example.test/News?Topic=Weather"

        handled, result = self.tools.execute_command(query)

        self.assertTrue(handled)
        self.assertIn("https://Example.test/News?Topic=Weather", result)
        open_url.assert_called_once_with("https://Example.test/News?Topic=Weather")

    @patch("services.system_tools.webbrowser.open")
    def test_bare_domains_open_as_websites(self, open_url):
        handled, result = self.tools.execute_command("open example.com/news")
        self.assertTrue(handled)
        self.assertIn("https://example.com/news", result)
        open_url.assert_called_once_with("https://example.com/news")

    @patch("services.system_tools.webbrowser.open", return_value=True)
    def test_open_youtube_and_search_opens_a_youtube_results_url(self, open_url):
        handled, result = self.tools.execute_command("open YouTube and search for bbs")

        self.assertTrue(handled)
        self.assertIn("YouTube search results for bbs", result)
        open_url.assert_called_once_with(
            "https://www.youtube.com/results?search_query=bbs"
        )

    @patch("services.system_tools.threading.Thread")
    def test_youtube_play_command_queues_first_video_for_default_browser(self, thread_type):
        thread = thread_type.return_value
        thread.start.return_value = None
        downloader = MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.extract_info.return_value = {
            "entries": [{"id": "abc123", "title": "BBC video"}]
        }
        with (
            patch("services.system_tools.yt_dlp.YoutubeDL", return_value=downloader),
            patch("services.system_tools.webbrowser.open", return_value=True) as open_url,
        ):
            handled, result = self.tools.execute_command(
                "open YouTube and play a BBC video"
            )
            self.assertTrue(handled)
            self.assertIn("Finding a YouTube video for BBC", result)
            thread_type.assert_called_once()
            thread_type.call_args.kwargs["target"]()

        downloader.extract_info.assert_called_once_with(
            "ytsearch1:BBC", download=False
        )
        open_url.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc123"
        )

    @patch("services.system_tools.webbrowser.open", return_value=True)
    def test_spotify_play_command_opens_search_for_the_requested_song(self, open_url):
        handled, result = self.tools.execute_command(
            "open Spotify and play Here Comes the Sun"
        )

        self.assertTrue(handled)
        self.assertIn("Choose a result to start playback", result)
        open_url.assert_called_once_with(
            "https://open.spotify.com/search/Here%20Comes%20the%20Sun"
        )

    @patch("services.system_tools.webbrowser.open", return_value=True)
    def test_explicit_external_searches_open_the_requested_default_browser_page(
        self, open_url
    ):
        cases = (
            (
                "search on YouTube for happy birthday",
                "https://www.youtube.com/results?search_query=happy+birthday",
            ),
            (
                "search for happy birthday on YouTube",
                "https://www.youtube.com/results?search_query=happy+birthday",
            ),
            (
                "open Google and search for local weather",
                "https://www.google.com/search?q=local+weather",
            ),
            (
                "search for local weather on Google",
                "https://www.google.com/search?q=local+weather",
            ),
            (
                "search on Spotify for happy birthday",
                "https://open.spotify.com/search/happy%20birthday",
            ),
        )
        for query, expected_url in cases:
            with self.subTest(query=query):
                open_url.reset_mock()
                handled, result = self.tools.execute_command(query)
                self.assertTrue(handled)
                self.assertIn("Opening", result)
                open_url.assert_called_once_with(expected_url)

    @patch("services.system_tools.subprocess.Popen")
    @patch("services.system_tools.shutil.which", return_value="/usr/bin/gnome-calculator")
    @patch("services.system_tools.platform.system", return_value="Linux")
    def test_local_app_launch_uses_platform_command_without_shell(
        self, _system, _which, popen
    ):
        handled, result = self.tools.execute_command("open calculator")

        self.assertTrue(handled)
        self.assertIn("Launching Calculator", result)
        popen.assert_called_once_with(["gnome-calculator"], shell=False)

    @patch.object(SystemTools, "add_weather_favorite", return_value="favorite saved")
    def test_weather_favorite_command_routes_and_is_scoped(self, save_favorite):
        handled, result = self.tools.system_controls(
            "save London as weather favorite home"
        )
        self.assertTrue(handled)
        self.assertEqual(result, "favorite saved")
        save_favorite.assert_called_once_with("home", "London")

    def test_weather_favorites_are_listed_from_user_settings(self):
        self.tools.weather_favorites = {"home": "London", "work": "Manchester"}
        handled, result = self.tools.system_controls("list my weather favorites")
        self.assertTrue(handled)
        self.assertIn("home: London", result)
        self.assertIn("work: Manchester", result)

    @patch("services.system_tools.requests.get")
    def test_named_weather_favorite_resolves_to_saved_location(self, get):
        self.tools.weather_favorites = {"home": "London"}
        get.side_effect = [
            self.response(
                {
                    "results": [
                        {
                            "name": "London",
                            "country": "United Kingdom",
                            "latitude": 51.5,
                            "longitude": -0.12,
                        }
                    ]
                }
            ),
            self.response(
                {
                    "current": {
                        "temperature_2m": 12,
                        "apparent_temperature": 12,
                        "relative_humidity_2m": 60,
                        "precipitation": 0,
                        "weather_code": 0,
                        "wind_speed_10m": 0,
                    },
                    "daily": {
                        "time": ["2026-10-26"],
                        "temperature_2m_max": [16],
                        "temperature_2m_min": [8],
                        "precipitation_probability_max": [10],
                    },
                }
            ),
        ]
        result = self.tools.get_weather("weather in home")
        self.assertIn("London", result)
        self.assertEqual(get.call_args_list[0].kwargs["params"]["name"], "London")

    @patch("services.system_tools.requests.get")
    def test_week_forecast_requests_seven_days(self, get):
        self.tools.weather_favorites = {}
        get.side_effect = [
            self.response(
                {
                    "results": [
                        {"name": "London", "latitude": 51.5, "longitude": -0.12}
                    ]
                }
            ),
            self.response(
                {
                    "current": {
                        "temperature_2m": 12,
                        "apparent_temperature": 12,
                        "relative_humidity_2m": 60,
                        "precipitation": 0,
                        "weather_code": 0,
                        "wind_speed_10m": 0,
                    },
                    "daily": {
                        "time": [f"2026-10-{day}" for day in range(26, 33)],
                        "temperature_2m_max": [16] * 7,
                        "temperature_2m_min": [8] * 7,
                        "precipitation_probability_max": [10] * 7,
                    },
                }
            ),
        ]

        result = self.tools.get_weather("weekly forecast in London")

        self.assertEqual(get.call_args_list[1].kwargs["params"]["forecast_days"], 7)
        self.assertEqual(result.count("precipitation chance"), 7)

    def test_offline_mode_blocks_network_features_but_keeps_local_reports(self):
        self.tools.is_offline = True
        self.tools.player = MagicMock()
        with (
            patch("services.system_tools.DDGS") as ddgs,
            patch.object(self.tools, "get_cpu_stats", return_value="CPU 10%"),
        ):
            self.assertIn("Offline mode", self.tools.search_web("news"))
            self.assertIn("Offline mode", self.tools.get_weather("weather"))
            handled, result = self.tools.execute_command("play a song")
            self.assertTrue(handled)
            self.assertIn("Offline mode", result)
            self.tools.player.play_song.assert_not_called()
            ddgs.assert_not_called()

            handled, result = self.tools.system_controls("CPU utilization")
            self.assertTrue(handled)
            self.assertEqual(result, "CPU 10%")

    @patch("services.system_tools.save_user_state", return_value=True)
    @patch("services.system_tools.load_user_state", return_value={"weather_favorites": {}})
    def test_offline_toggle_persists_and_stops_streaming_music(self, _load, save):
        self.tools.player = MagicMock()
        self.tools.set_offline_mode(True)
        self.assertTrue(self.tools.is_offline)
        self.tools.player.stop.assert_called_once()
        save.assert_called_once_with({"weather_favorites": {}, "offline_mode": True})

    @patch("services.system_tools.save_user_state", return_value=False)
    @patch("services.system_tools.load_user_state", return_value={})
    def test_failed_weather_favorite_persistence_is_not_reported_as_success(
        self, _load, _save
    ):
        self.tools.weather_favorites = {"home": "Old City"}
        result = self.tools.add_weather_favorite("home", "New City")
        self.assertIn("couldn't save", result)
        self.assertEqual(self.tools.weather_favorites["home"], "Old City")

    def test_reminder_commands_schedule_list_and_cancel(self):
        reminders = MagicMock()
        reminders.list_reminders.return_value = [
            {"message": "stretch", "id": "a1b2c3d4"}
        ]
        reminders.cancel.return_value = 1
        reminders.schedule.return_value = "timer set"
        self.tools.reminders = reminders
        handled, result = self.tools.system_controls("set a timer for 5 minutes")
        self.assertTrue(handled)
        self.assertEqual(result, "timer set")
        reminders.schedule.assert_called_once_with(300, "Timer", kind="timer")

        handled, result = self.tools.system_controls("list my reminders")
        self.assertTrue(handled)
        self.assertIn("stretch (ID a1b2c3d4)", result)

        handled, result = self.tools.system_controls("cancel reminder a1b2c3d4")
        self.assertTrue(handled)
        self.assertIn("Cancelled 1 reminder", result)
        reminders.cancel.assert_called_once_with("a1b2c3d4")

    def test_natural_reminder_list_and_cancel_commands_are_routed(self):
        reminders = MagicMock()
        reminders.list_reminders.side_effect = [
            [{"message": "Timer finished", "id": "a1b2c3d4"}],
            [{"message": "Timer finished", "id": "a1b2c3d4"}],
        ]
        reminders.cancel.return_value = 1
        self.tools.reminders = reminders

        handled, result = self.tools.execute_command("list the reminders")
        self.assertTrue(handled)
        self.assertIn("Timer finished (ID a1b2c3d4)", result)

        handled, result = self.tools.execute_command("cancel the reminder")
        self.assertTrue(handled)
        self.assertIn("Cancelled 1 reminder", result)
        reminders.cancel.assert_called_once_with("a1b2c3d4")

    def test_timer_and_reminder_phrases_route_without_typo_corruption(self):
        cases = (
            ("set timer for 5 minutes", (300, "Timer")),
            ("set a timer 30 seconds", (30, "Timer")),
            ("start a timer for 2 hours", (7200, "Timer")),
            ("set a timer for five minutes", (300, "Timer")),
            ("remind me in twenty seconds to stretch", (20, "stretch")),
            ("set a reminder for 1 minute", (60, "Reminder")),
            ("set reminder after one hour to take a break", (3600, "take a break")),
            ("set a timer for 30 secs", (30, "Timer")),
            ("set a reminder for 10 secs named inner", (10, "inner")),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                reminders = MagicMock()
                reminders.schedule.return_value = "timer set"
                self.tools.reminders = reminders
                handled, result = self.tools.execute_command(query)
                self.assertTrue(handled)
                self.assertEqual(result, "timer set")
                kind = (
                    "reminder"
                    if "reminder" in query.lower() or "remind me" in query.lower()
                    else "timer"
                )
                reminders.schedule.assert_called_once_with(*expected, kind=kind)

    def test_misspelled_typed_reminder_routes_to_reminder_service(self):
        reminders = MagicMock()
        reminders.schedule.return_value = "Reminder set."
        self.tools.reminders = reminders

        handled, result = self.tools.execute_command(
            "set a remnder for 1 minut"
        )

        self.assertTrue(handled)
        self.assertEqual(result, "Reminder set.")
        reminders.schedule.assert_called_once_with(
            60, "Reminder", kind="reminder"
        )

    @patch("services.system_tools.webbrowser.open", return_value=True)
    def test_misspelled_typed_youtube_search_is_understood(self, open_url):
        handled, result = self.tools.execute_command(
            "serch on youtub for BBS"
        )

        self.assertTrue(handled)
        self.assertIn("YouTube search results for BBS", result)
        open_url.assert_called_once_with(
            "https://www.youtube.com/results?search_query=BBS"
        )

    def test_absolute_timer_and_reminder_keep_their_distinct_kinds(self):
        for query, expected_kind in (
            ("set a timer for 7:45", "timer"),
            ("set a reminder for 7:45", "reminder"),
        ):
            with self.subTest(query=query):
                reminders = MagicMock()
                reminders.schedule_at.return_value = "scheduled"
                self.tools.reminders = reminders
                handled, result = self.tools.execute_command(query)
                self.assertTrue(handled)
                self.assertEqual(result, "scheduled")
                self.assertEqual(
                    reminders.schedule_at.call_args.kwargs["kind"],
                    expected_kind,
                )

    def test_incomplete_timer_request_is_explained_not_routed_to_specs(self):
        reminders = MagicMock()
        self.tools.reminders = reminders
        with patch.object(self.tools, "get_full_specs") as get_specs:
            handled, result = self.tools.execute_command("set a timer")
        self.assertTrue(handled)
        self.assertIn("couldn't understand that timer duration", result)
        get_specs.assert_not_called()
        reminders.schedule.assert_not_called()

    def test_unrecognized_commands_return_a_handled_status_tuple(self):
        handled, result = self.tools.execute_command("tell me an ordinary fact")
        self.assertFalse(handled)
        self.assertEqual(result, "")

    @patch("services.system_tools.os.startfile", create=True)
    @patch("services.system_tools.platform.system", return_value="Windows")
    @patch("services.system_tools.os.path.isdir", return_value=True)
    def test_downloads_launcher_opens_current_user_folder(self, _isdir, _system, startfile):
        handled, result = self.tools.execute_command("open my downloads")
        self.assertTrue(handled)
        self.assertIn("Downloads", result)
        startfile.assert_called_once()
        self.assertTrue(startfile.call_args.args[0].endswith("Downloads"))

    @patch("services.system_tools.webbrowser.open")
    @patch.object(SystemTools, "launch_local_target", return_value=(True, "Launching Spotify."))
    def test_spotify_prefers_local_app_and_youtube_opens_web(self, launch, open_site):
        handled, result = self.tools.execute_command("open Spotify")
        self.assertTrue(handled)
        self.assertEqual(result, "Launching Spotify.")
        launch.assert_called_once_with("Spotify")

        handled, _ = self.tools.execute_command("open YouTube")
        self.assertTrue(handled)
        open_site.assert_called_once_with("https://www.youtube.com")

    def test_shutdown_and_lock_are_confirmed_before_execution(self):
        for query, expected in (
            ("shut down my PC", "CONFIRM_ACTION:shutdown_pc"),
            ("shutdown CYRUS", "CONFIRM_ACTION:shutdown_cyrus"),
            ("lock my PC", "CONFIRM_ACTION:lock_pc"),
        ):
            with self.subTest(query=query):
                handled, result = self.tools.system_controls(query)
                self.assertTrue(handled)
                self.assertEqual(result, expected)

    @patch("services.system_tools.subprocess.Popen")
    @patch("services.system_tools.platform.system", return_value="Windows")
    def test_confirmed_pc_shutdown_uses_safe_argument_list(self, _platform, popen):
        result = self.tools.confirm_action("shutdown_pc")
        self.assertEqual(result, "Confirmed: shutdown pc requested.")
        popen.assert_called_once_with(
            ["shutdown.exe", "/s", "/t", "5"], shell=False
        )


class PerUserMemoryTests(unittest.TestCase):
    def test_legacy_memory_migrates_to_user_storage_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy_file = root / "legacy.json"
            target_directory = root / "user-data"
            target_file = target_directory / "memory.json"
            old_memory = {"identity": {"user_name": "Local User"}, "notes": ["kept"]}
            legacy_file.write_text(json.dumps(old_memory), encoding="utf-8")

            with (
                patch.object(memory_manager, "MEMORY_DIR", target_directory),
                patch.object(memory_manager, "MEMORY_FILE", target_file),
                patch.object(memory_manager, "LEGACY_MEMORY_FILE", legacy_file),
            ):
                migrated = memory_manager.load_memory()

            self.assertEqual(migrated, old_memory)
            self.assertEqual(json.loads(target_file.read_text(encoding="utf-8")), old_memory)
            self.assertEqual(json.loads(legacy_file.read_text(encoding="utf-8")), old_memory)


class ReminderServiceTests(unittest.TestCase):
    def test_parses_timer_and_reminder_phrases(self):
        cases = (
            ("set a timer for 5 minutes", (300, "Timer")),
            ("set timer 30 seconds", (30, "Timer")),
            ("set timer for five minutes", (300, "Timer")),
            ("set timer for twenty-five seconds", (25, "Timer")),
            ("remind me in 20 minutes to stretch", (1200, "stretch")),
            ("remind me after 2 hours to take a break", (7200, "take a break")),
            ("remind me in twenty seconds to stretch", (20, "stretch")),
            ("set reminder for 5 minutes", (300, "Reminder")),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(parse_reminder_command(query), expected)

    def test_schedule_persists_cancel_and_due_alert(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            reminder_file = Path(temporary_directory) / "reminders.json"
            alerts = []
            service = ReminderService(
                on_due=alerts.append, reminder_file=reminder_file, start=False
            )
            response = service.schedule(60, "stretch")
            reminder_id = response.rsplit("ID ", 1)[1].rstrip(").")
            loaded = ReminderService(reminder_file=reminder_file, start=False)
            self.assertEqual(loaded.list_reminders()[0]["message"], "stretch")
            self.assertEqual(loaded.cancel(reminder_id), 1)
            self.assertEqual(loaded.list_reminders(), [])

            service._reminders[0]["due_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat()
            fired = service._fire_due()
            self.assertEqual(len(fired), 1)
            self.assertEqual(alerts, ["Timer: stretch"])
            service.stop()
            loaded.stop()

    def test_storage_failure_does_not_claim_a_reminder_was_saved(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            service = ReminderService(
                reminder_file=Path(temporary_directory) / "reminders.json",
                start=False,
            )
            with patch.object(service, "_save", return_value=False):
                result = service.schedule(30, "test")
            self.assertIn("couldn't save", result)
            self.assertEqual(service.list_reminders(), [])
            service.stop()

    def test_named_reminder_kind_and_countdown_updates_are_persisted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            changes = []
            service = ReminderService(
                reminder_file=Path(temporary_directory) / "reminders.json",
                start=False,
            )
            service.on_change = changes.append
            result = service.schedule(120, "Stretch break", kind="reminder")
            active = service.list_reminders()
            self.assertIn("Reminder set", result)
            self.assertEqual(active[0]["kind"], "reminder")
            self.assertEqual(active[0]["message"], "Stretch break")
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0], active)
            self.assertEqual(service.cancel(active[0]["id"]), 1)
            self.assertEqual(changes[-1], [])
            service.stop()


class TelemetryHistoryTests(unittest.TestCase):
    def test_history_is_rate_limited_persisted_and_bounded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            history_file = Path(temporary_directory) / "history.json"
            history = TelemetryHistory(history_file)
            first = datetime(2026, 10, 26, tzinfo=timezone.utc)
            self.assertTrue(history.record(10, 20, 30, first))
            self.assertFalse(history.record(11, 21, 31, first + timedelta(seconds=4)))
            self.assertTrue(history.record(50, 60, 70, first + timedelta(seconds=5)))
            self.assertEqual(history.values("cpu"), [10.0, 50.0])
            reloaded = TelemetryHistory(history_file)
            self.assertEqual(reloaded.values("ram"), [20.0, 60.0])
            with self.assertRaises(ValueError):
                history.values("network")


if __name__ == "__main__":
    unittest.main()
