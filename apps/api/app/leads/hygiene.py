"""Lead name and phone hygiene (#15): ad forms fill names with emoji, fancy Unicode, business
names and social handles. `clean_name` makes a plain name and says whether a person must look at
it; `normalise_phone` turns Tajik numbers into +992XXXXXXXXX. Pure functions, no database.
"""

import re
import unicodedata
from dataclasses import dataclass

MAX_WORDS = 4
_URL = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|ru|tj|uz|net|org|io|me|info|biz)\b)", re.I)
_HANDLE = re.compile(r"^@?[A-Za-z0-9._]+$")
# characters that never belong in a name: invisible (Cf: zero-width, joiners, bidi marks), symbols
# and pictographs (S*: emoji, stars, arrows, dingbats), controls, surrogates, private use,
# unassigned; and the combining marks that turn text into emoji (variation selectors, keycap)
_INVISIBLE = {"Cf", "Me"}
_DROP_CATEGORIES = {"Cc", "Cs", "Co", "Cn", "So", "Sk", "Sm", "Sc"}
_VARIATION = re.compile("[︀-️\U000e0100-\U000e01ef]")
_EDGE = " \t-–—_.,:;!?~*•·'\"«»()[]{}/\\"
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class CleanName:
    name: str
    needs_review: bool


def _plain(text: str) -> str:
    """Compatibility forms to plain letters: 𝗟𝗶𝘃𝗲 -> Live, fullwidth -> ascii."""
    return unicodedata.normalize("NFKC", text)


def _strip(text: str) -> str:
    kept = []
    for ch in _VARIATION.sub("", text):
        category = unicodedata.category(ch)
        if category in _INVISIBLE:
            continue  # zero-width joiners sit inside a word: the word stays whole
        kept.append(" " if category in _DROP_CATEGORIES else ch)  # `Ali|Sales` must not glue
    return _SPACES.sub(" ", "".join(kept)).strip(_EDGE + "@")


def _looks_off(plain: str, cleaned: str) -> bool:
    """`plain` is the NFKC text with the decoration still in it (a `|` or `>` is a symbol that the
    cleaning removes, so the signals are read before it)."""
    if not any(ch.isalpha() for ch in cleaned):
        return True
    if "|" in plain or ">" in plain or "@" in plain or _URL.search(plain):
        return True
    if any(ch.isdigit() for ch in cleaned):
        return True
    if len(cleaned.split()) > MAX_WORDS:
        return True
    probe = plain.strip()
    return bool(_HANDLE.fullmatch(probe)) and (
        "_" in probe or "." in probe or probe.startswith("@") or any(c.isdigit() for c in probe)
    )


def clean_name(raw: str | None) -> CleanName:
    """The plain name and the «needs review» flag. An empty result becomes «Без имени»."""
    plain = _plain(raw or "")
    cleaned = _strip(plain)
    flag = _looks_off(plain, cleaned)
    return CleanName(cleaned or "Без имени", flag)


_NON_DIGITS = re.compile(r"\D")


def normalise_phone(raw: str | None) -> str | None:
    """+992XXXXXXXXX for a Tajik number written in any common way (9 local digits, 992…, 00992…,
    a leading 0); None when it cannot be told (the raw text stays in `phone_raw`)."""
    if not raw:
        return None
    digits = _NON_DIGITS.sub("", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 12 and digits.startswith("992"):
        return "+" + digits
    if len(digits) == 9:
        return "+992" + digits
    if len(digits) == 10 and digits.startswith("0"):
        return "+992" + digits[1:]
    return None


def phone_key(value: str | None) -> str | None:
    """The same key the database computes (`phone_key()`): the last 9 digits."""
    digits = _NON_DIGITS.sub("", value or "")
    return digits[-9:] if len(digits) >= 9 else None


def phone_parts(raw: str | None) -> tuple[str | None, str | None]:
    """(phone to store, raw text): the normalised number when possible, else the trimmed raw."""
    text = (raw or "").strip()
    if not text:
        return None, None
    return normalise_phone(text) or text, text


def neutral(text: str | None) -> str | None:
    """Imported free text must never start a spreadsheet formula."""
    if text is None:
        return None
    out = text.strip().lstrip("=+-@\t\r ").strip()
    return out or None
