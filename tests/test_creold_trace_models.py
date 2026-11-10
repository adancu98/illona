"""Image-trace inputs stay bounded and separate from geometry/raw code."""
import pytest
from pydantic import ValidationError

from illona_mcp.creold_models import ACTION_NAMES, ACTION_SOURCES, CreoldActionOptions, validate_action_options


def test_trace_action_is_in_catalog_with_original_attribution_and_native_defaults():
    assert len(ACTION_NAMES)==14 and "trace_images" in ACTION_NAMES
    assert ACTION_SOURCES["trace_images"]=="BatchTrace.jsx"
    options=CreoldActionOptions()
    assert options.preset=="16 Colors" and options.ignore_white is True
    assert validate_action_options("trace_images",options)=={}
    assert validate_action_options("trace_images",{"preset":"Black and White Logo","ignore_white":False})=={
        "preset":"Black and White Logo","ignore_white":False}


@pytest.mark.parametrize("options",[{"preset":""},{"preset":"x"*201},{"ignore_white":[]},{"jsx":"app.quit();"}])
def test_trace_options_reject_invalid_or_arbitrary_code_fields(options):
    with pytest.raises(ValidationError):
        validate_action_options("trace_images",options)


@pytest.mark.parametrize("action,options",[
    ("trace_images",{"value":20}),
    ("trace_images",{"point_indices":[1]}),
    ("change_opacity",{"value":50,"preset":"16 Colors"}),
    ("reverse_gradient_colors",{"ignore_white":True}),
])
def test_image_trace_fields_do_not_leak_into_other_actions(action,options):
    with pytest.raises(ValueError,match="Options not used"):
        validate_action_options(action,options)
