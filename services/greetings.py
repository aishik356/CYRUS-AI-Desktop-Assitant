import ctypes
import locale
import re
import sys
from datetime import datetime

import holidays


_HOLIDAY_GREETINGS = {
    "christmas": "Merry Christmas",
    "new year's day": "Happy New Year",
    "new year's eve": "Happy New Year",
    "eid al-fitr": "Eid Mubarak",
    "eid al-adha": "Eid Mubarak",
    "diwali": "Happy Diwali",
    "hanukkah": "Happy Hanukkah",
    "lunar new year": "Happy Lunar New Year",
    "chinese new year": "Happy Lunar New Year",
    "thanksgiving": "Happy Thanksgiving",
}


def detect_country_code() -> str | None:
    if sys.platform == "win32":
        try:
            country_name = ctypes.create_unicode_buffer(3)
            if ctypes.windll.kernel32.GetUserDefaultGeoName(country_name, 3):
                country_code = country_name.value.upper()
                if re.fullmatch(r"[A-Z]{2}", country_code):
                    return country_code
        except (AttributeError, OSError):
            pass

    locale_name = locale.getlocale()[0] or ""
    match = re.search(r"(?:^|[_-])([A-Za-z]{2})(?:$|[.@_-])", locale_name)
    if match:
        return match.group(1).upper()
    return None


def _time_of_day(local_time: datetime) -> str:
    if 5 <= local_time.hour < 12:
        return "morning"
    if 12 <= local_time.hour < 18:
        return "afternoon"
    if 18 <= local_time.hour < 22:
        return "evening"
    return "night"


def holiday_greeting(
    local_time: datetime,
    country_code: str | None = None,
) -> str:
    country = (country_code or detect_country_code() or "").upper()
    if not country:
        return ""
    try:
        holiday_names = holidays.country_holidays(country, years=[local_time.year])
    except (AttributeError, KeyError, NotImplementedError, ValueError):
        return ""
    names = holiday_names.get(local_time.date())
    if not names:
        return ""
    for holiday_name in str(names).split("; "):
        normalized = holiday_name.casefold()
        for marker, greeting in _HOLIDAY_GREETINGS.items():
            if marker in normalized:
                return greeting
    return f"Happy {str(names).split('; ', 1)[0]}."


def contextual_greeting(
    preferred_name: str = "",
    local_time: datetime | None = None,
    country_code: str | None = None,
) -> str:
    moment = local_time or datetime.now().astimezone()
    salutation = f"Good {_time_of_day(moment)}"
    name = preferred_name.strip()
    if name:
        salutation = f"{salutation}, {name}"

    holiday = holiday_greeting(moment, country_code)
    if holiday:
        if holiday.endswith("."):
            return f"{salutation}. {holiday}"
        return f"{salutation}. {holiday}! How can I help?"
    return f"{salutation}. How can I help?"
