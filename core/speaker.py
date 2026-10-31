import re
import threading
from pathlib import Path
from queue import Queue

import numpy
import sounddevice

from config.settings import get_user_voice_dir


def voice_asset_paths() -> tuple[Path, Path]:
    model_name = "en_GB-alan-medium.onnx"
    config_name = f"{model_name}.json"
    user_voice_directory = get_user_voice_dir()
    user_model_path = user_voice_directory / model_name
    user_config_path = user_voice_directory / config_name
    if user_model_path.is_file() and user_config_path.is_file():
        return user_model_path, user_config_path

    bundled_voice_directory = Path(__file__).resolve().parents[1] / "voices"
    bundled_model_path = bundled_voice_directory / model_name
    bundled_config_path = bundled_voice_directory / config_name
    if bundled_model_path.is_file() and bundled_config_path.is_file():
        return bundled_model_path, bundled_config_path

    return user_model_path, user_config_path


def _load_piper_voice(model_path: Path, config_path: Path):
    from piper import PiperVoice

    return PiperVoice.load(
        str(model_path),
        config_path=str(config_path),
    )


def _synthesize_at_full_volume(voice, text: str):
    from piper import SynthesisConfig

    return voice.synthesize(text, SynthesisConfig(volume=1.0))


def _scale_pcm_volume(audio: bytes, volume: float) -> bytes:
    samples = numpy.frombuffer(audio, dtype=numpy.int16)
    if volume <= 0:
        return numpy.zeros_like(samples).tobytes()
    if volume >= 1:
        return audio
    scaled = numpy.rint(samples.astype(numpy.float32) * volume)
    return numpy.clip(scaled, -32768, 32767).astype(numpy.int16).tobytes()


def preload_piper_runtime():
    """Loads ONNX Runtime before PyQt initializes its Windows DLLs."""
    from piper import PiperVoice

    return PiperVoice


class SilentVoiceSpeaker:
    """Speech-compatible no-op used when local voice output is not installed."""

    def __init__(self):
        self.is_speaking = False

    def stop(self):
        return

    def set_volume(self, _volume: int):
        return

    def speak(self, _text: str):
        return


class VoiceSpeaker:
    """Local Piper speech output using the configured Alan voice model."""

    def __init__(self):
        print("[System] Initializing local Piper speech output...")
        self.is_speaking = False
        self.stop_requested = threading.Event()
        self._volume_lock = threading.Lock()
        self._volume = 0.7
        self._requests = Queue()
        self._ready = threading.Event()
        self._initialization_error = None
        self._model_path, self._config_path = voice_asset_paths()
        self._speak_thread = threading.Thread(
            target=self._speech_worker,
            name="CyrusSpeech",
            daemon=True,
        )
        self._speak_thread.start()
        if not self._ready.wait(timeout=60):
            raise RuntimeError("Piper speech engine initialization timed out.")
        if self._initialization_error:
            raise RuntimeError(
                f"Piper speech engine could not start: {self._initialization_error}"
            ) from self._initialization_error

    def stop(self):
        """Requests playback to stop at the next audio chunk."""
        self.stop_requested.set()

    def set_volume(self, volume: int):
        """Sets Piper speech loudness as an integer percentage."""
        with self._volume_lock:
            self._volume = max(0, min(100, int(volume))) / 100

    def _get_volume(self) -> float:
        with self._volume_lock:
            return self._volume

    def _clean_text_for_speech(self, text: str) -> str:
        """Removes markdown tags, brackets, and code syntax for fluid pronunciation."""
        text = re.sub(r"[*_~`#>]", "", text)
        text = re.sub(r"\[.*?\]\(.*?\)", "", text)
        text = re.sub(r"http\S+", "", text)
        return text.strip()

    def _speech_worker(self):
        if not self._model_path.is_file():
            self._initialization_error = FileNotFoundError(
                f"Piper voice model was not found: {self._model_path}"
            )
            self._ready.set()
            return
        if not self._config_path.is_file():
            self._initialization_error = FileNotFoundError(
                f"Piper voice config was not found: {self._config_path}"
            )
            self._ready.set()
            return

        try:
            voice = _load_piper_voice(self._model_path, self._config_path)
        except Exception as error:
            self._initialization_error = error
            self._ready.set()
            print(f"[Speaker Error]: Piper speech output failed to initialize: {error}")
            return

        self._ready.set()
        while True:
            text, completed, outcome = self._requests.get()
            if text is None:
                completed.set()
                return

            stream = None
            try:
                for chunk in _synthesize_at_full_volume(voice, text):
                    if self.stop_requested.is_set():
                        break
                    if not chunk.audio_int16_bytes:
                        continue
                    samples_per_block = max(
                        chunk.sample_channels,
                        chunk.sample_rate * chunk.sample_channels // 20,
                    )
                    samples = numpy.frombuffer(
                        chunk.audio_int16_bytes,
                        dtype=numpy.int16,
                    )
                    if stream is None:
                        stream = sounddevice.RawOutputStream(
                            samplerate=chunk.sample_rate,
                            channels=chunk.sample_channels,
                            dtype="int16",
                        )
                        stream.start()
                    for start in range(0, len(samples), samples_per_block):
                        if self.stop_requested.is_set():
                            break
                        block = samples[start:start + samples_per_block].tobytes()
                        stream.write(_scale_pcm_volume(block, self._get_volume()))
            except Exception as error:
                outcome["error"] = error
                print(f"[Speaker Error]: Piper speech output failed: {error}")
            finally:
                if stream is not None:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception as error:
                        outcome.setdefault("error", error)
                        print(f"[Speaker Error]: Could not close Piper audio output: {error}")
                self.is_speaking = False
                self.stop_requested.clear()
                completed.set()

    def speak(self, text: str):
        if not text or not text.strip():
            return

        clean_text = self._clean_text_for_speech(text)
        if not clean_text:
            return
        if self._initialization_error:
            raise RuntimeError(
                f"Piper speech engine is unavailable: {self._initialization_error}"
            ) from self._initialization_error

        completed = threading.Event()
        outcome = {}
        self.stop_requested.clear()
        self.is_speaking = True
        self._requests.put((clean_text, completed, outcome))
        completed.wait()
        if "error" in outcome:
            raise RuntimeError(f"Piper speech output failed: {outcome['error']}") from outcome["error"]
