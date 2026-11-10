"""Bounded parameters for explicit, headless adaptations of Creold scripts.

The complete original library remains a separate interactive catalog. These
actions deliberately expose a documented subset with no ScriptUI or raw JSX.
"""

from typing import Annotated, Literal, get_args

from pydantic import Field, model_validator

from .models import Paint, StrictModel, Stroke


CreoldActionName = Literal[
    "reverse_gradient_colors", "distribute_gradient_stops", "remove_gradient_stops",
    "cycle_gradient_colors", "stroke_color_from_fill", "average_stroke_width",
    "align_text_baselines", "round_coordinates", "set_point_coordinates",
    "transform_points", "draw_artboard_rectangles", "change_opacity", "average_colors",
    "trace_images",
]
ACTION_NAMES = get_args(CreoldActionName)
ACTION_SOURCES = {
    "reverse_gradient_colors": "ReverseGradientColor.jsx",
    "distribute_gradient_stops": "DistributeGradientStops.jsx",
    "remove_gradient_stops": "RemoveGradientStops.jsx",
    "cycle_gradient_colors": "CycleGradientForward.jsx",
    "stroke_color_from_fill": "StrokeColorFromFill.jsx",
    "average_stroke_width": "AverageStrokesWidth.jsx",
    "align_text_baselines": "AlignTextBaseline.jsx",
    "round_coordinates": "RoundCoordinates.jsx",
    "set_point_coordinates": "SetPointsCoordinates.jsx",
    "transform_points": "TransformPoints.jsx",
    "draw_artboard_rectangles": "DrawRectanglesByArtboards.jsx",
    "change_opacity": "ChangeOpacity.jsx",
    "average_colors": "AverageColors.jsx",
    "trace_images": "BatchTrace.jsx",
}

PointIndex = Annotated[int, Field(ge=0, le=99999)]
ArtboardIndex = Annotated[int, Field(ge=0, le=999)]
BoundedCoordinate = Annotated[float, Field(ge=-1_000_000, le=1_000_000)]


class CreoldActionOptions(StrictModel):
    """Union of action-specific fields; validate_action_options checks relevance.

    All *_pt values use native document points, X right and Y up. Points are
    explicit zero-based indices on every targeted path; omitted indices mean all
    anchors. Gradients are isolated from unselected artwork before changing stops.
    """

    target: Literal["fill", "stroke", "both"] = Field(default="fill", description="Paint channel for gradient actions. average_colors accepts fill or stroke only.")
    steps: int = Field(default=1, ge=-256, le=256, description="cycle_gradient_colors: positive cycles forward, negative backward; stop positions and opacity stay fixed.")
    shift_percent: float = Field(default=0, ge=-100, le=100)
    width_pt: float | None = Field(default=None, ge=0.01, le=1000)
    precision: int = Field(default=2, ge=0, le=4)
    baseline_y_pt: BoundedCoordinate | None = None
    reference_uuid: str | None = Field(default=None, min_length=1, max_length=200)
    spacing_pt: float = Field(default=0, ge=0, le=10000, description="Baseline spacing in explicit target order, descending in document Y. Zero aligns all targeted point texts on one baseline.")
    step_pt: float = Field(default=1, ge=0.000001, le=10000)
    reference: Literal["center", "top_left"] = "center"
    include_stroke: bool = False
    point_indices: list[PointIndex] | None = Field(default=None, min_length=1, max_length=5000, description="Zero-based indices applied to every targeted path leaf; omit to transform all anchors. Handles move with their anchors.")
    x_pt: BoundedCoordinate | None = None
    y_pt: BoundedCoordinate | None = None
    relative: bool = False
    scale_x_pct: float = Field(default=100, ge=-10000, le=10000)
    scale_y_pct: float = Field(default=100, ge=-10000, le=10000)
    angle_deg: float = Field(default=0, ge=-360000, le=360000)
    dx_pt: BoundedCoordinate = 0
    dy_pt: BoundedCoordinate = 0
    origin_x_pt: BoundedCoordinate | None = None
    origin_y_pt: BoundedCoordinate | None = None
    artboard_indices: list[ArtboardIndex] | None = Field(default=None, min_length=1, max_length=100)
    bleed_pt: float = Field(default=0, ge=0, le=10000)
    layer_name: str = Field(default="Creold / Artboard rectangles", min_length=1, max_length=200)
    fill: Paint | None = None
    stroke: Stroke | None = None
    mode: Literal["absolute", "delta", "multiply"] = "absolute"
    value: float = Field(default=100, ge=-10000, le=10000, description="Opacity: absolute percentage, signed delta in percentage points, or direct multiplication factor (0.5 halves opacity). Results clamp to 0–100.")
    average_method: Literal["arithmetic", "rms"] = Field(default="arithmetic", description="Same-color-space averaging of path colors. rms uses root-mean-square channels for RGB; CMYK/Gray use arithmetic. Each path has equal weight; its gradient stops divide that weight equally.")
    preset: str = Field(default="16 Colors", min_length=1, max_length=200, description="trace_images: exact preset name from Illustrator's installed tracingPresetsList. Unavailable names fail before tracing any image.")
    ignore_white: bool = Field(default=True, description="trace_images: omit white areas and always expand to editable vector paths. Removing white margins can change output bounds.")

    @model_validator(mode="after")
    def check_pairs_and_indices(self):
        if (self.origin_x_pt is None) != (self.origin_y_pt is None):
            raise ValueError("Supply both origin_x_pt and origin_y_pt, or neither")
        for label in ("point_indices", "artboard_indices"):
            values = getattr(self, label)
            if values is not None and len(values) != len(set(values)):
                raise ValueError(f"{label} must not contain duplicates")
        if self.stroke is not None and self.stroke.width_pt < 0.01:
            raise ValueError("stroke.width_pt must be at least 0.01")
        return self


ACTION_OPTION_FIELDS = {
    "reverse_gradient_colors": {"target"},
    "distribute_gradient_stops": {"target"},
    "remove_gradient_stops": {"target"},
    "cycle_gradient_colors": {"target", "steps"},
    "stroke_color_from_fill": {"shift_percent", "width_pt"},
    "average_stroke_width": {"precision"},
    "align_text_baselines": {"baseline_y_pt", "reference_uuid", "spacing_pt"},
    "round_coordinates": {"step_pt", "reference", "include_stroke"},
    "set_point_coordinates": {"point_indices", "x_pt", "y_pt", "relative"},
    "transform_points": {"point_indices", "scale_x_pct", "scale_y_pct", "angle_deg",
                         "dx_pt", "dy_pt", "origin_x_pt", "origin_y_pt"},
    "draw_artboard_rectangles": {"artboard_indices", "bleed_pt", "layer_name", "fill", "stroke"},
    "change_opacity": {"mode", "value"},
    "average_colors": {"target", "average_method"},
    "trace_images": {"preset", "ignore_white"},
}


def validate_action_options(action: str, options: CreoldActionOptions | dict) -> dict:
    """Validate an action before receipts/native work and return explicit fields."""
    if action not in ACTION_OPTION_FIELDS:
        raise ValueError("Unknown Creold action")
    options = options if isinstance(options, CreoldActionOptions) else CreoldActionOptions.model_validate(options)
    unexpected = options.model_fields_set - ACTION_OPTION_FIELDS[action]
    if unexpected:
        raise ValueError(f"Options not used by {action}: {', '.join(sorted(unexpected))}")
    if action == "draw_artboard_rectangles" and not options.artboard_indices:
        raise ValueError("draw_artboard_rectangles requires artboard_indices")
    if action == "set_point_coordinates" and options.x_pt is None and options.y_pt is None:
        raise ValueError("set_point_coordinates requires x_pt or y_pt")
    if action == "align_text_baselines" and options.baseline_y_pt is not None and options.reference_uuid is not None:
        raise ValueError("Use baseline_y_pt or reference_uuid, not both")
    if action == "average_colors" and options.target == "both":
        raise ValueError("average_colors target must be fill or stroke")
    if action == "change_opacity":
        if "value" not in options.model_fields_set:
            raise ValueError("change_opacity requires value")
        if options.mode == "absolute" and not 0 <= options.value <= 100:
            raise ValueError("Absolute opacity must be between 0 and 100")
        if options.mode == "delta" and not -100 <= options.value <= 100:
            raise ValueError("Opacity delta must be between -100 and 100")
        if options.mode == "multiply" and not 0 <= options.value <= 100:
            raise ValueError("Opacity multiplier must be between 0 and 100")
    return options.model_dump(exclude_unset=True, exclude_none=True)
