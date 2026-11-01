import os
import sys
from queue import Empty, Queue

import time
import threading
import mimetypes
import re
import requests

# Load .env before importing assistant modules that read runtime settings.
from config import settings as _runtime_settings
from config.features import load_installed_features
from core.speaker import SilentVoiceSpeaker, VoiceSpeaker

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot

from config.settings import (
    PORTABLE_MODE,
    has_saved_api_settings,
    load_api_settings,
)
from config.user_state import load_user_state
from core.listener import VoiceListener
from core.brain import CyrusBrain
from services.system_tools import (
    SystemTools,
    configure_ollama,
    configure_openrouter,
)
from gui.dynamic_island import DynamicIslandHUD
from memory.memory_manager import add_note, load_memory
from services.vision_service import analyze_screen
from services.hotkey_service import HotkeyListener
from services.startup_check import check_startup_requirements, startup_check_warnings
from services.greetings import contextual_greeting


class StartupCheckWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str, str)

    def run(self):
        try:
            self.status.emit("BOOTING", "CHECKING SYSTEM REQUIREMENTS...")
            checks = check_startup_requirements()
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(startup_check_warnings(checks))


class StartupConfigurationWorker(QObject):
    completed = pyqtSignal(object, bool)
    failed = pyqtSignal(str)

    def run(self):
        try:
            settings = load_api_settings()
            has_saved_settings = has_saved_api_settings()
        except (OSError, ValueError) as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(settings, has_saved_settings)


class ProviderSetupWorker(QObject):
    completed = pyqtSignal(str)
    failed = pyqtSignal(str, str, bool)
    status = pyqtSignal(str, str)

    def __init__(self, provider: str, api_key: str = ""):
        super().__init__()
        self.provider = provider
        self.api_key = api_key

    def run(self):
        try:
            self.status.emit("BOOTING", f"VERIFYING {self.provider.upper()}...")
            if self.provider == "openrouter":
                settings = configure_openrouter(self.api_key)
                os.environ["CYRUS_AI_BACKEND"] = "openrouter"
                os.environ["OPENROUTER_API_KEY"] = settings["openrouter_api_key"]
                os.environ["OPENROUTER_CHAT_MODEL"] = settings[
                    "openrouter_chat_model"
                ]
            elif self.provider == "ollama":
                settings = configure_ollama()
                os.environ["CYRUS_AI_BACKEND"] = "ollama"
                os.environ["OLLAMA_HOST"] = settings["ollama_host"]
            else:
                raise ValueError(f"Unsupported AI provider: {self.provider}")
        except Exception as error:
            self.api_key = ""
            status_code = getattr(error.response, "status_code", None)
            is_network_error = isinstance(error, requests.RequestException) and (
                not isinstance(error, requests.HTTPError)
                or status_code is None
                or status_code >= 500
            )
            self.failed.emit(self.provider, str(error), is_network_error)
            return
        self.api_key = ""
        self.completed.emit(self.provider)


class StartupCoordinator(QObject):
    def __init__(self, hud: DynamicIslandHUD, on_ready):
        super().__init__(hud)
        self.hud = hud
        self.on_ready = on_ready
        self._threads = []
        self._workers = []

    @pyqtSlot()
    def start(self):
        self.hud.set_state("BOOTING", "LOADING LOCAL CONFIGURATION...")
        worker = StartupConfigurationWorker()
        worker.completed.connect(self._on_configuration_ready)
        worker.failed.connect(self._on_configuration_failed)
        thread = threading.Thread(
            target=worker.run,
            name="CyrusStartupConfiguration",
            daemon=True,
        )
        self._workers.append(worker)
        self._threads.append(thread)
        thread.start()

    @pyqtSlot(str)
    def _on_configuration_failed(self, message: str):
        QMessageBox.critical(
            self.hud,
            "CYRUS Configuration Error",
            f"Could not load the AI configuration: {message}",
        )
        QApplication.quit()

    @pyqtSlot(object, bool)
    def _on_configuration_ready(self, settings, has_saved_settings: bool):
        if not PORTABLE_MODE and not has_saved_settings:
            self._select_provider()
            return

        if PORTABLE_MODE:
            provider = "openrouter"
        else:
            provider = os.getenv(
                "CYRUS_AI_BACKEND",
                str(settings.get("ai_backend", "ollama") or "ollama"),
            ).strip().lower()

        if provider == "openrouter":
            api_key = (
                os.getenv("OPENROUTER_API_KEY", "").strip()
                or str(settings.get("openrouter_api_key", "") or "").strip()
            )
            if api_key:
                self._start_provider_setup(provider, api_key)
            else:
                self._request_api_key()
            return
        if provider == "ollama":
            self._start_provider_setup(provider)
            return
        self._select_provider()

    def _select_provider(self):
        provider = self.hud.prompt_ai_provider(PORTABLE_MODE)
        if provider == "openrouter":
            self._request_api_key()
        elif provider == "ollama":
            self._start_provider_setup(provider)
        else:
            QApplication.quit()

    def _request_api_key(self):
        api_key = self.hud.prompt_openrouter_api_key()
        if api_key:
            self._start_provider_setup("openrouter", api_key)
        else:
            QApplication.quit()

    def _start_provider_setup(self, provider: str, api_key: str = ""):
        worker = ProviderSetupWorker(provider, api_key)
        worker.completed.connect(self._on_provider_ready)
        worker.failed.connect(self._on_provider_failed)
        worker.status.connect(self.hud.set_state)
        thread = threading.Thread(
            target=worker.run,
            name="CyrusProviderSetup",
            daemon=True,
        )
        self._workers.append(worker)
        self._threads.append(thread)
        self.hud.set_state("BOOTING", "VERIFYING AI PROVIDER...")
        thread.start()

    @pyqtSlot(str)
    def _on_provider_ready(self, provider: str):
        if provider == "openrouter":
            self.hud.set_state(
                "BOOTING", "OPENROUTER KEY SUCCESSFUL // BOOTING..."
            )
            self.hud.append_log(
                "[OPENROUTER]: API key verified successfully. Booting CYRUS..."
            )
        if not self.hud.prompt_user_profile_if_needed():
            QApplication.quit()
            return
        self.hud.prompt_microphone_permission()
        self.on_ready()

    @pyqtSlot(str, str, bool)
    def _on_provider_failed(self, provider: str, message: str, offline: bool):
        if offline:
            self.hud.set_offline_mode(True)
            self.hud.set_state("OFFLINE", "ENDPOINT UNREACHABLE // LOCAL MODE")
            self.hud.append_log(
                f"[OFFLINE] {provider.title()} endpoint unreachable: {message}. "
                "Continuing with local features."
            )
            if not self.hud.prompt_user_profile_if_needed():
                QApplication.quit()
                return
            self.hud.prompt_microphone_permission()
            self.on_ready()
            return
        QMessageBox.warning(
            self.hud,
            "CYRUS Provider Setup",
            f"Could not configure {provider}: {message}",
        )
        if provider == "openrouter":
            self._request_api_key()
        else:
            self._select_provider()


class StartupCheckNotifier(QObject):
    finished = pyqtSignal()

    def __init__(self, app, hud: DynamicIslandHUD):
        super().__init__(app)
        self.hud = hud

    @pyqtSlot(object)
    def show_warnings(self, warnings):
        if warnings:
            endpoint_unreachable = any(
                check.name == "AI backend"
                and not check.ready
                and "Could not reach Ollama" in check.details
                for check in warnings
            )
            if endpoint_unreachable:
                self.hud.set_offline_mode(True)
                self.hud.set_state(
                    "OFFLINE", "ENDPOINT UNREACHABLE // LOCAL MODE"
                )
                self.hud.append_log(
                    "[OFFLINE] Ollama endpoint unreachable. "
                    "Continuing with local features."
                )
            for check in warnings:
                self.hud.append_log(
                    f"[STARTUP WARNING] {check.name}: {check.details}"
                )
        if not any(
            check.name == "AI backend" and not check.ready for check in warnings
        ):
            self.hud.set_state("BOOTING", "INITIALIZING CYRUS CORE...")
        self.finished.emit()

    @pyqtSlot(str)
    def show_check_error(self, message):
        QMessageBox.warning(
            None,
            "CYRUS Setup Check",
            f"Could not complete the setup check: {message}\nCYRUS will still open.",
        )
        self.finished.emit()


class FileInspectionWorker(QObject):
    completed = pyqtSignal(str, str)
    failed = pyqtSignal(str, str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        file_name = os.path.basename(self.file_path)
        try:
            if not os.path.isfile(self.file_path):
                raise FileNotFoundError(f"File no longer exists: {self.file_path}")
            file_size_kb = round(os.path.getsize(self.file_path) / 1024, 2)
            mime_type, _ = mimetypes.guess_type(self.file_path)
            mime_type = mime_type or "Unknown/Binary"
            ext = os.path.splitext(file_name)[1].lower() or "No Extension"
            summary = (
                f"File: {file_name}\nType: {mime_type} ({ext})\n"
                f"Size: {file_size_kb} KB\n"
            )
            text_extensions = {
                ".txt", ".py", ".js", ".json", ".html", ".css", ".md",
                ".log", ".csv", ".cpp", ".c", ".sh",
            }
            if ext in text_extensions or "text" in mime_type:
                with open(
                    self.file_path, "r", encoding="utf-8", errors="ignore"
                ) as file:
                    summary += f"\nPreview:\n{file.read(500)}..."
            else:
                summary += "\nBinary structure detected."
            spoken_text = (
                f"File {file_name} loaded. Format is {mime_type}, "
                f"size {file_size_kb} kilobytes."
            )
        except (OSError, ValueError) as error:
            self.failed.emit(file_name, str(error))
            return
        self.completed.emit(summary, spoken_text)


class FileInspectionNotifier(QObject):
    def __init__(self, hud: DynamicIslandHUD, request_queue: Queue):
        super().__init__(hud)
        self.hud = hud
        self.request_queue = request_queue

    @pyqtSlot(str, str)
    def show_result(self, summary: str, spoken_text: str):
        self.hud.append_log(f"[FILE_INSPECTOR]:\n{summary}")
        self.request_queue.put(("speak", spoken_text))
        self.hud.set_state("IDLE")

    @pyqtSlot(str, str)
    def show_error(self, file_name: str, message: str):
        self.hud.append_log(
            f"[FILE_INSPECTOR ERROR]: Could not inspect {file_name}: {message}"
        )
        self.hud.set_state("IDLE")


def speak_with_barge_in(
    text: str,
    speaker: VoiceSpeaker | SilentVoiceSpeaker,
    listener: VoiceListener | None,
    hud: DynamicIslandHUD,
):
    """Speaks text while concurrently listening for 'stop' or 'shut up' commands."""
    stop_words = ["stop", "shut up", "be quiet", "cancel", "quiet", "cyrus stop", "pause"]

    hud.set_state("SPEAKING", text)

    # Start speech on an asynchronous worker
    speech_thread = threading.Thread(target=speaker.speak, args=(text,), daemon=True)
    speech_thread.start()

    time.sleep(0.1)

    # Monitor mic while speaker is active (only if microphone is unmuted)
    while speaker.is_speaking:
        if listener is not None and not hud.is_mic_muted and not listener.is_muted:
            audio = listener.listen_and_record(timeout=0.4, phrase_time_limit=1.0)
            if audio is not None:
                heard = listener.transcribe(audio, timeout=2.0).lower().strip()
                if any(trigger in heard for trigger in stop_words):
                    print(f"\n[Interrupted]: Heard '{heard}'. Stopping speech.")
                    speaker.stop()
                    break
        time.sleep(0.04)

    speech_thread.join()
    if hud.is_mic_muted:
        hud.set_state("MUTED", "MIC OFF // CHAT READY")
    else:
        hud.set_state("IDLE")


def process_query(
    query: str,
    speaker: VoiceSpeaker | SilentVoiceSpeaker,
    listener: VoiceListener | None,
    brain: CyrusBrain,
    tools: SystemTools,
    hud: DynamicIslandHUD,
    source: str = "VOICE",
) -> str:
    """Unified handler for both Voice input and Text Chat input."""
    clean_q = query.lower().strip()
    if not clean_q or len(clean_q) < 2:
        if not hud.is_mic_muted:
            hud.set_state("IDLE")
        return ""

    print(f"[{source}]: {query}")

    greeting = clean_q.strip(" .,!?:;")
    if greeting in {
        "hello",
        "hello cyrus",
        "hi",
        "hi cyrus",
        "hey",
        "hey cyrus",
        "yo",
        "yo cyrus",
        "good morning",
        "good afternoon",
        "good evening",
        "good night",
    }:
        profile = load_user_state()
        reply = contextual_greeting(
            str(profile.get("preferred_name", "")),
        )
        hud.append_log(f"[CYRUS]: {reply}")
        speak_with_barge_in(reply, speaker, listener, hud)
        return reply

    # 1. Standby / Sleep / Wake
    if any(s in clean_q for s in ["go to sleep", "sleep cyrus", "standby mode"]):
        hud.set_state("SPEAKING", "ENTERING STANDBY")
        reply = "Entering background standby."
        hud.append_log(f"[CYRUS]: {reply}")
        speaker.speak(reply)
        return "SLEEP"

    if any(w in clean_q for w in ["wake up cyrus", "wake up", "cyrus wake up", "cyrus online"]):
        hud.set_state("SPEAKING", "CYRUS AWAKE")
        preferred_name = str(load_user_state().get("preferred_name", "")).strip()
        reply = (
            f"Online and listening, {preferred_name}."
            if preferred_name
            else "Online and listening."
        )
        hud.append_log(f"[CYRUS]: {reply}")
        speaker.speak(reply)
        hud.set_state("IDLE")
        return "WAKE"

    # 2. Persistent Memory Handling
    if "remember" in clean_q:
        fact = clean_q.replace("cyrus", "").replace("please", "")
        for prefix in ["remember that", "remember i", "remember", "remember this"]:
            fact = fact.replace(prefix, "")
        fact = fact.replace("that", "").strip(" .?!,")
        
        if fact:
            add_note(fact)
            reply = f"Understood. I will remember that {fact}."
            hud.append_log(f"[CYRUS]: {reply}")
            speak_with_barge_in(reply, speaker, listener, hud)
            return reply

    if any(w in clean_q for w in ["what do you remember", "read memory", "check memory"]):
        mem = load_memory()
        notes = mem.get("notes", [])
        if notes:
            recent = ". ".join(notes[-3:])
            reply = f"I recall: {recent}"
        else:
            reply = "Long-term memory is currently empty."
        hud.append_log(f"[CYRUS]: {reply}")
        speak_with_barge_in(reply, speaker, listener, hud)
        return reply

    # 3. Screen Vision Intercept
    vision_triggers = [
        "what is on my screen", "whats on my screen", "what's on my screen",
        "look at my screen", "look at the screen", "inspect screen",
        "analyze screen", "check my screen", "read screen",
        "what am i looking at", "tell me what is on my screen", "look at this"
    ]
    if any(vt in clean_q for vt in vision_triggers):
        if not tools.features["screen_analysis"]:
            reply = "Screen analysis was not selected during CYRUS setup."
            hud.append_log(f"[CYRUS]: {reply}")
            speak_with_barge_in(reply, speaker, listener, hud)
            return reply
        if tools.is_offline:
            reply = "Screen analysis is unavailable while offline mode is enabled."
            hud.append_log(f"[CYRUS]: {reply}")
            speak_with_barge_in(reply, speaker, listener, hud)
            return reply
        hud.set_state("THINKING", "INSPECTING SCREEN...")
        user_instruction = clean_q
        for vt in vision_triggers:
            user_instruction = user_instruction.replace(vt, "")
        user_instruction = user_instruction.strip() or "Describe what is currently visible on my screen."

        diagnosis = analyze_screen(user_instruction)
        hud.append_log(f"[CYRUS]: {diagnosis}")
        speak_with_barge_in(diagnosis, speaker, listener, hud)
        return diagnosis

    # 4. Fast System Tools & Hardware Specs/Stats
    handled, system_result = tools.execute_command(query)
    if handled and system_result and re.search(r"\b(?:volume|sound)\b", clean_q):
        current_system_volume = tools.get_system_master_volume()
        hud.volume_levels_signal.emit(
            hud.system_volume_slider.value()
            if current_system_volume is None
            else current_system_volume,
            tools.player.volume,
        )
    if handled and system_result:
        if system_result.startswith("CONFIRM_ACTION:"):
            action = system_result.partition(":")[2]
            hud.action_confirmation_signal.emit(action)
            reply = f"Confirm {action.replace('_', ' ')} using the dialog on screen."
            hud.append_log(f"[CYRUS]: {reply}")
            speak_with_barge_in(reply, speaker, listener, hud)
            return reply
        if system_result == "SHUTDOWN_CYRUS":
            hud.set_state("SPEAKING", "TERMINATING CORE")
            preferred_name = str(load_user_state().get("preferred_name", "")).strip()
            goodbye = (
                f"Powering down completely. Goodbye, {preferred_name}."
                if preferred_name
                else "Powering down completely. Goodbye."
            )
            shutdown_cyrus_after_goodbye(speaker, hud, goodbye)
            return goodbye

        # If it's raw web search data, pass it to the brain for a natural 2-sentence voice summary
        if system_result.startswith("Search results for"):
            hud.set_state("THINKING", "SUMMARIZING SEARCH...")
            summary = brain.think(f"Summarize these web search results into 2 short conversational sentences: {system_result}")
            hud.append_log(f"[CYRUS]: {summary}")
            sources = list(dict.fromkeys(re.findall(r"https?://[^\s)]+", system_result)))
            if sources:
                hud.append_log("[SOURCES]: " + " | ".join(sources))
            speak_with_barge_in(summary, speaker, listener, hud)
            return summary
        else:
            hud.append_log(f"[CYRUS]: {system_result}")
            speak_with_barge_in(system_result, speaker, listener, hud)
            return system_result

    if tools.is_offline and brain.backend != "ollama":
        reply = "Offline mode is enabled. Local system commands still work, but online AI is unavailable."
        hud.append_log(f"[CYRUS]: {reply}")
        speak_with_barge_in(reply, speaker, listener, hud)
        return reply

    # 5. Conversational Reasoning
    hud.set_state("THINKING", "NEURAL COMPUTE...")
    reply = brain.think(query)
    hud.append_log(f"[CYRUS]: {reply}")

    # 6. Speak the response
    speak_with_barge_in(reply, speaker, listener, hud)
    return reply


def shutdown_cyrus_after_goodbye(speaker, hud, goodbye: str):
    speech_finished = threading.Event()

    def speak_goodbye():
        try:
            speaker.speak(goodbye)
        finally:
            speech_finished.set()

    def finish_shutdown():
        if not speech_finished.wait(timeout=5):
            speaker.stop()
        hud.shutdown_signal.emit()

    threading.Thread(
        target=speak_goodbye,
        name="CyrusShutdownSpeech",
        daemon=True,
    ).start()
    threading.Thread(
        target=finish_shutdown,
        name="CyrusShutdownTimeout",
        daemon=True,
    ).start()


def _sync_external_system_volume(hud, tools, previous_volume: int) -> int:
    current_volume = tools.get_system_master_volume(log_errors=False)
    if current_volume is None or current_volume == previous_volume:
        return previous_volume
    hud.volume_levels_signal.emit(current_volume, tools.player.volume)
    return current_volume


def assistant_worker(hud: DynamicIslandHUD, request_queue: Queue):
    hud.set_state("BOOTING", "INITIALIZING VOICE AND AI SERVICES...")
    features = load_installed_features()
    microphone_input_enabled = features["microphone_input"]
    hud.voice_output_initializing_signal.emit(features["alan_voice"])
    hud.microphone_input_status_signal.emit(microphone_input_enabled)
    speaker = SilentVoiceSpeaker()
    listener = None
    brain = None
    tools = None

    def load_speaker():
        nonlocal speaker
        if not features["alan_voice"]:
            request_queue.put(("speaker_ready", SilentVoiceSpeaker()))
            return
        try:
            loaded_speaker = VoiceSpeaker()
            loaded_speaker.on_status_change = lambda available: (
                hud.voice_output_status_signal.emit(True, available)
            )
            hud.voice_output_status_signal.emit(True, loaded_speaker.is_available)
        except Exception as error:
            print(f"[Error Loading Speaker]: {error}")
            hud.voice_output_status_signal.emit(True, False)
            loaded_speaker = SilentVoiceSpeaker()
        request_queue.put(("speaker_ready", loaded_speaker))

    def load_listener():
        nonlocal listener
        if not microphone_input_enabled:
            return
        try: listener = VoiceListener()
        except Exception as e: print(f"[Error Loading Listener]: {e}")

    def load_brain_tools():
        nonlocal brain, tools
        try:
            brain = CyrusBrain()
            tools = SystemTools()
        except Exception as e: print(f"[Error Loading Brain/Tools]: {e}")

    t_spk = threading.Thread(target=load_speaker)
    t_lis = threading.Thread(target=load_listener)
    t_brn = threading.Thread(target=load_brain_tools)

    t_spk.start()
    if microphone_input_enabled:
        t_lis.start()
    t_brn.start()

    if microphone_input_enabled:
        t_lis.join()
    t_brn.join()

    if not brain or not tools:
        print("[System Failure] Core subsystems failed to initialize.")
        hud.set_state("BOOTING", "INIT FAILURE")
        return

    def mark_backend_offline(error):
        hud.set_offline_mode(True)
        tools.set_offline_mode(True)
        if listener is not None:
            listener.set_offline_mode(True)
        hud.set_state("OFFLINE", "ENDPOINT UNREACHABLE // LOCAL MODE")
        hud.append_log(
            f"[OFFLINE] AI endpoint unreachable: {error}. "
            "Online features are disabled; local commands remain available."
        )

    brain.on_network_error = mark_backend_offline
    tools.on_network_error = mark_backend_offline

    if microphone_input_enabled and not listener:
        print("[TTS_WARNING]: Microphone listener failed to start — running without voice input.")
    if listener is not None:
        def report_microphone_status(message):
            hud.append_log(f"[MICROPHONE]: {message}")
            if message.startswith("Microphone unavailable"):
                hud.set_state("ERROR", "MICROPHONE UNAVAILABLE")
        listener.on_status_change = report_microphone_status

    tools.player.on_state_change = hud.set_music_state
    tools.player.on_error = lambda message: hud.append_log(
        f"[MUSIC ERROR]: {message}"
    )
    tools.on_external_action_error = lambda message: hud.append_log(
        f"[BROWSER ACTION ERROR]: {message}"
    )
    def on_reminder_due(message: str):
        hud.reminder_alert_signal.emit(message)

    tools.reminders.on_due = on_reminder_due
    tools.reminders.on_change = hud.reminders_changed_signal.emit
    tools.reminders.start()
    hud.reminders_changed_signal.emit(tools.reminders.list_reminders())
    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(tools.reminders.stop)
    if listener is not None:
        listener.set_offline_mode(tools.is_offline)
    player_volume = hud.player_volume_slider.value()
    tools.player.set_volume(player_volume)
    system_volume = tools.get_system_master_volume()
    hud.volume_levels_signal.emit(
        hud.system_volume_slider.value() if system_volume is None else system_volume,
        player_volume,
    )
    last_system_volume = (
        hud.system_volume_slider.value() if system_volume is None else system_volume
    )
    last_system_volume_poll = time.monotonic()

    # Link GUI Physical Mic Button to VoiceListener mute state
    if listener is not None:
        hud.mic_toggled_signal.connect(listener.set_muted)
    hud.offline_mode_signal.connect(tools.set_offline_mode)
    if listener is not None:
        hud.offline_mode_signal.connect(listener.set_offline_mode)
    if listener is not None:
        listener.set_muted(hud.is_mic_muted)

    def announce_online():
        profile = load_user_state()
        welcome_msg = contextual_greeting(
            str(profile.get("preferred_name", "")),
        )
        welcome_msg = welcome_msg.removesuffix(" How can I help?")
        welcome_msg = f"{welcome_msg} CYRUS online and standing by."
        hud.append_log(f"[CYRUS]: {welcome_msg}")
        hud.set_state("SPEAKING", "CYRUS ONLINE")
        def speak_welcome():
            speaker.speak(welcome_msg)
            hud.set_state(
                "MUTED" if hud.is_mic_muted else "IDLE",
                "MIC OFF // CHAT READY" if hud.is_mic_muted else "STANDBY",
            )
        threading.Thread(
            target=speak_welcome,
            name="CyrusWelcomeSpeech",
            daemon=True,
        ).start()

    def install_speaker(loaded_speaker):
        nonlocal speaker
        speaker = loaded_speaker
        speaker.set_volume(hud.voice_volume_slider.value())
        hud.voice_volume_changed_signal.connect(
            speaker.set_volume, Qt.ConnectionType.DirectConnection
        )
        hud.stop_speech_signal.connect(speaker.stop)
        app = QApplication.instance()
        cleanup = getattr(speaker, "cleanup_temp_files", None)
        if app is not None and cleanup is not None:
            app.aboutToQuit.connect(cleanup)
        if not getattr(install_speaker, "announced", False):
            install_speaker.announced = True
            announce_online()

    install_speaker.announced = False
    if not features["alan_voice"]:
        speaker = SilentVoiceSpeaker()
        install_speaker(speaker)
    else:
        hud.set_state(
            "MUTED" if hud.is_mic_muted else "IDLE",
            "MIC OFF // CHAT READY" if hud.is_mic_muted else "STANDBY",
        )

    # --- Initialize Global Hotkey Hook (F4/Ctrl+Space=Stop Speech, F3/Ctrl+M=Mic Toggle) ---
    hotkey_hook = HotkeyListener(
        on_mute_callback=lambda: speaker.stop(),
        on_toggle_callback=(
            hud.mic_toggle_requested_signal.emit if listener is not None else None
        ),
    )
    hotkey_hook.start()

    is_sleeping = False

    while True:
        try:
            try:
                request_type, payload = request_queue.get_nowait()
            except Empty:
                request_type, payload = None, None

            if request_type == "chat":
                action = process_query(
                    payload, speaker, listener, brain, tools, hud, source="CHAT"
                )
                if action == "SLEEP":
                    is_sleeping = True
                elif action == "WAKE":
                    is_sleeping = False
                continue
            if request_type == "speak":
                hud.set_state("SPEAKING", "FILE INSPECTED")
                speaker.speak(payload)
                hud.set_state("IDLE")
                continue
            if request_type == "speaker_ready":
                install_speaker(payload)
                continue
            if request_type == "music_control":
                controls = {
                    "toggle": tools.player.toggle_play_pause,
                    "previous": tools.player.previous_track,
                    "next": tools.player.next_track,
                    "stop": tools.player.stop,
                }
                control = controls.get(payload)
                if control:
                    hud.append_log(f"[PLAYER]: {control()}")
                continue
            if request_type == "system_volume":
                result = tools.set_system_master_volume(payload)
                hud.append_log(f"[SYSTEM VOLUME]: {result}")
                current_volume = tools.get_system_master_volume()
                if current_volume is not None:
                    last_system_volume = current_volume
                continue
            if request_type == "player_volume":
                result = tools.player.set_volume(payload)
                hud.append_log(f"[PLAYER VOLUME]: {result}")
                continue
            if request_type == "confirmed_action":
                result = tools.confirm_action(payload)
                hud.append_log(f"[ACTION]: {result}")
                if result == "CONFIRMED_SHUTDOWN_CYRUS":
                    shutdown_cyrus_after_goodbye(
                        speaker,
                        hud,
                        "Powering down completely. Goodbye.",
                    )
                continue

            current_time = time.monotonic()
            if current_time - last_system_volume_poll >= 0.5:
                last_system_volume = _sync_external_system_volume(
                    hud,
                    tools,
                    last_system_volume,
                )
                last_system_volume_poll = current_time

            # Check if microphone is physically muted via button or hotkey
            if (
                listener is None
                or hud.is_mic_muted
                or listener.is_offline
            ):
                time.sleep(0.15)
                continue

            if not is_sleeping:
                hud.set_state("LISTENING", "MIC ON // SPEAK NOW")

            # 1.0s timeout ensures responsive mic mute checking without hanging
            audio = listener.listen_and_record(timeout=1.0, phrase_time_limit=10.0)
            if audio is None:
                continue

            hud.set_state("THINKING", "CAPTURING VOICE...")
            query = listener.transcribe(audio)

            if not query or len(query.strip()) < 2:
                hud.set_state("LISTENING", "MIC ON // SPEAK NOW")
                continue

            hud.append_log(f"[VOICE INPUT]: {query}")
            # Process voice query through unified handler
            action = process_query(query, speaker, listener, brain, tools, hud, source="VOICE")
            if action == "SLEEP":
                is_sleeping = True
            elif action == "WAKE":
                is_sleeping = False

        except Exception as e:
            print(f"[Loop Exception]: {e}")
            time.sleep(0.5)


def main():
    app = QApplication(sys.argv)
    hud = DynamicIslandHUD()
    hud.shutdown_signal.connect(app.quit)
    hud.show()

    request_queue = Queue()

    file_inspection_notifier = FileInspectionNotifier(hud, request_queue)

    # Keep metadata and preview reads off the GUI thread.
    def on_file_inspected(file_path):
        hud.set_state("THINKING", f"INSPECTING {os.path.basename(file_path)}")
        worker = FileInspectionWorker(file_path)
        worker.completed.connect(file_inspection_notifier.show_result)
        worker.failed.connect(file_inspection_notifier.show_error)
        threading.Thread(
            target=worker.run,
            name="CyrusFileInspection",
            daemon=True,
        ).start()

    hud.file_inspected_signal.connect(on_file_inspected)

    hud.text_command_signal.connect(
        lambda query: request_queue.put(("chat", query))
    )
    hud.music_control_signal.connect(
        lambda control: request_queue.put(("music_control", control))
    )
    hud.system_volume_changed_signal.connect(
        lambda level: request_queue.put(("system_volume", level))
    )
    hud.player_volume_changed_signal.connect(
        lambda level: request_queue.put(("player_volume", level))
    )
    hud.confirmed_action_signal.connect(
        lambda action: request_queue.put(("confirmed_action", action))
    )

    def start_runtime():
        startup_check_notifier = StartupCheckNotifier(app, hud)
        startup_check_worker = StartupCheckWorker()
        startup_check_worker.completed.connect(
            startup_check_notifier.show_warnings
        )
        startup_check_worker.failed.connect(
            startup_check_notifier.show_check_error
        )

        def start_assistant():
            threading.Thread(
                target=assistant_worker,
                args=(hud, request_queue),
                name="CyrusAssistant",
                daemon=True,
            ).start()

        startup_check_notifier.finished.connect(start_assistant)
        hud.set_state("BOOTING", "CHECKING SYSTEM REQUIREMENTS...")
        startup_check_worker.status.connect(hud.set_state)
        startup_thread = threading.Thread(
            target=startup_check_worker.run,
            name="CyrusStartupChecks",
            daemon=True,
        )
        startup_thread.start()

    startup_coordinator = StartupCoordinator(hud, start_runtime)
    QTimer.singleShot(0, startup_coordinator.start)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
