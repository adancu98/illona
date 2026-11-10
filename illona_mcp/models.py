"""Validated, bounded inputs; all coordinates are relative to an explicit artboard."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Color(StrictModel):
    space: Literal["rgb", "cmyk"] = "rgb"
    values: list[float] = Field(min_length=3, max_length=4)

    @model_validator(mode="after")
    def check_channels(self):
        count, maximum = (3, 255) if self.space == "rgb" else (4, 100)
        if len(self.values) != count or any(v < 0 or v > maximum for v in self.values):
            raise ValueError(f"{self.space} requires {count} channels between 0 and {maximum}")
        return self


HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Paint = HexColor | Color


class Stroke(StrictModel):
    color: Paint = "#182D43"
    width_pt: float = Field(default=1, gt=0, le=1000)


class Handle(StrictModel):
    x: float
    y: float


class PathPoint(Handle):
    left: Handle | None = None
    right: Handle | None = None
    smooth: bool = False


class Element(StrictModel):
    type: Literal["rect", "ellipse", "path", "text", "image"]
    name: str = Field(default="", max_length=200)
    x: float = 0
    y: float = 0
    width: float | None = Field(default=None, gt=0, le=10000)
    height: float | None = Field(default=None, gt=0, le=10000)
    fill: Paint | None = None
    stroke: Stroke | None = None
    opacity: float = Field(default=100, ge=0, le=100)
    points: list[PathPoint] | None = Field(default=None, min_length=2, max_length=1000)
    closed: bool = True
    text: str | None = Field(default=None, max_length=30000)
    font: str | None = Field(default=None, max_length=200)
    size_pt: float = Field(default=12, gt=0, le=1000)
    color: Paint = "#182D43"
    tracking: float | None = Field(default=None, ge=-1000, le=10000)
    leading_pt: float | None = Field(default=None, gt=0, le=2000)
    path: str | None = Field(default=None, min_length=1, max_length=4096)
    fit: Literal["contain", "cover"] = "contain"
    embed: bool = True

    @model_validator(mode="after")
    def check_geometry(self):
        if self.type in ("rect", "ellipse", "image") and (self.width is None or self.height is None):
            raise ValueError("Rectangles, ellipses and images require width and height")
        if self.type == "path" and not self.points:
            raise ValueError("Paths require at least two points")
        if self.type == "text" and self.text is None:
            raise ValueError("Text elements require text")
        if self.type == "text" and ((self.width is None) != (self.height is None)):
            raise ValueError("Area text requires both width and height; omit both for point text")
        if self.type == "image":
            if not {"x", "y"}.issubset(self.model_fields_set):
                raise ValueError("Images require explicit x and y coordinates")
            if self.path is None or not self.path.startswith("/") or "\0" in self.path:
                raise ValueError("Images require an absolute local path")
            if not self.path.lower().endswith((".jpg", ".jpeg", ".png")):
                raise ValueError("Images currently support JPG, JPEG and PNG files")
        return self


class ObjectChange(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=200)
    x: float | None = None
    y: float | None = None
    width: float | None = Field(default=None, gt=0, le=10000)
    height: float | None = Field(default=None, gt=0, le=10000)
    fill: Paint | None = None
    stroke: Stroke | None = None
    text: str | None = Field(default=None, max_length=30000)
    font: str | None = Field(default=None, max_length=200)
    size_pt: float | None = Field(default=None, gt=0, le=1000)
    opacity: float | None = Field(default=None, ge=0, le=100)


class Panel(StrictModel):
    title: str = Field(default="", max_length=300)
    body: str = Field(default="", max_length=6000)


class Palette(StrictModel):
    ink: HexColor = "#182D43"
    accent: HexColor = "#E66E51"
    paper: HexColor = "#F7F2E8"
    leaf: HexColor = "#578A76"

