import os
import re
import sys
import threading
from pathlib import Path
from queue import Queue

import numpy
import sounddevice

from config.settings import get_user_voice_dir

# ---------------------------------------------------------------------------
# Alan voice pack — default model loaded by VoiceSpeaker
# ---------------------------------------------------------------------------
_ALAN_MODEL_NAME = "en_GB-alan-medium.onnx"
_ALAN_CONFIG_NAME = f"{_ALAN_MODEL_NAME}.json"


def _ensure_voices_dir(directory: Path) -> None:
    """Create the voices directory if it does not already exist."""
    if not directory.exists():
        os.makedirs(directory, exist_ok=True)


def voice_asset_paths() -> tuple[Path, Path]:
    """Return (model_path, config_path) for the Alan voice pack.

    Search order:
      1. User-level voice directory (from settings).
      2. Project-bundled 'voices/' directory (sibling of this package root).

    Both directories are created automatically if absent.
    Falls back to the user-level paths (files may not exist yet) so the
    caller can report a clean missing-asset error rather than crashing.
    """
    # Resolve and guarantee the user voice directory.
    user_voice_directory = get_user_voice_dir()
    _ensure_voices_dir(user_voice_directory)

    # Resolve and guarantee the project-bundled voices/ directory.
    runtime_root = (
        Path(sys._MEIPASS)
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )
    bundled_voice_directory = runtime_root / "voices"
    _ensure_voices_dir(bundled_voice_directory)

    user_model_path = user_voice_directory / _ALAN_MODEL_NAME
    user_config_path = user_voice_directory / _ALAN_CONFIG_NAME
    if user_model_path.is_file() and user_config_path.is_file():
        return user_model_path, user_config_path

    bundled_model_path = bundled_voice_directory / _ALAN_MODEL_NAME
    bundled_config_path = bundled_voice_directory / _ALAN_CONFIG_NAME
    if bundled_model_path.is_file() and bundled_config_path.is_file():
        return bundled_model_path, bundled_config_path

    # Neither location has a complete pack; return user paths for error reporting.
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
    """Local Piper speech output using the configured Alan voice model.

    If the voice asset is missing or the speech engine fails to initialise,
    the error is logged via '[TTS_WARNING]' and the instance silently degrades
    (all subsequent speak() calls become no-ops) so the rest of the app keeps
    running without a crash or freeze.
    """

    def __init__(self):
        print("[System] Initializing local Piper speech output...")
        self.is_speaking = False
        self.stop_requested = threading.Event()
        self._volume_lock = threading.Lock()
        self._volume = 0.7
        self._requests = Queue()
        self._ready = threading.Event()
        self._initialization_error = None
        self._degraded = False  # True when TTS is unavailable but app continues
        self._temporary_audio_files: set[Path] = set()
        self._temporary_audio_lock = threading.Lock()
        self.on_status_change = None

        try:
            self._model_path, self._config_path = voice_asset_paths()
        except Exception as error:
            print("[TTS_WARNING]: Voice asset missing")
            print(f"[Speaker Error]: Could not resolve voice asset paths: {error}")
            self._degraded = True
            return

        try:
            self._speak_thread = threading.Thread(
                target=self._speech_worker,
                name="CyrusSpeech",
                daemon=True,
            )
            self._speak_thread.start()

            if not self._ready.wait(timeout=60):
                print("[TTS_WARNING]: Voice asset missing")
                print("[Speaker Error]: Piper speech engine initialization timed out.")
                self._degraded = True
                return

            if self._initialization_error:
                print("[TTS_WARNING]: Voice asset missing")
                print(
                    f"[Speaker Error]: Piper speech engine could not start: "
                    f"{self._initialization_error}"
                )
                self._degraded = True

        except Exception as error:
            print("[TTS_WARNING]: Voice asset missing")
            print(f"[Speaker Error]: Piper speech engine could not start: {error}")
            self._degraded = True

    def stop(self):
        """Requests playback to stop at the next audio chunk."""
        if getattr(self, "_degraded", False):
            return
        self.stop_requested.set()

    def track_temporary_audio_file(self, file_path: str | Path):
        """Register a generated speech file for deletion when CYRUS exits."""
        with self._temporary_audio_lock:
            self._temporary_audio_files.add(Path(file_path))

    def cleanup_temp_files(self):
        """Stop playback and delete speech files generated during this run."""
        self.stop()
        requests_queue = getattr(self, "_requests", None)
        if requests_queue is not None:
            requests_queue.put((None, threading.Event(), {}))
        with self._temporary_audio_lock:
            temporary_files = tuple(self._temporary_audio_files)
            self._temporary_audio_files.clear()
        for file_path in temporary_files:
            try:
                file_path.unlink(missing_ok=True)
            except OSError as error:
                print(
                    f"[Speaker Cleanup Warning]: Could not remove "
                    f"{file_path}: {error}"
                )

    @property
    def is_available(self) -> bool:
        return not getattr(self, "_degraded", False) and getattr(
            self, "_initialization_error", None
        ) is None

    def set_volume(self, volume: int):
        """Sets Piper speech loudness as an integer percentage."""
        if getattr(self, "_degraded", False):
            return
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
        try:
            if not self._model_path.is_file():
                print("[TTS_WARNING]: Voice asset missing")
                self._initialization_error = FileNotFoundError(
                    f"Piper voice model was not found: {self._model_path}"
                )
                self._ready.set()
                return
            if not self._config_path.is_file():
                print("[TTS_WARNING]: Voice asset missing")
                self._initialization_error = FileNotFoundError(
                    f"Piper voice config was not found: {self._config_path}"
                )
                self._ready.set()
                return

            voice = _load_piper_voice(self._model_path, self._config_path)
        except Exception as error:
            print("[TTS_WARNING]: Voice asset missing")
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
                        block = samples[start : start + samples_per_block].tobytes()
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
        if getattr(self, "_degraded", False):
            return
        if not text or not text.strip():
            return

        clean_text = self._clean_text_for_speech(text)
        if not clean_text:
            return
        if getattr(self, "_initialization_error", None):
            print(
                f"[TTS_WARNING]: Voice asset missing — "
                f"speak() skipped ({self._initialization_error})"
            )
            return

        completed = threading.Event()
        outcome = {}
        self.stop_requested.clear()
        self.is_speaking = True
        self._requests.put((clean_text, completed, outcome))
        completed.wait()
        if "error" in outcome:
            self._degraded = True
            print(
                f"[TTS_WARNING]: Audio output failed; voice disabled: "
                f"{outcome['error']}"
            )
            status_callback = self.on_status_change
            if status_callback is not None:
                status_callback(False)
