"""Layout schema v1: a certificate template as data. Pydantic models, unknown keys refused.

`parse_layout` is the one entry point: it also checks the field keys against the catalog
(`cert_field_unknown`), the layer count, the unique layer ids and the 200 KB size.
"""

import json
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.certificates.errors import CERT_FIELD_UNKNOWN, CERT_LAYOUT_INVALID
from app.certificates.fields import DATE_FORMATS, FIELDS
from app.certificates.fonts import FAMILIES
from app.core.errors import DomainError

MAX_LAYERS = 40
MAX_JSON_BYTES = 200 * 1024
MAX_TEXT_CHARS = 1000

Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,40}$")]
AssetRef = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Mm = Annotated[float, Field(gt=0, le=2000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(Strict):
    width_mm: float = Field(ge=50, le=600)
    height_mm: float = Field(ge=50, le=600)


class Background(Strict):
    asset: AssetRef


class TextRun(Strict):
    text: str


class FieldRun(Strict):
    field: str
    format: str | None = None


class GenderRun(Strict):
    class Words(Strict):
        male: str
        female: str

    gender: Words


Run = TextRun | FieldRun | GenderRun


class TextStyle(Strict):
    font: str
    weight: int = Field(default=400, ge=100, le=900)
    italic: bool = False
    size_pt: float = Field(gt=0, le=200)
    min_size_pt: float | None = Field(default=None, gt=0, le=200)
    color: Color
    align: Literal["left", "center", "right"] = "left"
    valign: Literal["top", "middle", "bottom"] = "top"
    line_height: float = Field(default=1.2, ge=0.5, le=4)
    letter_spacing_pt: float = Field(default=0, ge=-5, le=50)
    uppercase: bool = False

    @model_validator(mode="after")
    def _check(self) -> TextStyle:
        if self.font not in FAMILIES:
            raise ValueError(f"font must be one of {sorted(FAMILIES)}")
        if self.min_size_pt is None:
            self.min_size_pt = self.size_pt
        if self.min_size_pt > self.size_pt:
            raise ValueError("min_size_pt is above size_pt")
        return self


class Box(Strict):
    id: Slug
    x_mm: float = Field(ge=-1000, le=2000)
    y_mm: float = Field(ge=-1000, le=2000)
    w_mm: Mm
    h_mm: Mm
    rotation: float = Field(default=0, ge=-360, le=360)
    locked: bool = False


class TextLayer(Box):
    type: Literal["text"]
    style: TextStyle
    content: list[Run] = Field(max_length=50)

    @model_validator(mode="after")
    def _chars(self) -> TextLayer:
        total = 0
        for run in self.content:
            if isinstance(run, TextRun):
                total += len(run.text)
            elif isinstance(run, GenderRun):
                total += max(len(run.gender.male), len(run.gender.female))
        if total > MAX_TEXT_CHARS:
            raise ValueError(f"text is longer than {MAX_TEXT_CHARS} characters")
        return self


class AssetSource(Strict):
    asset: AssetRef


class SignatureSource(Strict):
    signature: Literal["instructor"]


class ImageLayer(Box):
    type: Literal["image"]
    source: AssetSource | SignatureSource
    fit: Literal["contain"] = "contain"


class QrLayer(Box):
    type: Literal["qr"]
    color: Color = "#000000"


class LineLayer(Box):
    type: Literal["line"]
    color: Color
    thickness_mm: float = Field(default=0.3, gt=0, le=20)
    dash: bool = False


Layer = Annotated[TextLayer | ImageLayer | QrLayer | LineLayer, Field(discriminator="type")]


class Layout(Strict):
    schema_: Literal[1] = Field(alias="schema")
    page: Page
    background: Background | None = None
    layers: list[Layer] = Field(max_length=MAX_LAYERS)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _unique_ids(self) -> Layout:
        ids = [layer.id for layer in self.layers]
        if len(ids) != len(set(ids)):
            raise ValueError("layer ids must be unique")
        return self

    def asset_refs(self) -> list[str]:
        """Every asset reference, background first, in layer order."""
        refs = [self.background.asset] if self.background else []
        for layer in self.layers:
            if isinstance(layer, ImageLayer) and isinstance(layer.source, AssetSource):
                refs.append(layer.source.asset)
        return refs

    def map_assets(self, mapping: dict[str, str]) -> Layout:
        """A copy with every asset reference replaced through `mapping`."""
        data = self.dump()
        if data["background"]:
            data["background"]["asset"] = mapping[data["background"]["asset"]]
        for layer in data["layers"]:
            if layer["type"] == "image" and "asset" in layer["source"]:
                layer["source"]["asset"] = mapping[layer["source"]["asset"]]
        return Layout.model_validate(data)

    def dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


def parse_layout(data: Any) -> Layout:
    """Validate a layout: 422 `cert_layout_invalid` or `cert_field_unknown`."""
    try:
        size = len(json.dumps(data, ensure_ascii=False).encode())
    except TypeError, ValueError:
        raise DomainError(CERT_LAYOUT_INVALID) from None
    if size > MAX_JSON_BYTES:
        raise DomainError(CERT_LAYOUT_INVALID, reason="too_large")
    try:
        layout = Layout.model_validate(data)
    except ValidationError as exc:
        problems = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()[:10]]
        raise DomainError(CERT_LAYOUT_INVALID, problems=problems) from None
    for layer in layout.layers:
        if not isinstance(layer, TextLayer):
            continue
        for run in layer.content:
            if isinstance(run, FieldRun):
                if run.field not in FIELDS:
                    raise DomainError(CERT_FIELD_UNKNOWN, field=run.field, layer=layer.id)
                if run.format is not None and run.format not in DATE_FORMATS:
                    raise DomainError(CERT_LAYOUT_INVALID, reason="date_format", layer=layer.id)
    return layout
