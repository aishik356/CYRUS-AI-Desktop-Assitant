import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from config.settings import get_user_data_dir


REMINDER_FILE = get_user_data_dir() / "reminders.json"
_DURATION_RE = re.compile(
    r"\b(?:(?:in|after|for)\s+)?"
    r"(?P<amount>\d+|(?:a|an|zero|one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"thousand)(?:[\s-]+(?:one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"thousand))*)\s*"
    r"(?P<unit>seconds?|secs?|mins?|minutes?|hrs?|hours?)\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "a": 1, "an": 1, "zero": 0, "one": 1, "two": 2, "three": 3,
    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_ABSOLUTE_DATE_RE = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?[A-Za-z]+\s+\d{4}\b"
    r"|\b[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4}\b",
    re.IGNORECASE,
)
_REMINDER_TIME_RE = re.compile(
    r"\b(?:at\s+)?(?P<time>\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)?"
    r"|\d{1,2}\s*(?:a\.?m\.?|p\.?m\.?))\b",
    re.IGNORECASE,
)


def _parse_duration_amount(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    total = current = 0
    for word in re.split(r"[\s-]+", value.lower()):
        if word in {"a", "an"}:
            current += 1
        elif word in _NUMBER_WORDS:
            current += _NUMBER_WORDS[word]
        elif word == "hundred":
            current = max(1, current) * 100
        elif word == "thousand":
            total += max(1, current) * 1000
            current = 0
        else:
            return None
    return total + current


def parse_reminder_command(query: str) -> tuple[int, str] | None:
    match = _DURATION_RE.search(query)
    if not match:
        return None
    amount = _parse_duration_amount(match.group("amount"))
    if amount is None:
        return None
    unit = match.group("unit").lower()
    multiplier = 1 if unit.startswith(("s", "sec")) else 60 if unit.startswith(("m", "min")) else 3600
    delay_seconds = amount * multiplier
    if delay_seconds < 1 or delay_seconds > 365 * 24 * 3600:
        return None
    named_title = re.search(
        r"\b(?:named|called)\s+(.+)$", query, flags=re.IGNORECASE
    )
    if named_title:
        title = named_title.group(1).strip(" .,!?:;-")
    else:
        title = re.sub(
            r"\b(?:(?:please\s+)?(?:set|create|start|make)\s+)?"
            r"(?:a\s+)?(?:timer|reminder)\b",
            "",
            query,
            flags=re.IGNORECASE,
        )
        title = _DURATION_RE.sub("", title)
        title = re.sub(
            r"^\s*(?:please\s+)?(?:remind\s+me)\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"^\s*(?:please\s+)?(?:set|create|start|make)\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(r"^\s*(?:to|that|for|named|called)\s+", "", title, flags=re.IGNORECASE)
        title = title.strip(" .,!?:;-")
    if not title:
        title = "Reminder" if re.search(
            r"\b(?:reminder|remind\s+me)\b", query, re.IGNORECASE
        ) else "Timer"
    return delay_seconds, title


def parse_absolute_reminder_command(
    query: str,
    now: datetime | None = None,
) -> tuple[datetime, str] | None:
    date_match = _ABSOLUTE_DATE_RE.search(query)
    time_match = _REMINDER_TIME_RE.search(query)
    if not date_match and not time_match:
        return None

    parsed_date = None
    if date_match:
        date_text = re.sub(
            r"(?<=\d)(?:st|nd|rd|th)\b", "", date_match.group(), flags=re.IGNORECASE
        )
        date_text = re.sub(r"\bof\b", "", date_text, flags=re.IGNORECASE)
        date_text = re.sub(r"\s+", " ", date_text).strip(" ,")
        date_text = date_text.replace(",", "")
        for date_format in (
            "%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
        ):
            try:
                parsed_date = datetime.strptime(date_text, date_format).date()
                break
            except ValueError:
                continue
        if parsed_date is None:
            raise ValueError(
                f"I couldn't understand the reminder date '{date_match.group()}'."
            )

    reminder_time = None
    if time_match:
        time_text = re.sub(r"\s+", " ", time_match.group("time").replace(".", "").upper()).strip()
        time_text = re.sub(r"(?<=\d)(AM|PM)$", r" \1", time_text)
        formats = ("%I:%M %p", "%I %p", "%H:%M")
        for time_format in formats:
            try:
                reminder_time = datetime.strptime(time_text, time_format).time()
                break
            except ValueError:
                continue
        if reminder_time is None:
            raise ValueError(f"I couldn't understand the reminder time '{time_match.group('time')}'.")
    else:
        reminder_time = datetime.strptime("09:00", "%H:%M").time()

    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    parsed_date = parsed_date or current.date()
    due_at = datetime.combine(parsed_date, reminder_time, tzinfo=current.tzinfo)
    if not date_match and due_at <= current:
        due_at += timedelta(days=1)
    elif date_match and due_at <= current:
        raise ValueError("That reminder date and time has already passed.")

    title = query
    spans = []
    if date_match:
        spans.append((date_match.start(), date_match.end()))
    if time_match:
        spans.append((time_match.start(), time_match.end()))
    for start, end in sorted(spans, reverse=True):
        title = title[:start] + " " + title[end:]
    title = re.sub(
        r"^\s*(?:please\s+)?(?:set|create|make)\s+(?:a\s+)?reminder\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        r"^\s*(?:please\s+)?(?:set|create|make)\s+(?:a\s+)?(?:timer|reminder)\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"^\s*(?:for|at|on|to|that)\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\s*(?:please\s+)?remind\s+me\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\s*(?:on|for|to|that)\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\s*(?:named|called)\s+", "", title, flags=re.IGNORECASE)
    title = title.strip(" .,!?:;-")
    title = re.sub(r"^(?:to|that|for)\s+", "", title, flags=re.IGNORECASE)
    if not title:
        title = "Reminder"
    return due_at, title


class ReminderService:
    def __init__(self, on_due=None, reminder_file: Path | None = None, start=True):
        self.reminder_file = Path(reminder_file or REMINDER_FILE)
        self.on_due = on_due
        self.on_change = None
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stopping = False
        self._reminders = self._load()
        self._thread = None
        if start:
            self.start()

    def start(self):
        with self._lock:
            if self._stopping:
                raise RuntimeError("A stopped reminder service cannot be restarted.")
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run,
                name="CyrusReminders",
                daemon=True,
            )
            self._thread.start()
        self._wake.set()

    def _load(self) -> list[dict]:
        if not self.reminder_file.exists():
            return []
        try:
            with self.reminder_file.open("r", encoding="utf-8") as reminder_file:
                data = json.load(reminder_file)
            if not isinstance(data, list):
                raise ValueError(f"{self.reminder_file} must contain a JSON list.")
            valid_reminders = []
            for item in data:
                if not (
                    isinstance(item, dict)
                    and isinstance(item.get("id"), str)
                    and isinstance(item.get("due_at"), str)
                    and isinstance(item.get("message"), str)
                ):
                    continue
                try:
                    datetime.fromisoformat(item["due_at"])
                except ValueError:
                    print(f"[Reminder Warning]: Ignoring malformed reminder {item['id']}.")
                    continue
                valid_reminders.append(item)
            return valid_reminders
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"[Reminder Error]: Could not load reminders: {error}")
            return []

    def _save(self):
        self.reminder_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.reminder_file.parent,
                delete=False,
                suffix=".tmp",
            ) as reminder_file:
                json.dump(self._reminders, reminder_file, indent=2)
                temporary_path = Path(reminder_file.name)
            os.replace(temporary_path, self.reminder_file)
            return True
        except OSError as error:
            if temporary_path and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError as cleanup_error:
                    print(f"[Reminder Error]: Could not clean temporary file: {cleanup_error}")
            print(f"[Reminder Error]: Could not save reminders: {error}")
            return False

    def schedule(
        self,
        delay_seconds: int,
        message: str = "Timer",
        kind: str = "timer",
    ) -> str:
        if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, int):
            raise TypeError("delay_seconds must be an integer.")
        if delay_seconds < 1 or delay_seconds > 365 * 24 * 3600:
            raise ValueError("Reminder duration must be from 1 second to 365 days.")
        if kind not in {"timer", "reminder"}:
            raise ValueError("kind must be 'timer' or 'reminder'.")
        reminder = {
            "id": uuid.uuid4().hex[:8],
            "due_at": (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(),
            "message": message.strip() or ("Reminder" if kind == "reminder" else "Timer"),
            "kind": kind,
        }
        with self._lock:
            self._reminders.append(reminder)
            if not self._save():
                self._reminders.pop()
                return "I couldn't save that reminder. Check local storage permissions and try again."
        self._wake.set()
        if self.on_change:
            try:
                self.on_change(self.list_reminders())
            except Exception as error:
                print(f"[Reminder Error]: Could not update countdown display: {error}")
        label = "Reminder" if kind == "reminder" else "Timer"
        return f"{label} set for {delay_seconds} seconds from now: {reminder['message']} (ID {reminder['id']})."

    def schedule_at(
        self,
        due_at: datetime,
        message: str = "Reminder",
        kind: str = "reminder",
    ) -> str:
        if not isinstance(due_at, datetime):
            raise TypeError("due_at must be a datetime.")
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=datetime.now().astimezone().tzinfo)
        if due_at <= datetime.now(due_at.tzinfo):
            raise ValueError("Reminder date and time must be in the future.")
        if kind not in {"timer", "reminder"}:
            raise ValueError("kind must be 'timer' or 'reminder'.")
        reminder = {
            "id": uuid.uuid4().hex[:8],
            "due_at": due_at.isoformat(),
            "message": message.strip()
            or ("Timer" if kind == "timer" else "Reminder"),
            "kind": kind,
        }
        with self._lock:
            self._reminders.append(reminder)
            if not self._save():
                self._reminders.pop()
                return "I couldn't save that reminder. Check local storage permissions and try again."
        self._wake.set()
        if self.on_change:
            try:
                self.on_change(self.list_reminders())
            except Exception as error:
                print(f"[Reminder Error]: Could not update countdown display: {error}")
        due_label = due_at.astimezone().strftime("%B %d, %Y at %I:%M %p")
        label = "Timer" if kind == "timer" else "Reminder"
        return f"{label} set for {due_label}: {reminder['message']} (ID {reminder['id']})."

    def list_reminders(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._reminders]

    def cancel(self, reminder_id: str | None = None) -> int:
        with self._lock:
            if reminder_id:
                remaining = [
                    item for item in self._reminders
                    if item["id"].lower() != reminder_id.lower()
                ]
            else:
                remaining = []
            removed = len(self._reminders) - len(remaining)
            if removed:
                previous = self._reminders
                self._reminders = remaining
                if not self._save():
                    self._reminders = previous
                    return -1
        if removed:
            self._wake.set()
            if self.on_change:
                try:
                    self.on_change(self.list_reminders())
                except Exception as error:
                    print(f"[Reminder Error]: Could not update countdown display: {error}")
        return removed

    def _fire_due(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        due = []
        remaining = []
        with self._lock:
            for reminder in self._reminders:
                due_at = datetime.fromisoformat(reminder["due_at"])
                if due_at.tzinfo is None:
                    due_at = due_at.replace(tzinfo=timezone.utc)
                (due if due_at <= now else remaining).append(reminder)
            if due:
                previous = self._reminders
                self._reminders = remaining
                if not self._save():
                    self._reminders = previous
                    return []
        if due and self.on_change:
            try:
                self.on_change(self.list_reminders())
            except Exception as error:
                print(f"[Reminder Error]: Could not update countdown display: {error}")
        for reminder in due:
            if self.on_due:
                try:
                    label = (
                        "Timer"
                        if reminder.get("kind") == "timer"
                        else "Reminder"
                    )
                    self.on_due(f"{label}: {reminder['message']}")
                except Exception as error:
                    print(f"[Reminder Error]: Could not display reminder alert: {error}")
        return due

    def _run(self):
        while not self._stopping:
            self._wake.wait(timeout=1.0)
            self._wake.clear()
            self._fire_due()

    def stop(self):
        self._stopping = True
        self._wake.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
