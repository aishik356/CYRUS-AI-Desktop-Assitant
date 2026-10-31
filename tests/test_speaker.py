import tempfile
import threading
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy

from core.speaker import VoiceSpeaker, _scale_pcm_volume, voice_asset_paths


class VoiceSpeakerTests(unittest.TestCase):
    def test_user_downloaded_voice_assets_are_preferred(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            user_voice_directory = Path(temporary_directory)
            model_path = user_voice_directory / "en_GB-alan-medium.onnx"
            config_path = user_voice_directory / "en_GB-alan-medium.onnx.json"
            model_path.touch()
            config_path.touch()
            with patch(
                "core.speaker.get_user_voice_dir",
                return_value=user_voice_directory,
            ):
                self.assertEqual(voice_asset_paths(), (model_path, config_path))

    @patch("core.speaker.sounddevice.RawOutputStream")
    @patch("core.speaker._load_piper_voice")
    def test_speaks_with_voice_from_voices_directory(self, load_voice, output_stream):
        chunk = SimpleNamespace(
            audio_int16_bytes=b"\x00\x00",
            sample_rate=22050,
            sample_channels=1,
        )
        voice = MagicMock()
        voice.synthesize.return_value = [chunk]
        load_voice.return_value = voice
        stream = output_stream.return_value
        speaker = VoiceSpeaker()

        speaker.speak("Hello, **there**")

        model_path = speaker._model_path
        self.assertEqual(model_path.parent.name, "voices")
        load_voice.assert_called_once_with(model_path, speaker._config_path)
        voice.synthesize.assert_called_once()
        self.assertEqual(voice.synthesize.call_args.args[0], "Hello, there")
        self.assertEqual(voice.synthesize.call_args.args[1].volume, 1.0)
        output_stream.assert_called_once_with(
            samplerate=22050,
            channels=1,
            dtype="int16",
        )
        stream.write.assert_called_once_with(b"\x00\x00")
        stream.stop.assert_called_once()
        stream.close.assert_called_once()
        self.assertFalse(speaker.is_speaking)

    @patch("core.speaker._load_piper_voice")
    def test_reports_voice_model_initialization_errors(self, load_voice):
        load_voice.side_effect = RuntimeError("model could not load")

        with self.assertRaisesRegex(RuntimeError, "Piper speech engine could not start"):
            VoiceSpeaker()

    def test_empty_text_does_not_initialize_audio(self):
        speaker = VoiceSpeaker.__new__(VoiceSpeaker)
        speaker._initialization_error = None

        with patch("core.speaker._load_piper_voice") as load_voice:
            speaker.speak("  ")

        load_voice.assert_not_called()

    def test_speech_volume_is_clamped_and_converted_to_a_gain(self):
        speaker = VoiceSpeaker.__new__(VoiceSpeaker)
        speaker._volume_lock = threading.Lock()

        speaker.set_volume(35)
        self.assertEqual(speaker._get_volume(), 0.35)
        speaker.set_volume(140)
        self.assertEqual(speaker._get_volume(), 1.0)
        speaker.set_volume(-10)
        self.assertEqual(speaker._get_volume(), 0.0)

    def test_zero_speech_volume_produces_silent_pcm(self):
        audio = numpy.array([12000, -12000], dtype=numpy.int16).tobytes()

        silenced = numpy.frombuffer(_scale_pcm_volume(audio, 0), dtype=numpy.int16)
        reduced = numpy.frombuffer(_scale_pcm_volume(audio, 0.5), dtype=numpy.int16)

        self.assertEqual(silenced.tolist(), [0, 0])
        self.assertEqual(reduced.tolist(), [6000, -6000])

    @patch("core.speaker.sounddevice.RawOutputStream")
    @patch("core.speaker._synthesize_at_full_volume")
    @patch("core.speaker._load_piper_voice")
    def test_changing_voice_volume_to_zero_mutes_remaining_audio(
        self, load_voice, synthesize, output_stream
    ):
        speaker = VoiceSpeaker()
        speaker.set_volume(50)
        samples = numpy.full(2205, 12000, dtype=numpy.int16)
        synthesize.return_value = [
            SimpleNamespace(
                audio_int16_bytes=samples.tobytes(),
                sample_rate=22050,
                sample_channels=1,
            )
        ]
        stream = output_stream.return_value
        stream.write.side_effect = lambda _audio: speaker.set_volume(0)

        speaker.speak("This speech should become quiet immediately.")

        written = [
            numpy.frombuffer(call.args[0], dtype=numpy.int16)
            for call in stream.write.call_args_list
        ]
        self.assertGreater(len(written), 1)
        self.assertEqual(int(numpy.max(written[0])), 6000)
        self.assertTrue(all(not numpy.any(block) for block in written[1:]))
        stream.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
