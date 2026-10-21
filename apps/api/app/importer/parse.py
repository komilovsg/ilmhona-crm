"""Pure parsing helpers of the import from the old system (docs/IMPORT.md). No database here."""

import hashlib
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.leads.hygiene import clean_name, normalise_phone, phone_key

TZ = ZoneInfo("Asia/Dushanbe")
MIN_DATE, MAX_DATE = date(2020, 1, 1), date(2035, 12, 31)
# calibration of the old lesson times (docs/IMPORT.md): 07:05 -> 18:30, 05:35 -> 17:00
TIME_SHIFT = timedelta(hours=11, minutes=25)

_JS_DATE = re.compile(
    r"^\s*\w{3} (\w{3}) (\d{1,2}) (\d{4}) (\d{2}):(\d{2}):(\d{2}) GMT([+-])(\d{2})(\d{2})"
)
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
    )
}


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
MAX_MONEY = Decimal("9999999999.99")  # numeric(12, 2), as the app's money fields
MAX_COUNT = 100_000
MAX_NAME = 200


def text(value: object) -> str:
    """Untrusted text of the old sheets: no NUL or other control characters (tab, newline stay)."""
    return "" if value is None else _CONTROL.sub("", str(value)).strip()


def clip(value: str | None, limit: int) -> str | None:
    """The app's length limit for the column (old cells can be any length)."""
    return value[:limit].strip() if value else value


def parse_dt(value: object) -> datetime | None:
    """`Mon May 04 2026 12:00:00 GMT+0500 (...)` -> an aware datetime in Asia/Dushanbe."""
    m = _JS_DATE.match(text(value))
    if not m or m.group(1) not in _MONTHS:
        return None
    month, day, year, hh, mm, ss, sign, oh, om = m.groups()
    try:
        offset = timezone(
            (1 if sign == "+" else -1) * timedelta(hours=int(oh), minutes=int(om)),
        )
        moment = datetime(
            int(year), _MONTHS[month], int(day), int(hh), int(mm), int(ss), tzinfo=offset
        )
    except ValueError:
        return None
    return moment.astimezone(TZ)


def parse_date(value: object) -> date | None:
    """The local date, or None when empty, unreadable or outside 2020-2035 (#8)."""
    moment = parse_dt(value)
    if moment is None or not MIN_DATE <= moment.date() <= MAX_DATE:
        return None
    return moment.date()


def parse_clock(value: object) -> time | None:
    """A lesson time of the old sheets: the clock as written, shifted by +11:25.

    The sheets store a bare time as a 1899 date. `Sun Dec 31 1899` values are the calibrated ones;
    anything else (`Sat Dec 30 1899`, other years) cannot be trusted and gives None."""
    m = _JS_DATE.match(text(value))
    if not m or (m.group(1), m.group(2), m.group(3)) != ("Dec", "31", "1899"):
        return None
    shifted = datetime(2000, 1, 1, int(m.group(4)), int(m.group(5))) + TIME_SHIFT
    return shifted.time().replace(second=0)


def lesson_window_ok(start: time | None, end: time | None) -> bool:
    """07:00-22:00 and 30-240 minutes (#6)."""
    if start is None or end is None:
        return False
    if start < time(7, 0) or end > time(22, 0):
        return False
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return 30 <= minutes <= 240


def _number(value: object) -> Decimal | None:
    raw = text(value).replace(",", ".").replace(" ", "")
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None  # NaN, sNaN, Infinity


def to_int(value: object) -> int | None:
    """A count / month / score: a whole number within ±100 000."""
    number = _number(value)
    if number is None or abs(number) > MAX_COUNT or number != number.to_integral_value():
        return None
    return int(number)


def to_decimal(value: object) -> Decimal | None:
    """Money as the app takes it: at most 2 decimals, below 10^10 (numeric(12, 2))."""
    number = _number(value)
    if number is None or abs(number) > MAX_MONEY:
        return None
    exponent = number.normalize().as_tuple().exponent
    return number if isinstance(exponent, int) and exponent >= -2 else None


# ---- names, phones --------------------------------------------------------------------------


def norm_name(value: object) -> str:
    plain = unicodedata.normalize("NFKC", text(value)).casefold().replace("ё", "е")
    plain = re.sub(r"[^\w\s]|_", " ", plain)
    return re.sub(r"\s+", " ", plain).strip()


def name_of(value: object) -> tuple[str, bool]:
    """(clean name, needs review) with the hygiene of the leads (#15)."""
    cleaned = clean_name(text(value)[: MAX_NAME * 2])
    name = clip(cleaned.name, MAX_NAME) or cleaned.name
    return name, cleaned.needs_review or name != cleaned.name


def phone_of(value: object) -> tuple[str | None, str]:
    """(+992XXXXXXXXX or None when unreadable, the original text)."""
    raw = text(value)
    return (normalise_phone(raw) if raw else None), raw


def phone9(value: object) -> str | None:
    return phone_key(normalise_phone(text(value)) or text(value))


_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "e", "ж": "j",
    "з": "z", "и": "i", "ӣ": "i", "й": "i", "к": "k", "қ": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ӯ": "u", "ф": "f", "х": "h",
    "ҳ": "h", "ц": "c", "ч": "c", "ш": "s", "щ": "s", "ъ": "", "ы": "i", "ь": "", "э": "e",
    "ю": "u", "я": "a",
}  # fmt: skip
_LAT_FOLD = (
    ("kh", "h"), ("sh", "s"), ("ch", "c"), ("zh", "j"), ("ts", "c"), ("yu", "u"), ("ya", "a"),
    ("yo", "e"), ("ou", "u"), ("x", "h"), ("y", "i"), ("w", "v"), ("q", "k"), ("'", ""),
)  # fmt: skip
_LAT_PLAIN = str.maketrans({"ё": "e"})


def translit_key(value: object) -> str:
    """The same person in Latin and Cyrillic gets the same key (#10): letters folded to a coarse
    Latin form, words sorted (so «Ali Karimov» = «Каримов Али»)."""
    words = []
    for word in norm_name(value).split():
        latin = "".join(_CYR.get(ch, ch) for ch in word.translate(_LAT_PLAIN))
        for src, dst in _LAT_FOLD:
            latin = latin.replace(src, dst)
        latin = re.sub(r"[^a-z]", "", latin)
        latin = re.sub(r"(.)\1+", r"\1", latin)
        if latin:
            words.append(latin)
    return " ".join(sorted(words))


def _typo(a: str, b: str) -> bool:
    """Two words of 4+ letters that differ by one letter (substitution, insert or delete)."""
    if min(len(a), len(b)) < 4 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


def same_person(a: object, b: object) -> bool:
    """Same student under two spellings? Words are compared in the coarse Latin form (so Latin =
    Cyrillic) and in any order. Rule: at least one word is exactly equal, and
    2 * matched / (words_a + words_b) >= 0.8, where a word of 4+ letters also matches a word that
    differs by one letter. «Ali Karimov» = «Каримов Али» = «Ali Karimof»; siblings «Ali Karimov» and
    «Aziza Karimov» (0.5) and different first names are not the same person."""
    wa, wb = translit_key(a).split(), translit_key(b).split()
    if not wa or not wb:
        return False
    total_words = len(wa) + len(wb)
    left, rest, exact = list(wb), [], 0
    for w in wa:  # exact words first, so a typo never steals an exact partner
        if w in left:
            left.remove(w)
            exact += 1
        else:
            rest.append(w)
    typo = 0
    for w in rest:
        hit = next((x for x in left if _typo(w, x)), None)
        if hit is not None:
            left.remove(hit)
            typo += 1
    return exact >= 1 and 2 * (exact + typo) / total_words >= 0.8


def slug(value: object) -> str:
    """A login from a name: `Ali Karimov` / `Али Каримов` -> `ali.karimov`."""
    parts = []
    for word in norm_name(value).split():
        latin = "".join(_CYR.get(ch, ch) for ch in word)
        latin = re.sub(r"[^a-z0-9]", "", latin)
        if latin:
            parts.append(latin)
    return ".".join(parts[:2])[:60]


# ---- grades ---------------------------------------------------------------------------------

OLD_HOMEWORK_MAX = 20
OLD_FINAL_MAX = 60
NEW_PART_MAX = 40


def parse_score(value: object) -> tuple[int, int, int] | None:
    """`score:A|B|C` = attendance / homework / final on the old scale (20 / 20 / 60)."""
    m = re.fullmatch(r"score:\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)", text(value))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def rescale(points: int, old_max: int) -> int:
    """Proportionally onto 0-40, halves up, never above 40."""
    return min(NEW_PART_MAX, (2 * points * NEW_PART_MAX + old_max) // (2 * old_max))


# ---- references -----------------------------------------------------------------------------


def make_ref(sheet: str, old_id: str, *key: object) -> str:
    """`legacy_ref`: the sheet, the old id (for tracing) and a short hash of the identifying
    values: old ids repeat for different people, so the id alone is not a key."""
    digest = hashlib.sha1("|".join(str(k) for k in key).encode()).hexdigest()[:8]  # noqa: S324
    return f"{sheet}:{old_id}~{digest}" if key else f"{sheet}:{old_id}"
