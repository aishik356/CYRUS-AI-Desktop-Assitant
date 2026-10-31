import json
import time
import os

import speech_recognition as sr

from config.settings import CONFIG_PATH, load_api_settings


class VoiceListener:
    def __init__(self):
        print("[System] Initializing High-Accuracy Speech Engine...")
        self.recognizer = sr.Recognizer()
        self.is_muted = True
        self.is_offline = False
        self.microphone = None
        self._last_listen_error = None
        
        # Audio detection thresholds
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.6
        self.recognizer.phrase_threshold = 0.2
        self.recognizer.non_speaking_duration = 0.3
        self.recognizer.operation_timeout = 8

        device_index = self._configured_device_index()
        try:
            device_names = sr.Microphone.list_microphone_names()
            if device_names:
                print("[System] Microphone devices: " + "; ".join(
                    f"{index}: {name}" for index, name in enumerate(device_names)
                ))
        except Exception as e:
            print(f"[Microphone Warning]: Could not list input devices: {e}")

        self.device_index = device_index

    def _initialize_microphone(self) -> bool:
        if self.microphone is not None:
            return True
        try:
            self.microphone = sr.Microphone(device_index=self.device_index)
        except Exception as error:
            print(f"[Microphone Init Error]: Could not open the microphone: {error}")
            return False
        try:
            with self.microphone as source:
                print("[System] Calibrating microphone after it was enabled...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
        except Exception as error:
            print(f"[Microphone Init Warning]: Could not calibrate the microphone: {error}")
        return True

    @staticmethod
    def _configured_device_index():
        try:
            settings = load_api_settings()
        except (OSError, json.JSONDecodeError, ValueError) as e:
            print(f"[Microphone Config Warning]: Could not read {CONFIG_PATH}: {e}")
            return None

        configured_index = os.getenv("CYRUS_MICROPHONE_DEVICE_INDEX")
        device_index = (
            configured_index
            if configured_index is not None
            else settings.get("microphone_device_index")
        )
        if device_index is None:
            return None
        if isinstance(device_index, str):
            try:
                device_index = int(device_index)
            except ValueError:
                print(
                    "[Microphone Config Error]: "
                    "CYRUS_MICROPHONE_DEVICE_INDEX must be a non-negative integer."
                )
                return None
        if (
            isinstance(device_index, bool)
            or not isinstance(device_index, int)
            or device_index < 0
        ):
            print(
                "[Microphone Config Error]: microphone_device_index must be "
                "a non-negative integer or null."
            )
            return None
        return device_index

    def set_muted(self, muted: bool):
        """Enables or disables audio capture."""
        self.is_muted = muted
        print(f"[System] VoiceListener mute status: {self.is_muted}")

    def set_offline_mode(self, enabled: bool):
        self.is_offline = bool(enabled)
        if self.is_offline:
            self.set_muted(True)
        print(f"[System] Offline speech recognition: {'disabled' if enabled else 'online'}")

    def toggle_mute(self) -> bool:
        """Toggles audio capture on and off."""
        self.is_muted = not self.is_muted
        print(f"[System] VoiceListener mute toggled to: {self.is_muted}")
        return self.is_muted

    def listen_and_record(self, timeout=None, phrase_time_limit=None):
        if self.is_muted:
            time.sleep(0.15)
            return None
        if not self._initialize_microphone():
            time.sleep(0.15)
            return None

        try:
            with self.microphone as source:
                # Use passed timeout and phrase limits if provided
                if timeout is not None or phrase_time_limit is not None:
                    audio = self.recognizer.listen(
                        source, 
                        timeout=timeout, 
                        phrase_time_limit=phrase_time_limit
                    )
                else:
                    audio = self.recognizer.listen(source)
                self._last_listen_error = None
                return audio
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            message = str(e)
            if message != self._last_listen_error:
                print(f"[Microphone Error]: Audio capture failed: {e}")
                self._last_listen_error = message
            return None

    def transcribe(self, audio_data, timeout=None) -> str:
        """Transcribes speech using Google's online speech-recognition service."""
        if self.is_offline:
            return ""
        if audio_data is None or self.is_muted:
            return ""

        previous_timeout = self.recognizer.operation_timeout
        if timeout is not None:
            self.recognizer.operation_timeout = timeout
        try:
            text = self.recognizer.recognize_google(audio_data, language="en-IN")
            return text.strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            try:
                text = self.recognizer.recognize_google(audio_data, language="en-US")
                return text.strip()
            except sr.UnknownValueError:
                return ""
            except sr.RequestError as e:
                print(f"[Speech Recognition Error]: Google's service is unavailable: {e}")
                return ""
        except Exception as e:
            print(f"[Speech Recognition Error]: Transcription failed: {e}")
            return ""
        finally:
            self.recognizer.operation_timeout = previous_timeout
