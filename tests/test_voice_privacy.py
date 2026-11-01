import unittest
from unittest.mock import MagicMock, patch

import speech_recognition as sr

from core.listener import VoiceListener


class VoicePrivacyTests(unittest.TestCase):
    @patch("core.listener.sr.Microphone")
    def test_microphone_is_not_opened_or_calibrated_until_user_enables_it(self, microphone_type):
        source = object()
        microphone_type.return_value.__enter__.return_value = source
        listener = VoiceListener()

        self.assertTrue(listener.is_muted)
        microphone_type.assert_not_called()
        microphone_type.list_microphone_names.assert_not_called()
        with patch.object(
            listener.recognizer, "adjust_for_ambient_noise"
        ) as calibrate:
            calibrate.assert_not_called()
            listener.set_muted(False)
            self.assertTrue(listener._initialize_microphone())
            microphone_type.assert_called_once_with(device_index=None)
            calibrate.assert_called_once_with(source, duration=0.5)

    def test_offline_mode_mutes_microphone_and_blocks_cloud_transcription(self):
        listener = VoiceListener.__new__(VoiceListener)
        listener.is_muted = False
        listener.is_offline = False
        listener.on_status_change = MagicMock()
        listener._last_transcription_error = None
        listener.set_offline_mode(True)
        self.assertTrue(listener.is_muted)
        self.assertTrue(listener.is_offline)
        self.assertEqual(listener.transcribe(MagicMock()), "")
        listener.on_status_change.assert_called_once()

    def test_microphone_reports_speech_recognition_network_failure(self):
        listener = VoiceListener.__new__(VoiceListener)
        listener.is_offline = False
        listener.is_muted = False
        listener.on_status_change = MagicMock()
        listener._last_transcription_error = None
        listener.recognizer = MagicMock()
        listener.recognizer.operation_timeout = 8
        with patch(
            "core.listener.recognize_legacy",
            side_effect=[
                sr.RequestError("service unavailable"),
                sr.RequestError("service unavailable"),
            ],
        ):
            self.assertEqual(listener.transcribe(MagicMock()), "")

        self.assertIn(
            "Online speech recognition is unavailable",
            listener.on_status_change.call_args.args[0],
        )
        self.assertEqual(listener.recognizer.operation_timeout, 8)

    def test_microphone_uses_explicit_google_backend_without_dynamic_method_registration(self):
        listener = VoiceListener.__new__(VoiceListener)
        listener.is_offline = False
        listener.is_muted = False
        listener.on_status_change = MagicMock()
        listener._last_transcription_error = None
        listener.recognizer = MagicMock(spec=["operation_timeout"])
        listener.recognizer.operation_timeout = 8

        with patch(
            "core.listener.recognize_legacy",
            side_effect=[sr.RequestError("try another locale"), "hello"],
        ) as recognize:
            self.assertEqual(listener.transcribe(MagicMock(), timeout=2), "hello")

        self.assertEqual(
            [call.kwargs["language"] for call in recognize.call_args_list],
            ["en-IN", "en-US"],
        )
        self.assertEqual(listener.recognizer.operation_timeout, 8)

    def test_unclear_speech_is_reported_once_until_successful_transcription(self):
        listener = VoiceListener.__new__(VoiceListener)
        listener.is_offline = False
        listener.is_muted = False
        listener.on_status_change = MagicMock()
        listener._last_transcription_error = None
        listener.recognizer = MagicMock()
        listener.recognizer.operation_timeout = 8

        with patch(
            "core.listener.recognize_legacy",
            side_effect=[
                sr.UnknownValueError(),
                sr.UnknownValueError(),
                sr.UnknownValueError(),
                sr.UnknownValueError(),
                "hello",
            ],
        ):
            self.assertEqual(listener.transcribe(MagicMock()), "")
            self.assertEqual(listener.transcribe(MagicMock()), "")
            listener.on_status_change.assert_called_once()
            self.assertEqual(listener.transcribe(MagicMock()), "hello")


if __name__ == "__main__":
    unittest.main()
