"""Bundled fonts. Only these families can be named by a template; every file holds Latin,
Cyrillic and the Tajik letters (ғ ҳ ҷ ӣ қ ӯ). Static instances of the OFL Montserrat
variable font."""

from functools import cache
from pathlib import Path

from fontTools.ttLib import TTFont

DIR = Path(__file__).parent / "fonts"
FAMILIES: dict[str, dict[bool, tuple[int, ...]]] = {
    "Montserrat": {False: (400, 500, 600, 700, 800), True: (400, 700)},
}


def nearest_weight(family: str, weight: int, italic: bool) -> tuple[int, bool]:
    """The bundled (weight, italic) closest to the request; italic falls back to upright when
    the family has no italic."""
    sets = FAMILIES[family]
    if italic and not sets[True]:
        italic = False
    return min(sets[italic], key=lambda w: abs(w - weight)), italic


def file_name(family: str, weight: int, italic: bool) -> str:
    return f"{family}-{weight}{'Italic' if italic else ''}.ttf"


def font_files() -> list[tuple[str, int, bool, str]]:
    """(family, weight, italic, file name) of every bundled face."""
    return [
        (fam, w, italic, file_name(fam, w, italic))
        for fam, sets in FAMILIES.items()
        for italic, weights in sets.items()
        for w in weights
    ]


class Face:
    """Glyph advances of one font file, in em."""

    def __init__(self, path: Path) -> None:
        font = TTFont(path)
        self.upem: int = font["head"].unitsPerEm
        self.cmap: dict[int, str] = font.getBestCmap()
        self.hmtx = font["hmtx"].metrics
        self.fallback = self.hmtx.get(".notdef", (self.upem // 2, 0))[0]

    def advance(self, ch: str) -> float:
        name = self.cmap.get(ord(ch))
        return float(self.hmtx[name][0] if name in self.hmtx else self.fallback) / self.upem


@cache
def face(family: str, weight: int, italic: bool) -> Face:
    w, i = nearest_weight(family, weight, italic)
    return Face(DIR / file_name(family, w, i))
