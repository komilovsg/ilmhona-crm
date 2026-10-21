"""A readable device name from a User-Agent: «Chrome · macOS». Order matters: Edge and Opera
also say Chrome, every Chrome says Safari, iPads and iPhones say «like Mac OS X»."""

import re

_BROWSERS = (
    (r"Edg(?:e|A|iOS)?/", "Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"YaBrowser/", "Яндекс Браузер"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"(?:Firefox|FxiOS)/", "Firefox"),
    (r"(?:Chrome|CriOS|Chromium)/", "Chrome"),
    (r"Safari/", "Safari"),
)
_SYSTEMS = (
    (r"iPhone|iPad|iPod", "iOS"),
    (r"Android", "Android"),
    (r"Windows", "Windows"),
    (r"Mac OS X|Macintosh", "macOS"),
    (r"CrOS", "ChromeOS"),
    (r"Linux|X11", "Linux"),
)


def device_name(user_agent: str | None) -> str:
    ua = user_agent or ""
    browser = next((name for pattern, name in _BROWSERS if re.search(pattern, ua)), None)
    system = next((name for pattern, name in _SYSTEMS if re.search(pattern, ua)), None)
    parts = [p for p in (browser, system) if p]
    return " · ".join(parts) if parts else "Неизвестное устройство"
