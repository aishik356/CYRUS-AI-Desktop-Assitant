import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from config.settings import get_user_data_dir


HISTORY_FILE = get_user_data_dir() / "telemetry_history.json"
MAX_SAMPLES = 240
MIN_SAMPLE_INTERVAL_SECONDS = 5


class TelemetryHistory:
    def __init__(self, history_file: Path | None = None):
        self.history_file = Path(history_file or HISTORY_FILE)
        self.samples = self._load()

    def _load(self) -> list[dict]:
        if not self.history_file.exists():
            return []
        try:
            with self.history_file.open("r", encoding="utf-8") as history_file:
                samples = json.load(history_file)
            if not isinstance(samples, list):
                raise ValueError(f"{self.history_file} must contain a JSON list.")
            valid_samples = []
            for sample in samples:
                if not (
                    isinstance(sample, dict)
                    and isinstance(sample.get("timestamp"), str)
                    and all(
                        isinstance(sample.get(key), (int, float))
                        for key in ("cpu", "ram", "disk")
                    )
                ):
                    continue
                try:
                    datetime.fromisoformat(sample["timestamp"])
                except ValueError:
                    print("[Telemetry History Warning]: Ignoring sample with an invalid timestamp.")
                    continue
                valid_samples.append(sample)
            return valid_samples[-MAX_SAMPLES:]
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"[Telemetry History Error]: Could not load history: {error}")
            return []

    def record(self, cpu: float, ram: float, disk: float, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.samples:
            previous = datetime.fromisoformat(self.samples[-1]["timestamp"])
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            elapsed = (now - previous).total_seconds()
            if 0 <= elapsed < MIN_SAMPLE_INTERVAL_SECONDS:
                return False
        self.samples.append(
            {
                "timestamp": now.isoformat(),
                "cpu": max(0.0, min(100.0, float(cpu))),
                "ram": max(0.0, min(100.0, float(ram))),
                "disk": max(0.0, min(100.0, float(disk))),
            }
        )
        self.samples = self.samples[-MAX_SAMPLES:]
        self._save()
        return True

    def _save(self):
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.history_file.parent,
                delete=False,
                suffix=".tmp",
            ) as history_file:
                json.dump(self.samples, history_file, indent=2)
                temporary_path = Path(history_file.name)
            os.replace(temporary_path, self.history_file)
        except OSError as error:
            if temporary_path and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError as cleanup_error:
                    print(f"[Telemetry History Error]: Could not clean temporary file: {cleanup_error}")
            print(f"[Telemetry History Error]: Could not save history: {error}")

    def values(self, metric: str, limit: int = 60) -> list[float]:
        if metric not in {"cpu", "ram", "disk"}:
            raise ValueError(f"Unsupported telemetry metric: {metric}")
        return [float(sample[metric]) for sample in self.samples[-limit:]]
