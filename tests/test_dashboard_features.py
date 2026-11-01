import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from config.settings import PROJECT_ROOT
from gui.dynamic_island import DynamicIslandHUD


class DashboardFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state_patch = patch("gui.dynamic_island.load_user_state", return_value={})
        self.state_patch.start()
        self.hud = DynamicIslandHUD()

    def tearDown(self):
        self.hud.telemetry_timer.stop()
        self.hud.countdown_timer.stop()
        self.hud.alarm_timer.stop()
        self.hud.cleanup_alarm_audio()
        self.hud.voice_volume_save_timer.stop()
        self.hud.system_volume_apply_timer.stop()
        self.hud.player_volume_apply_timer.stop()
        self.hud._shutdown_confirmed = True
        self.hud.close()
        self.state_patch.stop()
        self.app.processEvents()

    def test_existing_widgets_signals_and_privacy_default_remain_available(self):
        self.assertTrue(self.hud.is_mic_muted)
        self.assertFalse(
            self.hud.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        )
        self.assertIsNotNone(self.hud.chat_input)
        self.assertIsNotNone(self.hud.music_player_bar)
        self.assertTrue(self.hud.music_player_bar.isHidden())
        self.assertTrue(hasattr(self.hud, "text_command_signal"))
        self.assertTrue(hasattr(self.hud, "file_inspected_signal"))
        self.assertTrue(hasattr(self.hud, "stop_speech_signal"))
        self.assertTrue(hasattr(self.hud, "music_control_signal"))
        self.assertTrue(hasattr(self.hud, "reminder_alert_signal"))
        self.assertTrue(hasattr(self.hud, "offline_mode_signal"))

    def test_mic_toggle_emits_existing_signal_and_indicator_updates(self):
        spy = QSignalSpy(self.hud.mic_toggled_signal)
        self.hud.set_mic_muted(False)
        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[0][0], False)
        self.assertEqual(self.hud.current_subtext, "MIC ON // SPEAK NOW")
        self.assertEqual(self.hud.btn_mic.text(), "🎤 MIC ON")
        self.assertFalse(hasattr(self.hud, "diag_mic_lbl"))

    def test_hotkey_mic_toggle_is_dispatched_on_the_gui_thread(self):
        thread = threading.Thread(
            target=self.hud.mic_toggle_requested_signal.emit
        )
        thread.start()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        QTest.qWait(20)

        self.assertFalse(self.hud.is_mic_muted)
        self.assertEqual(self.hud.current_subtext, "MIC ON // SPEAK NOW")

        self.hud.mic_toggle_requested_signal.emit()
        self.app.processEvents()
        self.assertTrue(self.hud.is_mic_muted)

    @patch(
        "gui.dynamic_island.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )
    def test_microphone_permission_is_requested_before_unmuting(self, question):
        self.hud.is_mic_muted = True
        self.hud.update_mic_ui()

        self.assertTrue(self.hud.prompt_microphone_permission())

        question.assert_called_once()
        self.assertFalse(self.hud.is_mic_muted)
        self.assertEqual(self.hud.current_subtext, "MIC ON // SPEAK NOW")

    @patch(
        "gui.dynamic_island.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    )
    def test_declined_microphone_permission_leaves_mic_muted(self, question):
        self.hud.is_mic_muted = True

        self.assertFalse(self.hud.prompt_microphone_permission())

        question.assert_called_once()
        self.assertTrue(self.hud.is_mic_muted)

    def test_subsystem_status_panel_is_removed(self):
        status_text = {
            "• AUDIO:",
            "• MIC:",
            "• CHAT:",
            "• ROUTER:",
            "PIPER LOCAL",
            "CHAT READY",
            "DIRECT",
        }
        visible_text = {
            label.text()
            for label in self.hud.findChildren(QLabel)
        }
        self.assertTrue(status_text.isdisjoint(visible_text))

    def test_installer_can_disable_microphone_and_voice_output(self):
        features = {
            "alan_voice": False,
            "microphone_input": False,
            "web_news": True,
            "vlc_music": True,
            "screen_analysis": True,
        }
        with patch(
            "gui.dynamic_island.load_installed_features",
            return_value=features,
        ):
            hud = DynamicIslandHUD()

        try:
            self.assertTrue(hud.voice_volume_panel.isHidden())
            self.assertFalse(hud.btn_mic.isEnabled())
            self.assertFalse(hud.pill_btn_mic.isEnabled())
            hud.toggle_mic()
            self.assertTrue(hud.is_mic_muted)
        finally:
            hud.telemetry_timer.stop()
            hud.countdown_timer.stop()
            hud.voice_volume_save_timer.stop()
            hud.system_volume_apply_timer.stop()
            hud.player_volume_apply_timer.stop()
            hud._shutdown_confirmed = True
            hud.close()

    def test_voice_panel_links_to_downloads_when_selected_voice_is_missing(self):
        self.hud.voice_output_status_signal.emit(True, False)
        self.app.processEvents()

        self.assertFalse(self.hud.voice_volume_panel.isHidden())
        self.assertTrue(self.hud.voice_download_help.isVisible())
        self.assertFalse(self.hud.voice_volume_slider.isEnabled())
        self.assertIn("huggingface.co/rhasspy/piper-voices/resolve", self.hud.voice_download_help.text())
        self.assertIn("%LOCALAPPDATA%\\CYRUS\\voices", self.hud.voice_download_help.text())

    def test_voice_download_help_is_hidden_while_voice_initializes(self):
        self.hud.voice_output_status_signal.emit(True, False)
        self.app.processEvents()
        self.assertTrue(self.hud.voice_download_help.isVisible())

        self.hud.voice_output_initializing_signal.emit(True)
        self.app.processEvents()

        self.assertFalse(self.hud.voice_download_help.isVisible())
        self.assertFalse(self.hud.voice_volume_slider.isEnabled())

    def test_voice_download_links_hide_when_voice_is_available_or_not_selected(self):
        self.hud.voice_output_status_signal.emit(True, True)
        self.app.processEvents()
        self.assertTrue(self.hud.voice_volume_slider.isEnabled())
        self.assertFalse(self.hud.voice_download_help.isVisible())

        self.hud.voice_output_status_signal.emit(False, False)
        self.app.processEvents()
        self.assertTrue(self.hud.voice_volume_panel.isHidden())

    def test_close_confirmation_can_be_cancelled(self):
        with patch(
            "gui.dynamic_island.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ):
            self.hud.close_application()

        self.assertFalse(self.hud._shutdown_confirmed)

    def test_confirmed_close_requests_normal_application_shutdown(self):
        with (
            patch(
                "gui.dynamic_island.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch("gui.dynamic_island.QApplication.quit") as quit_application,
        ):
            self.hud.close_application()

        self.assertTrue(self.hud._shutdown_confirmed)
        quit_application.assert_called_once_with()

    def test_voice_volume_slider_updates_speech_setting_and_persists(self):
        spy = QSignalSpy(self.hud.voice_volume_changed_signal)
        with patch("gui.dynamic_island.save_user_state", return_value=True) as save:
            self.hud.voice_volume_slider.setValue(42)
            self.hud.system_volume_slider.setValue(31)
            self.hud.player_volume_slider.setValue(67)
            self.assertEqual(self.hud.voice_volume_value.text(), "42%")
            self.assertEqual(spy[0][0], 42)

            self.hud._save_voice_volume_preference()

        self.assertEqual(save.call_args.args[0]["voice_volume"], 42)
        self.assertEqual(save.call_args.args[0]["system_volume"], 31)
        self.assertEqual(save.call_args.args[0]["player_volume"], 67)
        self.hud.voice_volume_save_timer.stop()
        self.hud.system_volume_apply_timer.stop()
        self.hud.player_volume_apply_timer.stop()

    def test_voice_volume_slider_restores_saved_user_value(self):
        with patch(
            "gui.dynamic_island.load_user_state",
            return_value={"voice_volume": 28},
        ):
            hud = DynamicIslandHUD()

        try:
            self.assertEqual(hud.voice_volume_slider.value(), 28)
            self.assertEqual(hud.voice_volume_value.text(), "28%")
        finally:
            hud.telemetry_timer.stop()
            hud.countdown_timer.stop()
            hud.voice_volume_save_timer.stop()
            hud.system_volume_apply_timer.stop()
            hud.player_volume_apply_timer.stop()
            hud._shutdown_confirmed = True
            hud.close()

    def test_system_and_player_sliders_emit_independent_volume_levels(self):
        system_spy = QSignalSpy(self.hud.system_volume_changed_signal)
        player_spy = QSignalSpy(self.hud.player_volume_changed_signal)

        self.hud.system_volume_slider.setValue(33)
        self.hud.player_volume_slider.setValue(61)
        self.assertEqual(self.hud.system_volume_value.text(), "33%")
        self.assertEqual(self.hud.player_volume_value.text(), "61%")
        self.assertTrue(self.hud.system_volume_apply_timer.isActive())
        self.assertTrue(self.hud.player_volume_apply_timer.isActive())

        self.hud._apply_system_volume()
        self.hud._apply_player_volume()
        self.assertEqual(system_spy[0][0], 33)
        self.assertEqual(player_spy[0][0], 61)

    def test_volume_levels_can_sync_from_existing_volume_commands(self):
        self.hud.set_volume_levels(24, 76)
        self.assertEqual(self.hud.system_volume_slider.value(), 24)
        self.assertEqual(self.hud.player_volume_slider.value(), 76)
        self.assertEqual(self.hud.system_volume_value.text(), "24%")
        self.assertEqual(self.hud.player_volume_value.text(), "76%")
        self.assertFalse(self.hud.system_volume_apply_timer.isActive())
        self.assertFalse(self.hud.player_volume_apply_timer.isActive())

    @patch("gui.dynamic_island.winsound.PlaySound")
    def test_reminder_alert_is_visible_without_blocking_the_dashboard(self, play_alarm):
        self.hud.show_reminder_alert("Timer finished")
        self.assertEqual(len(self.hud._reminder_alerts), 1)
        alert = self.hud._reminder_alerts[0]
        self.assertEqual(alert.windowModality(), Qt.WindowModality.NonModal)
        self.assertTrue(alert.isVisible())
        self.assertTrue(self.hud.alarm_timer.isActive())
        play_alarm.assert_called_once()
        alarm_path = Path(play_alarm.call_args.args[0])
        self.assertTrue(alarm_path.is_file())
        alert.close()
        self.app.processEvents()
        self.assertEqual(self.hud._reminder_alerts, [])
        self.assertFalse(self.hud.alarm_timer.isActive())
        self.assertFalse(self.hud._alarm_playing)
        self.assertEqual(play_alarm.call_args.args[0], None)

    @patch("gui.dynamic_island.getpass.getuser", return_value="Alex")
    @patch("gui.dynamic_island.save_user_state", return_value=True)
    @patch("gui.dynamic_island.QDialog.exec", return_value=QDialog.DialogCode.Accepted)
    def test_first_run_profile_prompt_persists_name(self, _dialog, save, _user_name):
        self.hud.user_preferences = {}

        self.assertTrue(self.hud.prompt_user_profile_if_needed())

        self.assertTrue(save.called)
        saved = save.call_args.args[0]
        self.assertEqual(saved["preferred_name"], "Alex")
        self.assertTrue(saved["profile_setup_complete"])

    @patch("gui.dynamic_island.winsound.PlaySound")
    def test_alarm_repeats_until_reminder_alert_is_dismissed(self, play_alarm):
        self.hud.show_reminder_alert("Stretch break")
        play_alarm.assert_called_once()

        timeout = QSignalSpy(self.hud.alarm_timer.timeout)
        self.hud.alarm_timer.setInterval(10)
        self.assertTrue(timeout.wait(1000), "Repeating alarm timer did not fire")
        self.assertEqual(play_alarm.call_count, 1)

        self.hud._reminder_alerts[0].close()
        self.app.processEvents()
        self.assertFalse(self.hud.alarm_timer.isActive())

    def test_active_timer_and_named_reminder_count_down_above_reactor(self):
        due_at = (datetime.now(timezone.utc) + timedelta(seconds=125)).isoformat()
        self.hud.set_active_reminders(
            [
                {"kind": "timer", "message": "Timer", "due_at": due_at},
                {"kind": "reminder", "message": "Stretch break", "due_at": due_at},
            ]
        )
        self.assertFalse(self.hud.countdown_panel.isHidden())
        self.assertIn("TIMER", self.hud.countdown_label.text())
        self.assertIn("STRETCH BREAK", self.hud.countdown_label.text())
        self.assertIn("02:05", self.hud.countdown_label.text())
        self.assertLess(
            self.hud.center_layout.indexOf(self.hud.countdown_panel),
            self.hud.center_layout.indexOf(self.hud.reactor),
        )

    def test_one_minute_reminder_countdown_is_visible_in_pill_mode(self):
        due_at = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()

        self.hud.switchToPillMode()
        self.hud.set_active_reminders(
            [{"kind": "reminder", "message": "Call home", "due_at": due_at}]
        )

        self.assertIn("CALL HOME", self.hud.pill_status_label.text())
        self.assertIn("01:00", self.hud.pill_status_label.text())
        self.assertTrue(self.hud.countdown_panel.isHidden())

    def test_custom_reminder_alarm_is_used_without_being_deleted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            custom_alarm = Path(temporary_directory) / "reminder_alarm.wav"
            custom_alarm.write_bytes(b"custom wav asset")

            with patch(
                "gui.dynamic_island.get_user_data_dir",
                return_value=Path(temporary_directory),
            ):
                selected_alarm = self.hud._ensure_alarm_audio_file()
                self.hud.cleanup_alarm_audio()

            self.assertEqual(selected_alarm, custom_alarm)
            self.assertTrue(custom_alarm.is_file())

    def test_bundled_custom_alarm_is_used_when_no_user_override_exists(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                "gui.dynamic_island.get_user_data_dir",
                return_value=Path(temporary_directory),
            ):
                selected_alarm = self.hud._ensure_alarm_audio_file()

        self.assertEqual(
            selected_alarm,
            PROJECT_ROOT / "assets" / "reminder_alarm.wav",
        )
        self.assertTrue(selected_alarm.is_file())

    def test_countdown_panel_hides_when_there_are_no_active_reminders(self):
        self.hud.set_active_reminders([])
        self.assertTrue(self.hud.countdown_panel.isHidden())

    def test_dashboard_keeps_live_system_readings_without_duplicate_graphs(self):
        self.hud.show()
        self.assertTrue(self.hud.cpu_label.isVisible())
        self.assertTrue(self.hud.mem_label.isVisible())
        self.assertTrue(self.hud.disk_label.isVisible())
        self.assertFalse(hasattr(self.hud, "cpu_history_graph"))
        self.assertFalse(hasattr(self.hud, "ram_history_graph"))
        self.assertFalse(hasattr(self.hud, "disk_history_graph"))
        self.app.processEvents()

    def test_dashboard_size_is_clamped_to_available_screen_geometry(self):
        screen = self.app.primaryScreen()
        available = screen.availableGeometry()
        width, height = self.hud._dashboard_size()
        self.assertLessEqual(width, available.width())
        self.assertLessEqual(height, available.height())

    def test_pill_mode_can_shrink_below_dashboard_minimum_size(self):
        self.hud.switchToPillMode()
        self.assertEqual(self.hud.height(), 56)

    def test_compact_dashboard_shortens_headers_to_prevent_clipping(self):
        self.hud.resize(800, 600)
        self.app.processEvents()
        self.assertLess(self.hud.width(), 950)
        self.assertTrue(self.hud.dash_title.isHidden())
        self.assertEqual(self.hud.term_title.text(), "// 03. CHAT")
        self.assertEqual(self.hud.stream_badge.text(), "● LIVE")

    def test_dashboard_customization_reorders_hides_and_scales_panels(self):
        self.hud.user_preferences = {
            "panels": {"telemetry": False, "reactor": True, "terminal": True},
            "panel_order": ["terminal", "reactor", "telemetry"],
        }
        self.hud.dashboard_scale = 90
        self.hud.dashboard_brightness = 75
        self.hud.apply_dashboard_customization()

        self.assertFalse(self.hud.dashboard_panels["telemetry"].isVisible())
        self.assertTrue(self.hud.dashboard_panels["terminal"].isVisible())
        self.assertEqual(
            self.hud.panels_layout.itemAt(0).widget(),
            self.hud.dashboard_panels["terminal"],
        )
        self.assertAlmostEqual(self.hud.windowOpacity(), 0.75, places=2)

    @patch("gui.dynamic_island.QMessageBox.question", return_value=QMessageBox.StandardButton.No)
    def test_confirmation_defaults_to_no_and_does_not_dispatch_action(self, _question):
        spy = QSignalSpy(self.hud.confirmed_action_signal)
        self.hud.confirm_sensitive_action("shutdown_pc")
        self.assertEqual(len(spy), 0)

    @patch("gui.dynamic_island.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes)
    def test_confirmed_action_emits_only_after_user_approval(self, _question):
        spy = QSignalSpy(self.hud.confirmed_action_signal)
        self.hud.confirm_sensitive_action("lock_pc")
        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[0][0], "lock_pc")


if __name__ == "__main__":
    unittest.main()
