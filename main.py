import os
import sys
from queue import Empty, Queue

import time
import threading
import mimetypes
import re

# Load .env before importing assistant modules that read runtime settings.
from config import settings as _runtime_settings
from config.features import load_installed_features
from core.speaker import SilentVoiceSpeaker, VoiceSpeaker, preload_piper_runtime

preload_piper_runtime()

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot

from core.listener import VoiceListener
from core.brain import CyrusBrain
from services.system_tools import SystemTools
from gui.dynamic_island import DynamicIslandHUD
from memory.memory_manager import add_note, load_memory
from services.vision_service import analyze_screen
from services.hotkey_service import HotkeyListener
from services.startup_check import check_startup_requirements, startup_check_warnings


class StartupCheckWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self):
        try:
            checks = check_startup_requirements()
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(startup_check_warnings(checks))


class StartupCheckNotifier(QObject):
    @pyqtSlot(object)
    def show_warnings(self, warnings):
        if not warnings:
            return
        warning_dialog = QMessageBox(
            QMessageBox.Icon.Warning,
            "CYRUS Setup Check",
            "Some features may not be ready. CYRUS will still open.",
        )
        warning_dialog.setDetailedText(
            "\n".join(f"{check.name}: {check.details}" for check in warnings)
        )
        warning_dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        warning_dialog.exec()

    @pyqtSlot(str)
    def show_check_error(self, message):
        QMessageBox.warning(
            None,
            "CYRUS Setup Check",
            f"Could not complete the setup check: {message}\nCYRUS will still open.",
        )


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
    if greeting in {"hello", "hello cyrus", "hi", "hi cyrus", "hey", "hey cyrus"}:
        reply = "Hello! How can I help?"
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
        reply = "Online and listening, sir."
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
            speaker.speak("Powering down completely. Goodbye, sir.")
            os._exit(0)

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


def _sync_external_system_volume(hud, tools, previous_volume: int) -> int:
    current_volume = tools.get_system_master_volume(log_errors=False)
    if current_volume is None or current_volume == previous_volume:
        return previous_volume
    hud.volume_levels_signal.emit(current_volume, tools.player.volume)
    return current_volume


def assistant_worker(hud: DynamicIslandHUD, request_queue: Queue):
    features = load_installed_features()
    microphone_input_enabled = features["microphone_input"]
    hud.voice_output_status_signal.emit(
        features["alan_voice"],
        features["alan_voice"],
    )
    hud.set_microphone_input_enabled(microphone_input_enabled)
    speaker = None
    listener = None
    brain = None
    tools = None

    def load_speaker():
        nonlocal speaker
        if not features["alan_voice"]:
            speaker = SilentVoiceSpeaker()
            return
        try:
            speaker = VoiceSpeaker()
            hud.voice_output_status_signal.emit(True, True)
        except Exception as error:
            print(f"[Error Loading Speaker]: {error}")
            hud.voice_output_status_signal.emit(True, False)
            speaker = SilentVoiceSpeaker()

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

    t_spk.join()
    if microphone_input_enabled:
        t_lis.join()
    t_brn.join()

    if not speaker or (microphone_input_enabled and not listener) or not brain or not tools:
        print("[System Failure] Core subsystems failed to initialize.")
        hud.set_state("BOOTING", "INIT FAILURE")
        return

    tools.player.on_state_change = hud.set_music_state
    tools.reminders.on_due = hud.reminder_alert_signal.emit
    tools.reminders.on_change = hud.reminders_changed_signal.emit
    hud.reminders_changed_signal.emit(tools.reminders.list_reminders())
    if listener is not None:
        listener.set_offline_mode(tools.is_offline)
    speaker.set_volume(hud.voice_volume_slider.value())
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
    hud.voice_volume_changed_signal.connect(
        speaker.set_volume, Qt.ConnectionType.DirectConnection
    )
    hud.offline_mode_signal.connect(tools.set_offline_mode)
    if listener is not None:
        hud.offline_mode_signal.connect(listener.set_offline_mode)
    hud.stop_speech_signal.connect(speaker.stop)
    if listener is not None:
        listener.set_muted(hud.is_mic_muted)

    # --- Initialize Global Hotkey Hook (F4/Ctrl+Space=Stop Speech, F3/Ctrl+M=Mic Toggle) ---
    hotkey_hook = HotkeyListener(
        on_mute_callback=speaker.stop,
        on_toggle_callback=hud.toggle_mic if listener is not None else None
    )
    hotkey_hook.start()

    welcome_msg = "At your service, sir. Cyrus online and standing by."
    hud.append_log(f"[CYRUS]: {welcome_msg}")
    hud.set_state("SPEAKING", "CYRUS ONLINE")
    speaker.speak(welcome_msg)
    hud.set_state("IDLE")

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
                    speaker.speak("Powering down completely. Goodbye.")
                    os._exit(0)
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
                hud.set_state("IDLE")

            # 1.0s timeout ensures responsive mic mute checking without hanging
            audio = listener.listen_and_record(timeout=1.0, phrase_time_limit=10.0)
            if audio is None:
                continue

            hud.set_state("THINKING", "CAPTURING VOICE...")
            query = listener.transcribe(audio)

            if not query or len(query.strip()) < 2:
                hud.set_state("IDLE")
                continue

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
    hud.show()

    startup_check_notifier = StartupCheckNotifier(app)
    startup_check_worker = StartupCheckWorker()
    startup_check_worker.completed.connect(startup_check_notifier.show_warnings)
    startup_check_worker.failed.connect(startup_check_notifier.show_check_error)
    threading.Thread(
        target=startup_check_worker.run,
        name="CyrusStartupChecks",
        daemon=True,
    ).start()

    # Wire up universal file inspection signal
    def on_file_inspected(file_path):
        if not os.path.exists(file_path):
            return

        hud.set_state("THINKING", f"INSPECTING {os.path.basename(file_path)}")
        
        file_name = os.path.basename(file_path)
        file_size_kb = round(os.path.getsize(file_path) / 1024, 2)
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "Unknown/Binary"
        ext = os.path.splitext(file_name)[1].lower() or "No Extension"

        summary = f"File: {file_name}\nType: {mime_type} ({ext})\nSize: {file_size_kb} KB\n"

        text_extensions = ['.txt', '.py', '.js', '.json', '.html', '.css', '.md', '.log', '.csv', '.cpp', '.c', '.sh']
        if ext in text_extensions or "text" in mime_type:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(500)
                    summary += f"\nPreview:\n{content}..."
            except Exception as e:
                summary += f"\nError reading preview: {e}"
        else:
            summary += "\nBinary structure detected."

        hud.append_log(f"[FILE_INSPECTOR]:\n{summary}")
        
        spoken_text = f"File {file_name} loaded. Format is {mime_type}, size {file_size_kb} kilobytes."
        request_queue.put(("speak", spoken_text))

    hud.file_inspected_signal.connect(on_file_inspected)

    request_queue = Queue()
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

    worker = threading.Thread(
        target=assistant_worker, args=(hud, request_queue), daemon=True
    )
    worker.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
