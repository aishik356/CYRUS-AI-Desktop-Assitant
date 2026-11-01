import unittest
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import system_tools
from services.system_tools import CyrusPlayer, SystemTools


class SystemReportRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tools = SystemTools.__new__(SystemTools)

    def test_component_and_full_specs_have_separate_routes(self):
        cases = (
            ("what are my PC specs", "get_full_specs", "full"),
            ("what are my CPU specs", "get_cpu_spec", "cpu"),
            ("tell me my GPU specifications", "get_gpu_spec", "gpu"),
            ("what are my RAM specs", "get_ram_spec", "ram"),
        )
        for query, method, expected in cases:
            with self.subTest(query=query):
                with patch.object(self.tools, method, return_value=expected):
                    handled, result = self.tools.system_controls(query)
                self.assertTrue(handled)
                self.assertEqual(result, expected)

    def test_ambiguous_bare_system_specs_phrase_does_not_run_inventory_commands(self):
        handled, result = self.tools.system_controls("system specifications")

        self.assertTrue(handled)
        self.assertIn("Did you want to check system specs", result)

    def test_general_health_and_ram_process_question_are_separate(self):
        with (
            patch.object(self.tools, "get_pc_stats", return_value="health") as health,
            patch.object(self.tools, "get_top_ram_process", return_value="top app") as top_app,
        ):
            handled, result = self.tools.system_controls("tell me about my PC health")
            self.assertTrue(handled)
            self.assertEqual(result, "health")
            health.assert_called_once()
            top_app.assert_not_called()

            health.reset_mock()
            handled, result = self.tools.system_controls(
                "which app is consuming the most RAM"
            )
            self.assertTrue(handled)
            self.assertEqual(result, "top app")
            health.assert_not_called()
            top_app.assert_called_once()

    def test_individual_health_questions_route_to_one_component(self):
        cases = (
            ("CPU utilization", "get_cpu_stats", "cpu"),
            ("GPU usage", "get_gpu_stats", "gpu"),
            ("RAM usage", "get_ram_stats", "ram"),
            ("disk usage", "get_disk_stats", "disk"),
        )
        for query, method, expected in cases:
            with self.subTest(query=query):
                with patch.object(self.tools, method, return_value=expected):
                    handled, result = self.tools.system_controls(query)
                self.assertTrue(handled)
                self.assertEqual(result, expected)

    def test_component_spec_contents_are_scoped(self):
        process_result = lambda payload: SimpleNamespace(
            stdout=json.dumps(payload)
        )
        with patch(
            "services.system_tools.subprocess.run",
            return_value=process_result({
                "Name": "Example CPU",
                "NumberOfCores": 8,
                "NumberOfLogicalProcessors": 16,
                "CurrentClockSpeed": 2400,
                "MaxClockSpeed": 5000,
                "AddressWidth": 64,
            }),
        ):
            cpu = self.tools.get_cpu_spec()
        self.assertIn("Example CPU", cpu)
        self.assertNotIn("GPU", cpu)
        self.assertNotIn("RAM", cpu)

        with patch(
            "services.system_tools.subprocess.run",
            return_value=process_result({
                "Name": "Example GPU",
                "DriverVersion": "1.2.3",
                "AdapterRAM": 4 * 1024**3,
                "VideoModeDescription": "1920 x 1080",
                "CurrentRefreshRate": 144,
            }),
        ), patch.object(
            self.tools, "_get_nvidia_gpu_memory", return_value={"example gpu": "6144"}
        ):
            gpu = self.tools.get_gpu_spec()
        self.assertIn("Example GPU", gpu)
        self.assertIn("6144 MB dedicated VRAM", gpu)
        self.assertNotIn("CPU", gpu)
        self.assertNotIn("Installed RAM", gpu)

        memory = SimpleNamespace(total=16 * 1024**3)
        with (
            patch("services.system_tools.psutil.virtual_memory", return_value=memory),
            patch(
                "services.system_tools.subprocess.run",
                return_value=process_result({
                    "Manufacturer": "Example",
                    "PartNumber": "DDR5-module",
                    "Capacity": 16 * 1024**3,
                    "ConfiguredClockSpeed": 5600,
                    "FormFactor": 12,
                    "SMBIOSMemoryType": 34,
                    "DeviceLocator": "DIMM 1",
                }),
            ),
        ):
            ram = self.tools.get_ram_spec()
        self.assertIn("RAM specifications", ram)
        self.assertIn("DDR5", ram)
        self.assertNotIn("CPU", ram)
        self.assertNotIn("GPU", ram)

    def test_top_ram_process_reports_only_the_highest_process(self):
        processes = [
            SimpleNamespace(
                info={
                    "name": "SmallApp.exe",
                    "pid": 10,
                    "memory_info": SimpleNamespace(rss=50 * 1024**2),
                }
            ),
            SimpleNamespace(
                info={
                    "name": "LargeApp.exe",
                    "pid": 20,
                    "memory_info": SimpleNamespace(rss=200 * 1024**2),
                }
            ),
        ]
        with patch("services.system_tools.psutil.process_iter", return_value=processes):
            result = self.tools.get_top_ram_process()
        self.assertIn("LargeApp.exe", result)
        self.assertIn("200 MB", result)
        self.assertNotIn("SmallApp.exe", result)

    def test_health_contains_requested_metrics_without_process_rankings(self):
        memory = SimpleNamespace(
            percent=50.0,
            used=8 * 1024**3,
            total=16 * 1024**3,
        )
        partition = SimpleNamespace(device="C:", mountpoint="C:\\")
        disk_usage = SimpleNamespace(
            percent=40.0,
            used=200 * 1024**3,
            total=500 * 1024**3,
        )
        with (
            patch("services.system_tools.psutil.cpu_percent", return_value=23.0),
            patch("services.system_tools.psutil.virtual_memory", return_value=memory),
            patch("services.system_tools.psutil.disk_partitions", return_value=[partition]),
            patch("services.system_tools.psutil.disk_usage", return_value=disk_usage),
            patch.object(self.tools, "get_gpu_telemetry", return_value=("", "41%")),
            patch("services.system_tools.psutil.process_iter") as process_iter,
        ):
            result = self.tools.get_pc_stats()

        self.assertIn("CPU utilization 23.0%", result)
        self.assertIn("GPU utilization 41%", result)
        self.assertIn("RAM utilization 50.0%", result)
        self.assertIn("Disk C: utilization: 40.0% full", result)
        self.assertNotIn("process", result.lower())
        process_iter.assert_not_called()

    def test_health_marks_disk_unavailable_when_no_volumes_are_reported(self):
        memory = SimpleNamespace(percent=25.0, used=4 * 1024**3, total=16 * 1024**3)
        with (
            patch("services.system_tools.psutil.cpu_percent", return_value=10.0),
            patch("services.system_tools.psutil.virtual_memory", return_value=memory),
            patch("services.system_tools.psutil.disk_partitions", return_value=[]),
            patch.object(self.tools, "get_gpu_telemetry", return_value=("", "")),
        ):
            result = self.tools.get_pc_stats()
        self.assertIn("Disk utilization unavailable", result)
        self.assertIn("GPU utilization unavailable", result)


class VolumeRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tools = SystemTools.__new__(SystemTools)
        self.tools.player = SimpleNamespace(
            set_volume=lambda level: f"player={level}",
            adjust_volume=lambda delta: f"player_delta={delta}",
        )

    def test_player_volume_commands_do_not_change_system_volume(self):
        cases = (
            ("set player volume to 40", "player=40"),
            ("set volume of the song to 135", "player=100"),
            ("increase player volume", "player_delta=5"),
            ("decrease music volume by 12", "player_delta=-12"),
            ("turn up the track volume", "player_delta=5"),
            ("lower the player's volume by 7", "player_delta=-7"),
        )
        with patch.object(
            self.tools, "set_system_master_volume"
        ) as set_system_volume, patch("services.system_tools.pyautogui.press") as press:
            for query, expected in cases:
                with self.subTest(query=query):
                    handled, result = self.tools.system_controls(query)
                    self.assertTrue(handled)
                    self.assertEqual(result, expected)
            set_system_volume.assert_not_called()
            press.assert_not_called()

    def test_unqualified_volume_commands_still_target_system_audio(self):
        cases = (
            ("set volume to 40", "system=40"),
            ("set system volume to 140", "system=100"),
            ("increase volume", "Volume increased."),
            ("decrease sound", "Volume decreased."),
        )

        def set_system(level):
            return f"system={level}"

        with patch.object(
            self.tools, "set_system_master_volume", side_effect=set_system
        ), patch("services.system_tools.pyautogui.press") as press:
            for query, expected in cases:
                with self.subTest(query=query):
                    handled, result = self.tools.system_controls(query)
                    self.assertTrue(handled)
                    self.assertEqual(result, expected)
            self.assertEqual(
                [call.args[0] for call in press.call_args_list],
                ["volumeup"] * 5 + ["volumedown"] * 5,
            )

    def test_player_volume_is_persisted_and_applied_only_to_vlc(self):
        class FakeMediaPlayer:
            def __init__(self):
                self.volume_calls = []

            def audio_set_volume(self, level):
                self.volume_calls.append(level)
                return 0

        player = CyrusPlayer.__new__(CyrusPlayer)
        player._lock = threading.RLock()
        player.queue = []
        player.volume = 100
        player.media_player = FakeMediaPlayer()

        result = player.set_volume(42)
        self.assertIn("next song", result)
        self.assertEqual(player.volume, 42)
        self.assertEqual(player.media_player.volume_calls, [])

        player.queue = [{"title": "Current track", "url": "https://example.test"}]
        result = player.adjust_volume(8)
        self.assertEqual(result, "Music player volume set to 50 percent.")
        self.assertEqual(player.volume, 50)
        self.assertEqual(player.media_player.volume_calls, [50])

    def test_music_search_errors_are_reported_to_the_dashboard(self):
        class ImmediateThread:
            def __init__(self, target, **_kwargs):
                self.target = target

            def start(self):
                self.target()

        player = CyrusPlayer.__new__(CyrusPlayer)
        player._lock = threading.RLock()
        player._generation = 0
        player._queue_generation = 0
        player.queue = []
        player.queue_index = -1
        player.is_playing = False
        player.is_paused = False
        player.is_loading = False
        player.current_title = ""
        player.media_player = MagicMock()
        player.on_state_change = MagicMock()
        player.on_error = MagicMock()

        with (
            patch("services.system_tools.yt_dlp.YoutubeDL", side_effect=RuntimeError("network blocked")),
            patch("services.system_tools.threading.Thread", ImmediateThread),
        ):
            result = player.play_song("test track")

        self.assertEqual(result, "Finding test track.")
        self.assertIn("Music search failed: network blocked", player.on_error.call_args.args[0])
        self.assertEqual(player.on_state_change.call_args.args[1], "Could not load music")

    def test_vlc_volume_is_applied_after_audio_output_starts(self):
        class DelayedAudioPlayer:
            def __init__(self):
                self.state = system_tools.vlc.State.Opening
                self.events = []

            def play(self):
                self.events.append("play")
                return 0

            def get_state(self):
                if self.events.count("volume") > 0:
                    self.state = system_tools.vlc.State.Playing
                return self.state

            def audio_set_volume(self, level):
                self.events.append("volume")
                self.asserted_level = level
                return (
                    0
                    if self.state == system_tools.vlc.State.Playing
                    else -1
                )

        player = CyrusPlayer.__new__(CyrusPlayer)
        player.media_player = DelayedAudioPlayer()
        player.volume = 73

        with patch("services.system_tools.time.sleep"):
            player._start_playback_with_volume()

        self.assertEqual(player.media_player.events[0], "play")
        self.assertEqual(player.media_player.asserted_level, 73)

    @patch("services.system_tools.AudioUtilities")
    def test_reads_current_system_master_volume_as_percentage(self, audio_utilities):
        endpoint = audio_utilities.GetSpeakers.return_value.EndpointVolume
        endpoint.GetMasterVolumeLevelScalar.return_value = 0.37

        self.assertEqual(SystemTools.get_system_master_volume(), 37)


if __name__ == "__main__":
    unittest.main()
