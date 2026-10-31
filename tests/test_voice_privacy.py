import unittest
from unittest.mock import MagicMock, patch

from core.listener import VoiceListener


class VoicePrivacyTests(unittest.TestCase):
    @patch("core.listener.sr.Microphone")
    def test_microphone_is_not_opened_or_calibrated_until_user_enables_it(self, microphone_type):
        microphone_type.list_microphone_names.return_value = []
        source = object()
        microphone_type.return_value.__enter__.return_value = source
        listener = VoiceListener()

        self.assertTrue(listener.is_muted)
        microphone_type.assert_not_called()
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
        listener.set_offline_mode(True)
        self.assertTrue(listener.is_muted)
        self.assertTrue(listener.is_offline)
        self.assertEqual(listener.transcribe(MagicMock()), "")


if __name__ == "__main__":
    unittest.main()
