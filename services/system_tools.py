import os
import sys
import re
import difflib
import time
import subprocess
import threading
import urllib.parse
import webbrowser
import platform
import shutil
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import psutil
import pyautogui
import requests
from ddgs import DDGS
import yt_dlp
import vlc

from memory.memory_manager import add_note, load_memory
from config.features import load_installed_features
from config.user_state import load_user_state, save_user_state
from services.reminder_service import ReminderService, parse_reminder_command

try:
    import winreg
except ImportError:
    winreg = None

try:
    from pycaw.pycaw import AudioUtilities
except ImportError:
    AudioUtilities = None


_COMMAND_TERMS = (
    "system", "spec", "specs", "specification", "specifications",
    "hardware", "report", "health", "update", "usage", "memory", "ram",
    "cpu", "disk", "computer", "live", "current", "utilization",
    "processor", "gpu", "graphics", "queue", "next", "previous",
    "song", "music", "player", "track", "play", "add", "volume",
)


def _correct_command_typos(query: str) -> str:
    """Correct only near-matches to known command words, preserving other text."""
    words = re.split(r"(\W+)", query)
    corrected = []
    for word in words:
        if len(word) < 4 or not word.isalpha():
            corrected.append(word)
            continue
        normalized = word.lower()
        match = difflib.get_close_matches(
            normalized, _COMMAND_TERMS, n=1, cutoff=0.76
        )
        corrected.append(match[0] if match else word)
    return "".join(corrected)


class CyrusPlayer:
    def __init__(self):
        self.vlc_instance = vlc.Instance("--no-video", "--quiet")
        self.media_player = self.vlc_instance.media_player_new()
        self.is_playing = False
        self.is_paused = False
        self.is_loading = False
        self.current_title = ""
        self.volume = 100
        self.queue = []
        self.queue_index = -1
        self.on_state_change = None
        self._lock = threading.RLock()
        self._generation = 0
        self._queue_generation = 0
        self.media_player.event_manager().event_attach(
            vlc.EventType.MediaPlayerEndReached, self._on_track_end
        )

    def play_song(self, query: str) -> str:
        query = query.strip()
        if not query:
            return "Tell me which song or artist to play."

        with self._lock:
            self.media_player.stop()
            self._generation += 1
            self._queue_generation += 1
            queue_generation = self._queue_generation
            self.queue = []
            self.queue_index = -1
            self.is_playing = False
            self.is_paused = False
            self.is_loading = True
            self.current_title = query
        self._notify("Searching", visible=True)

        def _search_and_play():
            try:
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    search = ydl.extract_info(
                        f"ytsearch5:{query}", download=False
                    )
                    tracks = self._tracks_from_search(search, query)

                if not tracks:
                    raise ValueError("No matching tracks were found.")
                with self._lock:
                    if queue_generation != self._queue_generation:
                        return
                    self.queue = tracks
                    self.queue_index = 0
                self._play_queue_index(0)
            except Exception as e:
                print(f"[Player Error]: {e}")
                with self._lock:
                    if queue_generation != self._queue_generation:
                        return
                    self.is_loading = False
                    self.is_playing = False
                    self.is_paused = False
                    self.current_title = "Playback unavailable"
                self._notify("Could not load music", visible=False)

        threading.Thread(target=_search_and_play, daemon=True).start()
        return f"Finding {query}."

    @staticmethod
    def _tracks_from_search(search, query: str) -> list[dict[str, str]]:
        entries = search.get("entries") or []
        return [
            {
                "title": entry.get("title") or query,
                "url": (
                    entry.get("webpage_url")
                    or (
                        entry.get("url")
                        if str(entry.get("url", "")).startswith("http")
                        else f"https://www.youtube.com/watch?v={entry['id']}"
                    )
                ),
            }
            for entry in entries
            if entry and entry.get("id")
        ]

    def add_to_queue(self, query: str, play_next: bool = False) -> str:
        query = query.strip()
        if not query:
            return "Tell me which song to add to the queue."
        with self._lock:
            if not self.queue:
                if self.is_loading:
                    return "A music search is already loading; try adding the song again shortly."
                return self.play_song(query)
            queue_generation = self._queue_generation
        self._notify("Finding next track" if play_next else "Adding to queue")

        def _search_and_add():
            try:
                options = {"quiet": True, "no_warnings": True, "extract_flat": True}
                with yt_dlp.YoutubeDL(options) as ydl:
                    search = ydl.extract_info(f"ytsearch5:{query}", download=False)
                tracks = self._tracks_from_search(search, query)
                if not tracks:
                    raise ValueError("No matching tracks were found.")
                with self._lock:
                    if queue_generation != self._queue_generation:
                        return
                    if play_next:
                        insert_at = self.queue_index + 1
                        self.queue[insert_at:insert_at] = tracks
                    else:
                        self.queue.extend(tracks)
                    title = tracks[0]["title"]
                self._notify(
                    "Added to play next" if play_next else "Added to queue",
                    visible=True,
                )
                print(f"[Player]: Added {title} {'next' if play_next else 'to the queue'}.")
            except Exception as e:
                print(f"[Player Error]: Could not add {query} to the queue: {e}")
                self._notify("Could not add to queue", visible=True)

        threading.Thread(target=_search_and_add, daemon=True).start()
        return f"Finding {query} to play {'next' if play_next else 'later'}."

    def add_current_to_queue(self, play_next: bool = False) -> str:
        with self._lock:
            if not self.queue or not 0 <= self.queue_index < len(self.queue):
                return "There is no current song to add."
            track = dict(self.queue[self.queue_index])
            if play_next:
                self.queue.insert(self.queue_index + 1, track)
            else:
                self.queue.append(track)
        self._notify("Added to play next" if play_next else "Added to queue")
        return (
            f"Added {track['title']} to play next."
            if play_next else f"Added {track['title']} to the queue."
        )

    def set_volume(self, level_percent: int) -> str:
        level_percent = max(0, min(100, int(level_percent)))
        with self._lock:
            if self.queue:
                result = self.media_player.audio_set_volume(level_percent)
                if result < 0:
                    return "The music player could not change its volume."
            self.volume = level_percent
            active = bool(self.queue)
        if active:
            return f"Music player volume set to {level_percent} percent."
        return (
            f"Music player volume set to {level_percent} percent; "
            "it will apply to the next song."
        )

    def adjust_volume(self, delta: int) -> str:
        with self._lock:
            new_volume = max(0, min(100, self.volume + delta))
        return self.set_volume(new_volume)

    def _notify(self, status: str, visible: bool = True):
        callback = self.on_state_change
        if callback:
            callback(self.current_title, status, visible, self.is_playing)

    def _play_queue_index(self, index: int):
        with self._lock:
            if not self.queue:
                self.is_loading = False
                self._notify("Queue is empty", visible=False)
                return
            if index < 0 or index >= len(self.queue):
                self.is_playing = False
                self.is_paused = False
                self.is_loading = False
                self._notify("Queue finished", visible=False)
                return
            self._generation += 1
            generation = self._generation
            self.queue_index = index
            track = self.queue[self.queue_index]
            self.current_title = track["title"]
            self.is_loading = True
            self.is_playing = False
            self.is_paused = False
        self._notify("Loading", visible=True)

        def _resolve_and_play():
            try:
                options = {
                    "format": "bestaudio/best",
                    "quiet": True,
                    "no_warnings": True,
                }
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(track["url"], download=False)
                audio_url = info.get("url")
                if not audio_url:
                    raise ValueError("No playable audio stream was returned.")
                media = self.vlc_instance.media_new(audio_url)
                with self._lock:
                    if generation != self._generation:
                        return
                    self.media_player.set_media(media)
                    if self.media_player.audio_set_volume(self.volume) < 0:
                        raise RuntimeError("VLC could not set the player volume.")
                    self.media_player.play()
                    self.current_title = info.get("title") or track["title"]
                    self.is_loading = False
                    self.is_playing = True
                    self.is_paused = False
                self._notify("Playing", visible=True)
            except Exception as e:
                print(f"[Player Error]: Could not load {track['title']}: {e}")
                with self._lock:
                    if generation != self._generation:
                        return
                    self.is_loading = False
                    self.is_playing = False
                self._notify("Playback unavailable", visible=False)

        threading.Thread(target=_resolve_and_play, daemon=True).start()

    def next_track(self) -> str:
        with self._lock:
            if not self.queue:
                return "No music queue is available."
            next_index = self.queue_index + 1
            if next_index >= len(self.queue):
                self.stop()
                return "The end of the music queue was reached."
        self._play_queue_index(next_index)
        return "Loading the next track."

    def previous_track(self) -> str:
        with self._lock:
            if not self.queue:
                return "No music queue is available."
            previous_index = self.queue_index - 1
            if previous_index < 0:
                return "This is the first track in the queue."
        self._play_queue_index(previous_index)
        return "Loading the previous track."

    def toggle_play_pause(self) -> str:
        with self._lock:
            if self.is_loading:
                return "The track is still loading."
            if not self.queue:
                return "No music is queued."
            if self.is_paused:
                return self.resume()
            if self.is_playing:
                return self.pause()
            return "No track is ready to play."

    def pause(self) -> str:
        with self._lock:
            if self.is_playing:
                self.media_player.set_pause(1)
                self.is_playing = False
                self.is_paused = True
                self._notify("Paused")
                return "Playback paused."
        return "No media actively playing."

    def resume(self) -> str:
        with self._lock:
            if self.is_paused and self.queue:
                self.media_player.set_pause(0)
                self.is_playing = True
                self.is_paused = False
                self._notify("Playing")
                return "Playback resumed."
        return "No paused track to resume."

    def _on_track_end(self, _event):
        with self._lock:
            if not self.is_playing or not self.queue:
                return
            next_index = self.queue_index + 1
            if next_index >= len(self.queue):
                self.is_playing = False
                self.is_paused = False
                self._notify("Queue finished", visible=False)
                return
        self._play_queue_index(next_index)

    def stop(self) -> str:
        with self._lock:
            self.media_player.stop()
            self._generation += 1
            self.is_playing = False
            self.is_paused = False
            self.is_loading = False
            self.queue = []
            self.queue_index = -1
            self._notify("Stopped", visible=False)
        return "Playback stopped."


class UnavailableCyrusPlayer:
    def __init__(self):
        self.volume = 100
        self.on_state_change = None

    @staticmethod
    def _unavailable():
        return "Music playback was not selected during CYRUS setup."

    def play_song(self, _query: str) -> str:
        return self._unavailable()

    def set_volume(self, _level_percent: int) -> str:
        return self._unavailable()

    def next_track(self) -> str:
        return self._unavailable()

    def previous_track(self) -> str:
        return self._unavailable()

    def toggle_play_pause(self) -> str:
        return self._unavailable()

    def pause(self) -> str:
        return self._unavailable()

    def resume(self) -> str:
        return self._unavailable()

    def stop(self) -> str:
        return self._unavailable()


class SystemTools:
    def __init__(self):
        self.features = load_installed_features()
        if self.features["vlc_music"]:
            try:
                self.player = CyrusPlayer()
            except (vlc.VLCException, OSError, AttributeError) as error:
                print(f"[Player Warning]: VLC is unavailable: {error}")
                self.player = UnavailableCyrusPlayer()
        else:
            self.player = UnavailableCyrusPlayer()
        state = load_user_state()
        self.is_offline = bool(
            state.get("offline_mode", False)
            or os.getenv("CYRUS_OFFLINE_MODE", "").strip().lower() in {"1", "true", "yes"}
        )
        self.weather_favorites = state.get("weather_favorites", {})
        if not isinstance(self.weather_favorites, dict):
            self.weather_favorites = {}
        self.reminders = ReminderService()

    def set_offline_mode(self, enabled: bool) -> None:
        self.is_offline = bool(enabled)
        if getattr(self, "is_offline", False):
            self.player.stop()
        state = load_user_state()
        state["offline_mode"] = self.is_offline
        if not save_user_state(state):
            print("[Offline Mode Error]: The setting could not be persisted.")

    def add_weather_favorite(self, name: str, location: str) -> str:
        name = name.strip().lower()
        location = location.strip()
        if not name or not location:
            return "Tell me a place and a short favorite name, such as 'save London as weather favorite home'."
        previous_location = self.weather_favorites.get(name)
        self.weather_favorites[name] = location
        state = load_user_state()
        state["weather_favorites"] = self.weather_favorites
        if not save_user_state(state):
            if previous_location is None:
                self.weather_favorites.pop(name, None)
            else:
                self.weather_favorites[name] = previous_location
            return "I couldn't save that weather favorite. Check local storage permissions and try again."
        return f"Saved {location} as weather favorite '{name}'."

    def _weather_favorites_reply(self) -> str:
        if not self.weather_favorites:
            return "You have no saved weather favorites yet."
        saved = ", ".join(
            f"{name}: {place}" for name, place in sorted(self.weather_favorites.items())
        )
        return f"Weather favorites: {saved}."

    # --- Windows Volume Control ---
    @staticmethod
    def get_system_master_volume(log_errors: bool = True) -> int | None:
        try:
            speakers = AudioUtilities.GetSpeakers()
            if hasattr(speakers, "EndpointVolume"):
                scalar = speakers.EndpointVolume.GetMasterVolumeLevelScalar()
            else:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume

                endpoint = getattr(speakers, "Endpoint", speakers)
                interface = endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                scalar = volume.GetMasterVolumeLevelScalar()
            return max(0, min(100, round(float(scalar) * 100)))
        except Exception as error:
            if log_errors:
                print(f"[Volume Error]: Could not read system volume: {error}")
            return None

    @staticmethod
    def set_system_master_volume(level_percent: int) -> str:
        try:
            level_percent = max(0, min(100, level_percent))
            scalar = level_percent / 100.0
            speakers = AudioUtilities.GetSpeakers()
            if hasattr(speakers, 'EndpointVolume'):
                speakers.EndpointVolume.SetMasterVolumeLevelScalar(scalar, None)
            else:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume
                endpoint = getattr(speakers, "Endpoint", speakers)
                interface = endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMasterVolumeLevelScalar(scalar, None)
            return f"System volume set to {level_percent} percent."
        except Exception as e:
            return f"Failed to adjust system volume: {e}"

    def search_web(self, query: str) -> str:
        """Returns web or news search snippets with source links."""
        if not getattr(self, "features", load_installed_features())["web_news"]:
            return "Web search and news were not selected during CYRUS setup."
        if getattr(self, "is_offline", False):
            return "Offline mode is enabled, so live web search is unavailable."
        try:
            clean_query = re.sub(
                r"^\s*(?:(?:please\s+)?(?:search(?:\s+the\s+web)?|google|look\s+up|find\s+out)"
                r"\s*(?:for|about)?\s*)",
                "",
                query,
                flags=re.IGNORECASE,
            ).strip(" .,!?:;")

            if not clean_query:
                return "What would you like me to search for?"

            is_news_search = any(
                marker in clean_query.lower()
                for marker in (
                    "news",
                    "headline",
                    "headlines",
                    "current events",
                    "breaking",
                )
            )
            results = []
            with DDGS() as ddgs:
                search = ddgs.news if is_news_search else ddgs.text
                for result in search(clean_query, max_results=5):
                    title = result.get("title", "").strip()
                    body = result.get("body", "").strip()
                    url = result.get("href") or result.get("url", "")
                    if body:
                        source = f"{title}: " if title else ""
                        source += body
                        if is_news_search:
                            publisher = result.get("source", "").strip()
                            published = result.get("date", "").strip()
                            if publisher:
                                source += f" — {publisher}"
                            if published:
                                source += f", {published}"
                        if url:
                            source += f" ({url})"
                        results.append(source)

            if results:
                combined = " ".join(results)[:1800]
                return f"Search results for {clean_query}: {combined}"
            return f"I couldn't find any relevant web search results for {clean_query}."
        except Exception as e:
            return f"Web search encountered an issue: {e}"

    # --- Hardware Identification ---
    @staticmethod
    def get_cpu_name() -> str:
        try:
            if winreg is None:
                return platform.processor() or "Unknown CPU"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return cpu_name.strip()
        except Exception:
            return platform.processor() or "Unknown CPU"

    @staticmethod
    def get_gpu_name() -> str:
        try:
            if AudioUtilities is None:
                return "System volume control is unavailable on this platform."
            cmd = "nvidia-smi --query-gpu=name --format=csv,noheader"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().split("\n")[0].strip()
        except Exception:
            pass

        try:
            cmd = 'powershell -Command "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                names = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
                dedicated = [g for g in names if "nvidia" in g.lower() or "rtx" in g.lower() or "radeon" in g.lower()]
                if dedicated:
                    return dedicated[0]
                return ", ".join(names)
        except Exception:
            pass
        return "Integrated Display Adapter"

    @staticmethod
    def get_cpu_temp() -> str:
        try:
            cmd = 'powershell -Command "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                raw = float(res.stdout.strip().split("\n")[0])
                celsius = round((raw / 10.0) - 273.15, 1)
                if celsius > 0:
                    return f"{celsius}°C"
        except Exception:
            pass
        return ""

    @staticmethod
    def get_gpu_telemetry() -> tuple[str, str]:
        try:
            cmd = "nvidia-smi --query-gpu=temperature.gpu,utilization.gpu --format=csv,noheader,nounits"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                temp, util = [x.strip() for x in res.stdout.strip().split(",")]
                return f"{temp}°C", f"{util}%"
        except Exception:
            pass
        return "", ""

    # --- Specific Specs Responses ---
    def get_cpu_spec(self) -> str:
        script = (
            "Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,"
            "NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,CurrentClockSpeed,"
            "AddressWidth,VirtualizationFirmwareEnabled | ConvertTo-Json -Compress"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            processors = json.loads(result.stdout)
            processors = processors if isinstance(processors, list) else [processors]
            details = []
            for processor in processors:
                virtualization = processor.get("VirtualizationFirmwareEnabled")
                details.append(
                    f"{processor.get('Name') or self.get_cpu_name()} "
                    f"(manufacturer {processor.get('Manufacturer') or 'unavailable'}): "
                    f"{processor.get('NumberOfCores', 'unknown')} cores, "
                    f"{processor.get('NumberOfLogicalProcessors', 'unknown')} threads, "
                    f"current/max clock {processor.get('CurrentClockSpeed', 'unknown')}/"
                    f"{processor.get('MaxClockSpeed', 'unknown')} MHz, "
                    f"{processor.get('AddressWidth', 'unknown')}-bit, "
                    f"firmware virtualization "
                    f"{'enabled' if virtualization is True else 'disabled' if virtualization is False else 'unavailable'}"
                )
            if details:
                return "CPU specifications: " + "; ".join(details) + "."
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, AttributeError) as e:
            print(f"[System Specs Error]: CPU inventory query failed: {e}")

        return (
            f"CPU specifications: {self.get_cpu_name()}, "
            f"{psutil.cpu_count(logical=False)} physical cores, "
            f"{psutil.cpu_count(logical=True)} logical processors. "
            "Detailed clock and architecture information is unavailable."
        )

    @staticmethod
    def _get_nvidia_gpu_memory() -> dict[str, str]:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            memory_by_name = {}
            for line in result.stdout.splitlines():
                name, separator, memory_mb = line.rpartition(",")
                if separator:
                    memory_by_name[name.strip().lower()] = memory_mb.strip()
            return memory_by_name
        except (OSError, subprocess.SubprocessError):
            return {}

    def get_gpu_spec(self) -> str:
        script = (
            "Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,"
            "AdapterRAM,VideoModeDescription,CurrentRefreshRate | ConvertTo-Json -Compress"
        )
        nvidia_memory = self._get_nvidia_gpu_memory()
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            adapters = json.loads(result.stdout)
            adapters = adapters if isinstance(adapters, list) else [adapters]
            details = []
            for adapter in adapters:
                name = adapter.get("Name") or "graphics adapter name unavailable"
                memory_bytes = adapter.get("AdapterRAM")
                actual_memory = next(
                    (
                        memory_mb
                        for gpu_name, memory_mb in nvidia_memory.items()
                        if gpu_name in name.lower() or name.lower() in gpu_name
                    ),
                    None,
                )
                if actual_memory:
                    memory = f"{actual_memory} MB dedicated VRAM (nvidia-smi)"
                elif memory_bytes and memory_bytes != 4294967295:
                    memory = f"{memory_bytes / (1024 ** 3):.1f} GB reported adapter memory"
                elif memory_bytes == 4294967295:
                    memory = "adapter memory exceeds the Windows reporting limit"
                else:
                    memory = "adapter memory unavailable"
                details.append(
                    f"{name}; {memory}; "
                    f"driver {adapter.get('DriverVersion') or 'unavailable'}; "
                    f"display mode {adapter.get('VideoModeDescription') or 'unavailable'}; "
                    f"refresh {adapter.get('CurrentRefreshRate') or 'unavailable'} Hz"
                )
            if details:
                return "GPU specifications: " + "; ".join(details) + "."
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, AttributeError) as e:
            print(f"[System Specs Error]: GPU inventory query failed: {e}")

        return (
            f"GPU specifications: {self.get_gpu_name()}. "
            "Detailed adapter and display information is unavailable."
        )

    def get_ram_spec(self) -> str:
        total_memory = psutil.virtual_memory().total
        modules = []
        script = (
            "Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer,PartNumber,"
            "Capacity,Speed,ConfiguredClockSpeed,FormFactor,SMBIOSMemoryType,DeviceLocator "
            "| ConvertTo-Json -Compress"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            modules = json.loads(result.stdout)
            modules = (
                []
                if modules is None
                else modules if isinstance(modules, list) else [modules]
            )
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, AttributeError) as e:
            print(f"[System Specs Error]: RAM inventory query failed: {e}")

        type_names = {24: "DDR3", 26: "DDR4", 34: "DDR5"}
        form_names = {8: "DIMM", 12: "SO-DIMM"}
        parts = [f"Installed RAM: {total_memory / (1024 ** 3):.1f} GB"]
        for index, module in enumerate(modules, start=1):
            capacity = module.get("Capacity")
            size = f"{int(capacity) / (1024 ** 3):.1f} GB" if capacity else "capacity unavailable"
            speed = module.get("ConfiguredClockSpeed") or module.get("Speed")
            memory_type = type_names.get(
                module.get("SMBIOSMemoryType"), "memory type unavailable"
            )
            form_factor = form_names.get(
                module.get("FormFactor"), "form factor unavailable"
            )
            vendor = " ".join(
                str(module.get(key)).strip()
                for key in ("Manufacturer", "PartNumber")
                if module.get(key) and str(module.get(key)).strip()
            ) or "module identification unavailable"
            slot = module.get("DeviceLocator") or "slot unavailable"
            speed_text = f"{speed} MHz" if speed else "speed unavailable"
            parts.append(
                f"Module {index}: {size}, {memory_type}, {speed_text}, "
                f"{form_factor}, {vendor}, slot {slot}"
            )
        if not modules:
            parts.append("Module count, type, speed, and slot details are unavailable.")
        return "RAM specifications: " + "; ".join(parts) + "."

    def get_full_specs(self) -> str:
        specs = []
        powershell_script = r"""
$ErrorActionPreference = 'Stop'
$computer = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, CurrentClockSpeed, AddressWidth, Architecture, VirtualizationFirmwareEnabled
$board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product, Version
$bios = Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate
$gpus = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, AdapterRAM, VideoModeDescription, CurrentRefreshRate)
$memory = @(Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer, PartNumber, Capacity, Speed, ConfiguredClockSpeed, FormFactor, MemoryType, SMBIOSMemoryType, DataWidth, TotalWidth, DeviceLocator, BankLabel)
$drives = @(Get-CimInstance Win32_DiskDrive | Select-Object Model, MediaType, InterfaceType, Size, FirmwareRevision)
if (Get-Command Get-PhysicalDisk -ErrorAction SilentlyContinue) {
  $physicalDisks = @(Get-PhysicalDisk | Select-Object FriendlyName, MediaType, BusType, Size, HealthStatus, OperationalStatus)
} else {
  $physicalDisks = @()
}
$network = @(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled=True" | Select-Object Description, MACAddress, IPAddress, DefaultIPGateway, DNSServerSearchOrder, DHCPEnabled)
$result = [ordered]@{
  Computer = [ordered]@{ Manufacturer = $computer.Manufacturer; Model = $computer.Model; SystemType = $computer.SystemType }
  OperatingSystem = [ordered]@{ Caption = $os.Caption; Version = $os.Version; BuildNumber = $os.BuildNumber; OSArchitecture = $os.OSArchitecture; WindowsDirectory = $os.WindowsDirectory }
  Processor = @($cpu)
  Baseboard = @($board)
  BIOS = @($bios)
  Graphics = $gpus
  MemoryModules = $memory
  PhysicalDrives = $drives
  PhysicalDiskHealth = $physicalDisks
  NetworkAdapters = $network
}
ConvertTo-Json -InputObject $result -Depth 5 -Compress
"""
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", powershell_script],
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
            inventory = json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
            print(f"[System Specs Error]: Windows hardware inventory query failed: {e}")
            inventory = {}

        def as_items(value):
            if value is None:
                return []
            return value if isinstance(value, list) else [value]

        def format_bytes(value):
            try:
                size = float(value)
            except (TypeError, ValueError):
                return "unavailable"
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if size < 1024 or unit == "TB":
                    return f"{size:.1f} {unit}"
                size /= 1024

        computer = inventory.get("Computer", {})
        specs.append(
            "System: "
            + " ".join(
                str(computer.get(key))
                for key in ("Manufacturer", "Model", "SystemType")
                if computer.get(key)
            )
            if computer
            else f"System: {platform.node()} ({platform.machine() or 'architecture unavailable'})"
        )

        operating_system = inventory.get("OperatingSystem", {})
        if operating_system:
            os_details = " ".join(
                str(operating_system.get(key))
                for key in ("Caption", "OSArchitecture", "Version", "BuildNumber")
                if operating_system.get(key)
            )
        else:
            os_details = f"{platform.system()} {platform.release()} {platform.version()} ({platform.machine()})"
        specs.append(f"Operating system: {os_details}")

        processors = as_items(inventory.get("Processor"))
        if processors:
            for index, processor in enumerate(processors, start=1):
                specs.append(
                    f"CPU {index}: {processor.get('Name') or 'name unavailable'}; "
                    f"{processor.get('NumberOfCores', 'unknown')} cores, "
                    f"{processor.get('NumberOfLogicalProcessors', 'unknown')} threads; "
                    f"current/max clock "
                    f"{processor.get('CurrentClockSpeed', 'unknown')}/"
                    f"{processor.get('MaxClockSpeed', 'unknown')} MHz; "
                    f"{processor.get('AddressWidth', 'unknown')}-bit; "
                    f"manufacturer {processor.get('Manufacturer') or 'unknown'}"
                )
        else:
            frequency = psutil.cpu_freq()
            specs.append(
                f"CPU: {self.get_cpu_name()}; {psutil.cpu_count(logical=False)} cores, "
                f"{psutil.cpu_count(logical=True)} logical processors; "
                f"current frequency {frequency.current:.0f} MHz"
                if frequency
                else f"CPU: {self.get_cpu_name()}; {psutil.cpu_count(logical=False)} cores, "
                f"{psutil.cpu_count(logical=True)} logical processors"
            )

        memory = psutil.virtual_memory()
        specs.append(f"Installed physical memory: {format_bytes(memory.total)}")
        modules = as_items(inventory.get("MemoryModules"))
        memory_types = {24: "DDR3", 26: "DDR4", 34: "DDR5"}
        module_forms = {8: "DIMM", 12: "SO-DIMM"}
        for index, module in enumerate(modules, start=1):
            capacity = format_bytes(module.get("Capacity"))
            module_name = " ".join(
                str(module.get(key)).strip()
                for key in ("Manufacturer", "PartNumber")
                if module.get(key) and str(module.get(key)).strip()
            ) or "module details unavailable"
            speed = module.get("ConfiguredClockSpeed") or module.get("Speed")
            memory_type = memory_types.get(
                module.get("SMBIOSMemoryType") or module.get("MemoryType"),
                "type unavailable",
            )
            form_factor = module_forms.get(module.get("FormFactor"), "form factor unavailable")
            locator = module.get("DeviceLocator") or module.get("BankLabel")
            width = module.get("DataWidth")
            module_details = [
                f"Memory module {index}: {capacity}",
                memory_type,
                module_name,
                f"{speed} MHz" if speed else "speed unavailable",
                form_factor,
                f"{width}-bit data width" if width else "data width unavailable",
                f"slot {locator}" if locator else "slot unknown",
            ]
            specs.append(", ".join(module_details))
        if not modules:
            specs.append("Memory module layout/speed: unavailable from Windows hardware inventory")
        swap = psutil.swap_memory()
        specs.append(f"Page file/swap capacity: {format_bytes(swap.total)}")

        graphics = as_items(inventory.get("Graphics"))
        nvidia_memory_by_name = self._get_nvidia_gpu_memory()
        if graphics:
            for index, gpu in enumerate(graphics, start=1):
                vram = format_bytes(gpu.get("AdapterRAM"))
                gpu_name = gpu.get("Name") or "name unavailable"
                actual_nvidia_memory = next(
                    (
                        memory_mb
                        for name, memory_mb in nvidia_memory_by_name.items()
                        if name in gpu_name.lower() or gpu_name.lower() in name
                    ),
                    None,
                )
                if actual_nvidia_memory:
                    vram = f"{actual_nvidia_memory} MB dedicated VRAM (nvidia-smi)"
                elif gpu.get("AdapterRAM") == 4294967295:
                    vram = "at least 4.0 GB (Windows reporting limit; exact value unavailable)"
                specs.append(
                    f"Graphics {index}: {gpu_name}; "
                    f"reported adapter memory {vram}; driver {gpu.get('DriverVersion') or 'unknown'}; "
                    f"mode {gpu.get('VideoModeDescription') or 'unknown'}; "
                    f"refresh {gpu.get('CurrentRefreshRate') or 'unknown'} Hz"
                )
        else:
            specs.append(f"Graphics: {self.get_gpu_name()}; detailed driver/display data unavailable")

        for index, board in enumerate(as_items(inventory.get("Baseboard")), start=1):
            specs.append(
                f"Motherboard {index}: {board.get('Manufacturer') or 'unknown'} "
                f"{board.get('Product') or 'model unavailable'}; version "
                f"{board.get('Version') or 'unknown'}"
            )
        for index, bios in enumerate(as_items(inventory.get("BIOS")), start=1):
            release_date = bios.get("ReleaseDate")
            if isinstance(release_date, str) and release_date.startswith("/Date("):
                try:
                    timestamp_ms = int(release_date[6:].split(")", 1)[0])
                    release_date = datetime.fromtimestamp(
                        timestamp_ms / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                except (ValueError, OverflowError, OSError):
                    release_date = "unavailable"
            specs.append(
                f"BIOS {index}: {bios.get('Manufacturer') or 'unknown'} "
                f"{bios.get('SMBIOSBIOSVersion') or 'version unavailable'}; "
                f"release date {release_date or 'unavailable'}"
            )

        drives = as_items(inventory.get("PhysicalDrives"))
        if drives:
            for index, drive in enumerate(drives, start=1):
                specs.append(
                    f"Physical drive {index}: {drive.get('Model') or 'model unavailable'}; "
                    f"{format_bytes(drive.get('Size'))}; "
                    f"{drive.get('MediaType') or 'media type unavailable'}; "
                    f"interface {drive.get('InterfaceType') or 'unknown'}; "
                    f"firmware {drive.get('FirmwareRevision') or 'unknown'}"
                )
        else:
            specs.append("Physical drive models/types: unavailable from Windows hardware inventory")

        for index, drive in enumerate(as_items(inventory.get("PhysicalDiskHealth")), start=1):
            specs.append(
                f"Physical disk status {index}: {drive.get('FriendlyName') or 'name unavailable'}; "
                f"{drive.get('MediaType') or 'media type unavailable'}; "
                f"{drive.get('BusType') or 'bus type unavailable'}; "
                f"health {drive.get('HealthStatus') or 'unavailable'}; "
                f"status {drive.get('OperationalStatus') or 'unavailable'}"
            )

        partitions = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                partitions.append(
                    f"{partition.device or partition.mountpoint} "
                    f"({partition.fstype or 'filesystem unknown'}): "
                    f"{format_bytes(usage.total)} total"
                )
            except (OSError, PermissionError):
                continue
        specs.append(
            "Mounted storage: " + "; ".join(partitions)
            if partitions
            else "Mounted storage volumes: unavailable"
        )

        adapters = as_items(inventory.get("NetworkAdapters"))
        for index, adapter in enumerate(adapters, start=1):
            ip_addresses = adapter.get("IPAddress") or []
            gateways = adapter.get("DefaultIPGateway") or []
            dns_servers = adapter.get("DNSServerSearchOrder") or []
            if isinstance(ip_addresses, str):
                ip_addresses = [ip_addresses]
            if isinstance(gateways, str):
                gateways = [gateways]
            if isinstance(dns_servers, str):
                dns_servers = [dns_servers]
            specs.append(
                f"Network adapter {index}: {adapter.get('Description') or 'name unavailable'}; "
                f"MAC {adapter.get('MACAddress') or 'unavailable'}; "
                f"IP {', '.join(ip_addresses) or 'unavailable'}; "
                f"gateway {', '.join(gateways) or 'unavailable'}; "
                f"DNS {', '.join(dns_servers) or 'unavailable'}; "
                f"DHCP {'enabled' if adapter.get('DHCPEnabled') else 'disabled or unavailable'}"
            )

        specs.append(
            f"Logical processors: {psutil.cpu_count(logical=True)}; "
            f"physical cores: {psutil.cpu_count(logical=False)}"
        )
        specs.append(f"Python runtime architecture: {platform.architecture()[0]}")
        specs.append(f"Network hostname: {platform.node()}")
        return "Complete system specifications (values marked unavailable could not be read): " + ". ".join(specs) + "."

    # --- Specific Real-Time Stats Responses ---
    def get_cpu_stats(self) -> str:
        load = psutil.cpu_percent(interval=0.2)
        cores = psutil.cpu_count(logical=False)
        threads = psutil.cpu_count(logical=True)
        freq = psutil.cpu_freq()
        cur_freq = f" running at {round(freq.current / 1000, 2)} GHz" if freq else ""
        temp = self.get_cpu_temp()
        temp_str = f" The CPU temperature is {temp}." if temp else ""
        return f"CPU Utilization is currently {load}% across {cores} cores and {threads} threads{cur_freq}.{temp_str}"

    def get_pc_stats(self) -> str:
        """Returns only live CPU, GPU, RAM, and disk utilization/capacity."""
        cpu_load = psutil.cpu_percent(interval=0.25)
        ram = psutil.virtual_memory()
        _, gpu_load = self.get_gpu_telemetry()
        parts = [
            f"Live PC health: CPU utilization {cpu_load:.1f}%",
            (
                f"GPU utilization {gpu_load}"
                if gpu_load
                else "GPU utilization unavailable from the available telemetry interface"
            ),
            f"RAM utilization {ram.percent:.1f}% "
            f"({ram.used / (1024 ** 3):.1f} GB used of {ram.total / (1024 ** 3):.1f} GB)",
        ]
        partitions = psutil.disk_partitions(all=False)
        if not partitions:
            parts.append("Disk utilization unavailable; no mounted volumes were reported")
        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                parts.append(
                    f"Disk {partition.device or partition.mountpoint} utilization: "
                    f"{usage.percent:.1f}% full "
                    f"({usage.used / (1024 ** 3):.1f} GB used of {usage.total / (1024 ** 3):.1f} GB)"
                )
            except (OSError, PermissionError):
                parts.append(f"Disk {partition.device or partition.mountpoint}: usage unavailable")
        return ". ".join(part.rstrip(".") for part in parts) + "."

    def get_top_ram_process(self) -> str:
        processes = []
        for process in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = process.info
                memory = info.get("memory_info")
                if memory:
                    processes.append(
                        (info.get("name") or "Unknown process", info.get("pid"), memory.rss)
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        if not processes:
            return "I couldn't read process memory usage; Windows may have denied access."
        name, pid, used_bytes = max(processes, key=lambda item: item[2])
        return (
            f"The app using the most RAM is {name} (PID {pid}), "
            f"using approximately {used_bytes / (1024 ** 2):.0f} MB."
        )

    def get_ram_stats(self) -> str:
        ram = psutil.virtual_memory()
        return (
            f"RAM utilization is {ram.percent:.1f}% "
            f"({ram.used / (1024 ** 3):.1f} GB used of {ram.total / (1024 ** 3):.1f} GB)."
        )

    def get_gpu_stats(self) -> str:
        _, utilization = self.get_gpu_telemetry()
        if utilization:
            return f"GPU utilization is {utilization}."
        return "GPU utilization is unavailable from the installed telemetry interface."

    def get_disk_stats(self) -> str:
        parts = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                parts.append(
                    f"{partition.device or partition.mountpoint}: {usage.percent:.1f}% full "
                    f"({usage.used / (1024 ** 3):.1f} GB used of "
                    f"{usage.total / (1024 ** 3):.1f} GB)"
                )
            except (OSError, PermissionError):
                parts.append(f"{partition.device or partition.mountpoint}: usage unavailable")
        return "Disk usage: " + "; ".join(parts) + "." if parts else "Disk usage is unavailable."

    def get_weather(self, query: str) -> str:
        """Gets current conditions for a named place or the user's IP location."""
        if getattr(self, "is_offline", False):
            return "Offline mode is enabled, so live weather is unavailable."
        location_match = re.search(
            r"\b(?:weather|forecast)\b.*?\b(?:in|for|at|of)\s+(.+)$",
            query,
            re.IGNORECASE,
        )
        location = location_match.group(1).strip(" .,!?:;") if location_match else ""
        location = re.sub(
            r"\s+(?:for\s+)?(?:(?:this|next|coming)\s+)?(?:week|7\s*days?)$",
            "",
            location,
            flags=re.IGNORECASE,
        ).strip()
        favorites = getattr(self, "weather_favorites", {})
        if location.lower() in favorites:
            location = favorites[location.lower()]
        weekly_forecast = bool(re.search(r"\b(?:week|weekly|7\s*day)\b", query, re.IGNORECASE))

        try:
            if location:
                geo_response = requests.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 1, "language": "en", "format": "json"},
                    timeout=10,
                )
                geo_response.raise_for_status()
                places = geo_response.json().get("results") or []
                if not places:
                    return f"I couldn't find a location named {location}."
                place = places[0]
            else:
                location_error = None
                place = None
                for endpoint in ("https://ipapi.co/json/", "https://ipwho.is/"):
                    try:
                        geo_response = requests.get(endpoint, timeout=5)
                        geo_response.raise_for_status()
                        place_data = geo_response.json()
                        if place_data.get("success") is False:
                            raise ValueError("Location provider could not locate this network.")
                        latitude = place_data.get("latitude")
                        longitude = place_data.get("longitude")
                        if latitude is None or longitude is None:
                            raise ValueError("Location provider returned no coordinates.")
                        place = {
                            "name": place_data.get("city") or place_data.get("region") or "Your area",
                            "admin1": place_data.get("region"),
                            "country": place_data.get("country_name") or place_data.get("country"),
                            "latitude": latitude,
                            "longitude": longitude,
                        }
                        break
                    except (requests.RequestException, KeyError, TypeError, ValueError) as error:
                        location_error = error
                if place is None:
                    raise requests.RequestException(
                        f"Automatic location lookup failed: {location_error}"
                    )

            weather_response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": (
                        "temperature_2m,apparent_temperature,relative_humidity_2m,"
                        "precipitation,weather_code,wind_speed_10m"
                    ),
                    "daily": (
                        "temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max"
                    ),
                    "forecast_days": 7 if weekly_forecast else 1,
                    "timezone": "auto",
                },
                timeout=10,
            )
            weather_response.raise_for_status()
            weather = weather_response.json()
            current = weather["current"]
            daily = weather.get("daily", {})

            weather_codes = {
                0: "clear",
                1: "mostly clear",
                2: "partly cloudy",
                3: "overcast",
                45: "foggy",
                48: "foggy",
                51: "light drizzle",
                53: "drizzle",
                55: "heavy drizzle",
                61: "light rain",
                63: "rain",
                65: "heavy rain",
                71: "light snow",
                73: "snow",
                75: "heavy snow",
                80: "rain showers",
                81: "rain showers",
                82: "heavy rain showers",
                95: "thunderstorms",
                96: "thunderstorms with hail",
                99: "thunderstorms with hail",
            }
            place_parts = []
            for part in (place.get("name"), place.get("admin1"), place.get("country")):
                if part and part not in place_parts:
                    place_parts.append(part)
            place_name = ", ".join(place_parts) or "Your area"
            unit = current.get("temperature_2m")
            temperature = f"{unit}°C" if unit is not None else "unavailable"
            feels_like_value = current.get("apparent_temperature")
            feels_like = f"{feels_like_value}°C" if feels_like_value is not None else "unavailable"
            code = current.get("weather_code")
            condition = weather_codes.get(code, "current conditions")
            summary = (
                f"Current weather in {place_name}: {condition}, {temperature}, "
                f"feels like {feels_like}, humidity {current.get('relative_humidity_2m', 'unavailable')}%, "
                f"precipitation {current.get('precipitation', 'unavailable')} mm, "
                f"wind {current.get('wind_speed_10m', 'unavailable')} kilometers per hour."
            )
            highs = daily.get("temperature_2m_max", [])
            lows = daily.get("temperature_2m_min", [])
            rain = daily.get("precipitation_probability_max", [])
            if highs and lows:
                summary += f" Today: high {highs[0]}°C and low {lows[0]}°C."
            if rain:
                summary += f" Chance of precipitation: {rain[0]}%."
            if weekly_forecast:
                dates = daily.get("time", [])
                for index in range(min(7, len(dates), len(highs), len(lows))):
                    rain_chance = rain[index] if index < len(rain) else "unavailable"
                    summary += (
                        f" {dates[index]}: high {highs[index]}°C, low {lows[index]}°C, "
                        f"precipitation chance {rain_chance}%."
                    )
            return summary
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            print(f"[Weather Error]: {e}")
            return "I couldn't retrieve the live weather right now. Please check your internet connection and try again."

    # --- Local App Launcher ---
    def launch_local_target(self, target_name: str) -> tuple[bool, str]:
        clean_target = target_name.lower().strip()
        if clean_target.startswith(("http://", "https://", "www.")):
            if getattr(self, "is_offline", False):
                return False, "Offline mode is enabled, so websites cannot be opened."
            url = clean_target if "://" in clean_target else f"https://{clean_target}"
            webbrowser.open(url)
            return True, f"Opening {url}."

        if platform.system() == "Windows":
            app_map = {
                "downloads": [os.path.join(str(Path.home()), "Downloads")],
                "my downloads": [os.path.join(str(Path.home()), "Downloads")],
                "calculator": ["calc.exe"], "notepad": ["notepad.exe"],
                "cmd": ["cmd.exe"], "terminal": ["wt.exe"],
                "powershell": ["powershell.exe"], "task manager": ["taskmgr.exe"],
                "explorer": ["explorer.exe"], "file explorer": ["explorer.exe"],
                "settings": ["ms-settings:"], "chrome": ["chrome.exe"],
                "edge": ["msedge.exe"], "steam": ["steam://open/main"],
                "discord": ["discord:"], "spotify": ["Spotify.exe"],
                "vs code": ["code"], "vscode": ["code"],
            }
        elif platform.system() == "Darwin":
            app_map = {
                "calculator": ["open", "-a", "Calculator"],
                "notepad": ["open", "-a", "TextEdit"],
                "terminal": ["open", "-a", "Terminal"],
                "explorer": ["open", str(Path.home())],
                "file explorer": ["open", str(Path.home())],
                "spotify": ["open", "-a", "Spotify"],
                "vs code": ["code"], "vscode": ["code"],
            }
        else:
            app_map = {
                "calculator": ["gnome-calculator"],
                "notepad": ["gedit"],
                "terminal": ["x-terminal-emulator"],
                "explorer": ["xdg-open", str(Path.home())],
                "file explorer": ["xdg-open", str(Path.home())],
                "spotify": ["spotify"],
                "vs code": ["code"], "vscode": ["code"],
            }

        for app_key, launch_cmd in app_map.items():
            if app_key in clean_target:
                try:
                    if app_key in {"downloads", "my downloads"}:
                        if not os.path.isdir(launch_cmd[0]):
                            return False, f"The Downloads folder was not found: {launch_cmd[0]}"
                        if platform.system() == "Windows":
                            os.startfile(launch_cmd[0])
                        elif platform.system() == "Darwin":
                            subprocess.Popen(["open", launch_cmd[0]], shell=False)
                        else:
                            subprocess.Popen(["xdg-open", launch_cmd[0]], shell=False)
                        return True, "Opening Downloads."
                    if len(launch_cmd) == 1 and launch_cmd[0].endswith(":"):
                        webbrowser.open(launch_cmd[0])
                    elif len(launch_cmd) == 1 and launch_cmd[0].startswith("steam:"):
                        webbrowser.open(launch_cmd[0])
                    else:
                        executable = launch_cmd[0]
                        if platform.system() != "Darwin" and not shutil.which(executable):
                            if app_key == "spotify" and platform.system() == "Windows":
                                continue
                            raise FileNotFoundError(f"{executable} is not installed or not on PATH.")
                        subprocess.Popen(launch_cmd, shell=False)
                    return True, f"Launching {app_key.title()}."
                except Exception as e:
                    return False, f"Failed to launch {app_key}: {e}"

        if not re.fullmatch(r"[\w .()+-]{1,100}", target_name.strip()):
            return False, "That application name contains unsupported characters."

        if shutil.which(target_name.strip()):
            try:
                subprocess.Popen([target_name.strip()], shell=False)
                return True, f"Launching {target_name.strip()}."
            except OSError as e:
                return False, f"Failed to launch {target_name}: {e}"

        if platform.system() != "Windows":
            return False, f"Unable to find {target_name} on this system."

        search_dirs = [
            os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            r"C:\Program Files", r"C:\Program Files (x86)", r"D:\Games", r"D:\Apps"
        ]

        for s_dir in search_dirs:
            if not os.path.exists(s_dir):
                continue
            for root, _, files in os.walk(s_dir):
                for f in files:
                    base_name = os.path.splitext(f)[0].lower()
                    if clean_target in base_name and f.lower().endswith((".lnk", ".exe", ".url")):
                        full_path = os.path.join(root, f)
                        try:
                            os.startfile(full_path)
                            return True, f"Launching {clean_target.title()}."
                        except Exception:
                            continue

        return False, f"Unable to find {target_name} on this system."

    # --- System Controls Router ---
    def system_controls(self, query: str) -> tuple[bool, str]:
        timer_intent = re.search(
            r"\b(?:timers?|reminders?|remind\s+me)\b|\bset\s+(?:a\s+)?time\b",
            query,
            re.IGNORECASE,
        )
        if timer_intent:
            raw_query = query.strip()
            if re.search(
                r"\b(?:list|show|what are)\s+(?:(?:my|the)\s+)?(?:timers?|reminders?)\b",
                raw_query,
                re.IGNORECASE,
            ):
                reminders = self.reminders.list_reminders()
                if not reminders:
                    return True, "You have no active timers or reminders."
                return True, "Active reminders: " + "; ".join(
                    f"{item['message']} (ID {item['id']})" for item in reminders
                )
            if re.search(
                r"\b(?:cancel|delete|clear)\s+(?:(?:all|the|my)\s+)?(?:timers?|reminders?)\b",
                raw_query,
                re.IGNORECASE,
            ):
                id_match = re.search(r"\b(?:id\s*)?([a-f0-9]{8})\b", raw_query, re.IGNORECASE)
                reminder_id = id_match.group(1) if id_match else None
                if reminder_id is None and not re.search(r"\ball\b", raw_query, re.IGNORECASE):
                    active_reminders = self.reminders.list_reminders()
                    if len(active_reminders) > 1:
                        return True, (
                            "More than one reminder is active. Specify a reminder ID "
                            "or say 'cancel all reminders'."
                        )
                    if active_reminders:
                        reminder_id = active_reminders[0]["id"]
                removed = self.reminders.cancel(reminder_id)
                if removed < 0:
                    return True, "I couldn't save the reminder cancellation. Check local storage permissions and try again."
                if not removed:
                    return True, "No matching active timer or reminder was found."
                return True, f"Cancelled {removed} reminder{'s' if removed != 1 else ''}."
            parsed = parse_reminder_command(raw_query)
            if parsed:
                kind = (
                    "reminder"
                    if re.search(r"\b(?:reminder|remind\s+me)\b", raw_query, re.IGNORECASE)
                    else "timer"
                )
                return True, self.reminders.schedule(*parsed, kind=kind)
            return True, (
                "I couldn't understand that timer duration. Try 'set a timer for "
                "5 minutes' or 'remind me in 30 seconds to stretch'."
            )

        query = _correct_command_typos(query)
        q = query.replace(",", "").replace(".", "").replace("-", " ").strip().lower()

        youtube_search = re.search(
            r"\b(?:open|launch|go to)\s+youtube\b.*?\bsearch(?:\s+for)?\s+(.+)$"
            r"|\bsearch\s+(?:on\s+)?youtube\s+(?:for\s+)?(.+)$"
            r"|\byoutube\s+(?:search|for)\s+(.+)$",
            query,
            re.IGNORECASE,
        )
        if youtube_search:
            search_term = next(
                (group.strip(" .,!?:;") for group in youtube_search.groups() if group),
                "",
            )
            if not search_term:
                return True, "What would you like to search for on YouTube?"
            if getattr(self, "is_offline", False):
                return True, "Offline mode is enabled, so YouTube cannot be opened."
            url = (
                "https://www.youtube.com/results?search_query="
                + urllib.parse.quote_plus(search_term)
            )
            if not webbrowser.open(url):
                return True, "I couldn't open YouTube. Check your internet connection and try again."
            return True, f"Opening YouTube search results for {search_term}."

        favorite_list_request = bool(
            re.search(r"\b(?:list|show|what are)\s+(?:my\s+)?weather favorites\b", q)
        )
        if favorite_list_request:
            return True, self._weather_favorites_reply()

        favorite_match = re.search(
            r"\b(?:save|add|remember)\s+(.+?)\s+as\s+(?:a\s+)?weather favorite\s+([a-z0-9 _-]+)$",
            query,
            re.IGNORECASE,
        )
        if favorite_match:
            return True, self.add_weather_favorite(
                favorite_match.group(2), favorite_match.group(1)
            )

        if re.search(r"\b(weather|forecast)\b", q):
            return True, self.get_weather(query)

        player_volume_request = bool(
            re.search(
                r"\b(?:player|music|song|track)(?:'s)?\s+volume\b"
                r"|\bvolume\s+(?:of|for|on)\s+(?:the\s+)?(?:player|music|song|track)\b",
                q,
            )
        )
        if player_volume_request:
            direction_match = re.search(
                r"\b(increase|raise|up|louder|decrease|lower|down|quieter|turn up|turn down)\b",
                q,
            )
            amount_match = re.search(r"\bby\s+(\d{1,3})\b", q)
            if direction_match and amount_match:
                amount = int(amount_match.group(1))
                delta = amount if direction_match.group(1) in {
                    "increase", "raise", "up", "louder", "turn up"
                } else -amount
                return True, self.player.adjust_volume(delta)
            level = self._parse_volume_level(q)
            if level is not None:
                return True, self.player.set_volume(level)
            if re.search(r"\b(up|increase|raise|louder|turn up)\b", q):
                return True, self.player.adjust_volume(5)
            if re.search(r"\b(down|decrease|lower|quieter|turn down)\b", q):
                return True, self.player.adjust_volume(-5)
            return True, "Tell me a player volume level, or say increase or decrease player volume."

        ram_process_question = (
            re.search(
                r"\b(which|what)\s+(app|application|process)\b.*"
                r"\b(using|uses|use|consuming|consumes|consume|taking|takes)\b.*"
                r"\b(most|highest|maximum)\b.*\b(ram|memory)\b",
                q,
            )
            or any(
                trigger in q
                for trigger in (
                    "what is using my ram",
                    "which app is using my ram",
                    "highest ram using",
                    "most ram consuming",
                    "most memory using",
                )
            )
        )
        if ram_process_question:
            return True, self.get_top_ram_process()

        spec_request = (
            re.search(r"\b(specs?|specifications?|hardware)\b", q)
            or "system information" in q
        )
        cpu_requested = bool(re.search(r"\b(cpu|processor)\b", q))
        gpu_requested = bool(re.search(r"\b(gpu|graphics card|graphics|video card)\b", q))
        ram_requested = bool(re.search(r"\b(ram|memory)\b", q))

        if spec_request:
            if cpu_requested:
                return True, self.get_cpu_spec()
            if gpu_requested:
                return True, self.get_gpu_spec()
            if ram_requested:
                return True, self.get_ram_spec()
            return True, self.get_full_specs()

        if re.search(r"\b(what is|tell me about|describe)\s+(my\s+)?(cpu|processor)\b", q):
            return True, self.get_cpu_spec()
        if re.search(r"\b(what is|tell me about|describe)\s+(my\s+)?(gpu|graphics card)\b", q):
            return True, self.get_gpu_spec()
        if re.search(r"\b(how much|tell me about|describe)\s+(installed\s+)?(ram|memory)\b", q):
            return True, self.get_ram_spec()

        if cpu_requested and re.search(r"\b(usage|utilization|load|temperature|temp|stats?|health|status)\b", q):
            return True, self.get_cpu_stats()
        if gpu_requested and re.search(r"\b(usage|utilization|load|temperature|temp|stats?|health|status)\b", q):
            return True, self.get_gpu_stats()
        if ram_requested and re.search(r"\b(usage|utilization|health|status)\b", q):
            return True, self.get_ram_stats()
        if re.search(r"\b(disk|storage)\b", q) and re.search(
            r"\b(usage|utilization|space|health|status|full)\b", q
        ):
            return True, self.get_disk_stats()

        health_triggers = (
            "system report", "system health", "system update", "pc report",
            "pc health", "pc update", "computer report", "computer health",
            "system usage", "pc usage", "live report", "live system",
            "system stats", "system status", "pc stats", "pc status",
            "computer stats", "diagnostics", "diagnostic",
        )
        if any(trigger in q for trigger in health_triggers):
            return True, self.get_pc_stats()

        # --- Web Search Intercept ---
        search_triggers = ["search for", "search web for", "google ", "look up ", "search "]
        live_search_triggers = (
            "current events", "latest news", "breaking news", "current news",
            "live news", "news today", "today's news", "todays news",
            "today's headlines", "todays headlines", "latest headlines",
            "latest updates",
            "what happened today", "what is happening now", "what's happening now",
            "what is happening in the world", "what's happening in the world",
            "what is going on in the world", "what's going on in the world",
            "live score", "current price of", "latest price of",
        )
        recent_context = any(
            marker in q
            for marker in ("latest", "current", "live", "today", "now", "breaking")
        ) and any(
            subject in q
            for subject in (
                "news", "event", "score", "price", "headline", "update",
                "happening", "result", "election", "politic", "world",
                "market", "stock", "sport", "technology", "release",
            )
        )
        if (
            any(st in q for st in search_triggers)
            or any(trigger in q for trigger in live_search_triggers)
            or recent_context
        ) and not any(app in q for app in ["open google", "launch google", "chrome"]):
            return True, self.search_web(query)

        # 1. PC shutdown is confirmed separately from CYRUS exit.
        if re.search(
            r"\b(?:shut\s*down|turn\s+off)\s+(?:my\s+)?(?:pc|computer)\b",
            q,
        ):
            return True, "CONFIRM_ACTION:shutdown_pc"

        # 2. Shutdown CYRUS
        shutdown_triggers = [
            "shutdown cyrus", "shut down", "shutdown", "shut down cyrus", "close cyrus", "exit cyrus",
            "terminate cyrus", "kill cyrus", "turn off cyrus", "shutdown yourself"
        ]
        if any(w in q for w in shutdown_triggers):
            return True, "CONFIRM_ACTION:shutdown_cyrus"

        # 3. Dedicated Hardware Stats Routing
        if any(w in q for w in ["cpu stat", "cpu stats", "cpu temperature", "cpu temp", "processor stat", "processor stats", "processor temperature"]):
            return True, self.get_cpu_stats()

        if any(w in q for w in ["pc stat", "pc stats", "computer stat", "computer stats", "system stat", "system stats", "pc status", "system status", "diagnostics", "diagnostic"]):
            return True, self.get_pc_stats()

        # 4. Dedicated Hardware Specs Routing
        if any(w in q for w in ["cpu spec", "cpu specs", "what is my cpu", "processor spec", "processor specs"]):
            return True, self.get_cpu_spec()

        if any(w in q for w in ["gpu spec", "gpu specs", "graphics card spec", "graphics spec", "what is my gpu"]):
            return True, self.get_gpu_spec()

        if any(w in q for w in ["what is my spec", "what are my specs", "my specs", "pc specs", "full specs", "hardware specs", "system specs"]):
            return True, self.get_full_specs()

        # 5. Native Audio Controls
        if any(w in q for w in ["next song", "next track", "skip song", "skip track", "next music"]):
            return True, self.player.next_track()

        if any(w in q for w in ["previous song", "previous track", "last song", "previous music"]):
            return True, self.player.previous_track()

        if any(w in q for w in ["pause song", "pause music", "pause playback", "pause"]):
            return True, self.player.pause()

        if any(w in q for w in ["resume song", "resume music", "resume playback", "resume"]):
            return True, self.player.resume()

        if any(w in q for w in ["stop song", "stop music", "stop playback"]):
            return True, self.player.stop()

        # 6. Global Mute / Unmute
        if "mute" in q and "unmute" not in q:
            pyautogui.press("volumemute")
            return True, "System audio muted."
        elif "unmute" in q:
            pyautogui.press("volumemute")
            return True, "System audio unmuted."

        # 7. Volume Percentage
        if "volume" in q or "sound" in q:
            level = self._parse_volume_level(q)

            if level is not None:
                return True, self.set_system_master_volume(level)

            if "up" in q or "increase" in q:
                for _ in range(5): pyautogui.press("volumeup")
                return True, "Volume increased."
            if "down" in q or "decrease" in q:
                for _ in range(5): pyautogui.press("volumedown")
                return True, "Volume decreased."

        # 8. Battery
        if "battery" in q:
            b = psutil.sensors_battery()
            if b:
                plugged = "plugged in" if b.power_plugged else "on battery"
                return True, f"Battery is at {b.percent}%, currently {plugged}."
            return True, "Battery telemetry unavailable."

        # 9. Screenshot
        if "screenshot" in q:
            p_dir = os.path.join(os.environ.get("USERPROFILE", ""), "Pictures")
            save_file = os.path.join(p_dir, "cyrus_screenshot.png")
            pyautogui.screenshot().save(save_file)
            return True, "Screenshot captured and saved to Pictures."

        # 10. Lock Screen
        if re.search(r"\block(?:\s+my)?\s+(?:pc|computer|screen)\b", q):
            return True, "CONFIRM_ACTION:lock_pc"

        return False, ""

    @staticmethod
    def _parse_volume_level(query: str) -> int | None:
        number_match = re.search(r"\b(\d{1,3})\b", query)
        if number_match:
            return min(100, int(number_match.group(1)))
        if re.search(r"\b(hundred|max|maximum)\b", query):
            return 100
        if re.search(r"\b(half|midpoint)\b", query):
            return 50
        if re.search(r"\b(zero|min|minimum|mute)\b", query):
            return 0
        return None

    # --- Master Router ---
    def execute_command(self, text: str) -> tuple[bool, str | None]:
        corrected_text = _correct_command_typos(text)
        clean_text = corrected_text.lower().replace("?", "").replace(".", "").replace("!", "").replace(",", "").strip()
        offline = getattr(self, "is_offline", False)

        direct_url = re.match(
            r"^\s*(?:please\s+)?(?:open|launch)\s+(https?://\S+|www\.\S+)\s*$",
            corrected_text,
            re.IGNORECASE,
        )
        if direct_url:
            if offline:
                return True, "Offline mode is enabled, so websites cannot be opened."
            url = direct_url.group(1)
            if url.lower().startswith("www."):
                url = f"https://{url}"
            webbrowser.open(url)
            return True, f"Opening {url}."

        play_next_match = re.search(r"\bplay\s+(.+?)\s+next\b", corrected_text, re.IGNORECASE)
        if play_next_match:
            if offline:
                return True, "Offline mode is enabled, so YouTube music playback is unavailable."
            song = play_next_match.group(1).strip()
            if song.lower() in {"this song", "this", "it", "the current song"}:
                return True, self.player.add_current_to_queue(play_next=True)
            return True, self.player.add_to_queue(song, play_next=True)

        add_to_queue_match = re.search(
            r"\b(?:add|put)\s+(.+?)\s+(?:to|in|into)\s+(?:the\s+)?queue\b",
            corrected_text,
            re.IGNORECASE,
        )
        if add_to_queue_match:
            if offline:
                return True, "Offline mode is enabled, so YouTube music playback is unavailable."
            song = add_to_queue_match.group(1).strip()
            if song.lower() in {"this song", "this", "it", "the current song"}:
                return True, self.player.add_current_to_queue()
            return True, self.player.add_to_queue(song)

        handled_sys, sys_msg = self.system_controls(text)
        if handled_sys:
            return True, sys_msg

        if clean_text.startswith("play ") or "play song " in clean_text or "play track " in clean_text:
            if offline:
                return True, "Offline mode is enabled, so YouTube music playback is unavailable."
            song_name = clean_text.replace("play song", "").replace("play track", "").replace("play", "").strip()
            if song_name:
                return True, self.player.play_song(song_name)

        open_match = re.search(r"\b(?:open|launch)\s+(.+)$", corrected_text, re.IGNORECASE)
        if open_match:
            target = open_match.group(1).strip()
            is_bare_domain = bool(
                re.fullmatch(r"[\w-]+(?:\.[\w-]+)+(?:/[^\s]*)?", target)
            )
            if target.startswith(("http://", "https://", "www.")) or is_bare_domain:
                if offline:
                    return True, "Offline mode is enabled, so websites cannot be opened."
                url = target if "://" in target else f"https://{target}"
                webbrowser.open(url)
                return True, f"Opening {url}."
            web_aliases = {
                "youtube": "https://www.youtube.com", "google": "https://www.google.com",
                "github": "https://www.github.com", "reddit": "https://www.reddit.com",
                "chatgpt": "https://www.chatgpt.com", "gmail": "https://mail.google.com",
                "youtube music": "https://music.youtube.com",
            }
            for site, url in web_aliases.items():
                if site in target.lower():
                    if offline:
                        return True, "Offline mode is enabled, so websites cannot be opened."
                    webbrowser.open(url)
                    return True, f"Opening {site.title()}."

            handled_app, app_msg = self.launch_local_target(target)
            if not handled_app and target.lower() == "spotify" and not offline:
                webbrowser.open("https://open.spotify.com")
                return True, "Spotify is not installed; opening Spotify Web Player."
            return True, app_msg
        return False, ""

        return False, ""

    def confirm_action(self, action: str) -> str:
        actions = {
            "shutdown_pc": {
                "windows": ["shutdown.exe", "/s", "/t", "5"],
                "darwin": ["shutdown", "-h", "+1"],
                "linux": ["shutdown", "-h", "+1"],
            },
            "lock_pc": {
                "windows": ["rundll32.exe", "user32.dll,LockWorkStation"],
            },
        }
        if action == "shutdown_cyrus":
            return "CONFIRMED_SHUTDOWN_CYRUS"
        platform_actions = actions.get(action)
        if not platform_actions:
            return f"Unsupported confirmed action: {action}."
        command = platform_actions.get(platform.system().lower())
        if not command:
            return f"{action.replace('_', ' ').title()} is unavailable on this platform."
        try:
            subprocess.Popen(command, shell=False)
        except OSError as error:
            return f"Could not perform {action.replace('_', ' ')}: {error}"
        return f"Confirmed: {action.replace('_', ' ')} requested."
