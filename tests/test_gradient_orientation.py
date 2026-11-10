"""Exercise gradient-only native transforms in a host VM, without Illustrator.

The fixture models Illustrator's fresh GradientColor readback and affine matrix
composition. Native rendering still needs the separate application acceptance
check; these tests prove the direction math and the transform's geometry flags.
"""

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from illona_mcp.bridge import HOST


HOST_FIXTURE = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const radians = angle => angle * Math.PI / 180;
function rotation(angle, scale) {
    const c = Math.cos(radians(angle)) * scale;
    const s = Math.sin(radians(angle)) * scale;
    return {mValueA:c, mValueB:s, mValueC:-s, mValueD:c, mValueTX:0, mValueTY:0};
}
function multiply(left, right) {
    return {
        mValueA:left.mValueA*right.mValueA + left.mValueC*right.mValueB,
        mValueB:left.mValueB*right.mValueA + left.mValueD*right.mValueB,
        mValueC:left.mValueA*right.mValueC + left.mValueC*right.mValueD,
        mValueD:left.mValueB*right.mValueC + left.mValueD*right.mValueD,
        mValueTX:left.mValueA*right.mValueTX + left.mValueC*right.mValueTY + left.mValueTX,
        mValueTY:left.mValueB*right.mValueTX + left.mValueD*right.mValueTY + left.mValueTY
    };
}
const clone = value => JSON.parse(JSON.stringify(value));
const initialBounds = input.bounds || [10, 110, 150, 50];
const corner = (x,y) => ({anchor:[x,y],leftDirection:[x,y],rightDirection:[x,y]});
const state = {
    color:{
        typename:'GradientColor', gradient:{name:'VM linear gradient', type:'linear'},
        // Illustrator's angle property can remain zero after a native transform.
        angle:0, length:input.length === undefined ? 140 : input.length,
        origin:[10, 80], matrix:rotation(input.existing_angle || 0, input.existing_scale || 1)
    },
    bounds:initialBounds,
    points:input.path_points || [corner(initialBounds[0],initialBounds[1]),corner(initialBounds[2],initialBounds[1]),
        corner(initialBounds[2],initialBounds[3]),corner(initialBounds[0],initialBounds[3])],
    strokeWidth:input.stroke_width === undefined ? 0.8 : input.stroke_width,
    textStrokeWidths:input.text_stroke_widths || [0.8,0.8],
    contents:'Editable native type', calls:[], reads:0
};
const context = {
    $:{global:{}},
    app:{getRotationMatrix:angle => rotation(angle, 1)},
    Transformation:{CENTER:'center'},
    GradientType:{LINEAR:'linear', RADIAL:'radial'}
};
vm.createContext(context);
for (const filename of process.argv.slice(1)) {
    vm.runInContext(fs.readFileSync(filename, 'utf8'), context, {filename});
}
const item = {
    typename:input.typename || 'PathItem', uuid:'native-gradient-fixture', filled:true, closed:input.closed !== false,
    transform:function(matrix, positions, fillPatterns, fillGradients, strokePatterns, lineWidths, about) {
        // Any geometry, pattern, or stroke transform is a contract violation.
        assert.strictEqual(arguments.length, 7);
        assert.strictEqual(positions, false);
        assert.strictEqual(fillPatterns, false);
        assert.strictEqual(fillGradients, true);
        assert.strictEqual(strokePatterns, false);
        // Illustrator 30.8.2 multiplies widths by this value. Unity preserves
        // strokes; the previous factor100 inflated a 0.4228pt stroke to42.28pt.
        assert.strictEqual(lineWidths, 1);
        assert.strictEqual(about, 'center');
        state.calls.push(clone(matrix));
        if (this.typename === 'TextFrame') state.textStrokeWidths = state.textStrokeWidths.map(width => width * lineWidths);
        else state.strokeWidth *= lineWidths;
        if (['stroke_drift','stroke_restore_ignored','transform_throw_after_stroke_drift'].includes(input.host_behavior)) {
            if (this.typename === 'TextFrame') state.textStrokeWidths = state.textStrokeWidths.map(width => width * 100);
            else state.strokeWidth *= 100;
        }
        if (input.host_behavior === 'transform_throw_after_stroke_drift') throw new Error('Native transform failed after changing stroke widths');
        if (input.host_behavior === 'ignore_all') return;
        let nativeMatrix = clone(matrix);
        if (input.host_behavior === 'ignore_scale') {
            const norm = Math.hypot(nativeMatrix.mValueA, nativeMatrix.mValueB);
            for (const key of ['mValueA','mValueB','mValueC','mValueD']) nativeMatrix[key] /= norm;
        }
        state.color.matrix = multiply(nativeMatrix, state.color.matrix);
        if (input.host_behavior === 'geometry_drift') state.bounds[0] += 0.1;
    }
};
function readColor() {
    state.reads++;
    return input.missing_gradient ? {typename:'RGBColor'} : clone(state.color);
}
const rejectAssignment = () => {throw new Error('A native gradient must be transformed, not reassigned');};
const characterAttributes = {};
Object.defineProperty(characterAttributes, 'fillColor', {get:readColor, set:rejectAssignment});
Object.defineProperty(characterAttributes, 'strokeWeight', {
    get:() => state.textStrokeWidths.every(width => width === state.textStrokeWidths[0]) ? state.textStrokeWidths[0] : undefined,
    set:() => {throw new Error('Mixed native text must never receive a uniform range-level stroke weight');}
});
item.textRange = {characterAttributes};
item.characters = state.textStrokeWidths.map((width,index) => {
    const attributes = {};
    Object.defineProperty(attributes,'strokeWeight',{
        get:() => state.textStrokeWidths[index],
        set:value => {if (input.host_behavior !== 'stroke_restore_ignored') state.textStrokeWidths[index] = value;}
    });
    return {characterAttributes:attributes};
});
Object.defineProperty(item.textRange, 'contents', {get:() => state.contents, set:rejectAssignment});
Object.defineProperties(item, {
    fillColor:{get:readColor, set:rejectAssignment},
    geometricBounds:{get:() => state.bounds.slice(), set:rejectAssignment},
    pathPoints:{get:() => clone(state.points), set:rejectAssignment},
    strokeWidth:{get:() => state.strokeWidth, set:value => {if (input.host_behavior !== 'stroke_restore_ignored') state.strokeWidth = value;}},
    position:{get:() => state.bounds.slice(0,2), set:rejectAssignment},
    width:{get:() => state.bounds[2]-state.bounds[0], set:rejectAssignment},
    height:{get:() => state.bounds[1]-state.bounds[3], set:rejectAssignment}
});
const before = {bounds:clone(state.bounds), points:clone(state.points), strokeWidth:state.strokeWidth, textStrokeWidths:clone(state.textStrokeWidths), contents:state.contents};
let report = null, error = null;
try {
    report = context.Illona.orientGradientFill(item, input.angle);
} catch (caught) {
    error = {code:caught.illonaCode || null, message:caught.message};
}
const after = {bounds:clone(state.bounds), points:clone(state.points), strokeWidth:state.strokeWidth, textStrokeWidths:clone(state.textStrokeWidths), contents:state.contents};
process.stdout.write(JSON.stringify({report,error,before,after,color:state.color,calls:state.calls,reads:state.reads}));
"""


@pytest.fixture(scope="module")
def node():
    candidate = os.getenv("ILLONA_TEST_NODE") or shutil.which("node")
    if not candidate:
        candidate = str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
    if not Path(candidate).is_file():
        pytest.skip("Node is unavailable for isolated gradient host checks")
    return candidate


def run_host(node, **params):
    completed = subprocess.run(
        [node, "-e", HOST_FIXTURE, str(HOST / "core.jsx"), str(HOST / "gradient_orientation.jsx")],
        input=json.dumps(params), capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert not completed.stderr
    return json.loads(completed.stdout)


def angle_difference(first, second):
    return (first - second + 180) % 360 - 180


@pytest.mark.parametrize("typename", ["PathItem", "TextFrame"])
@pytest.mark.parametrize("angle,existing_angle,existing_scale,length", [
    (0, 0, 1, 140),
    (90, 0, 1, 140),
    (45, 0, 1, 140),
    (45, 30, 2, 70),
])
def test_gradient_orientation_and_projected_span_preserve_editable_artwork(
    node, typename, angle, existing_angle, existing_scale, length,
):
    result = run_host(node, typename=typename, angle=angle, existing_angle=existing_angle,
                      existing_scale=existing_scale, length=length)
    assert result["error"] is None, result
    report = result["report"]
    assert report["requested_angle"] == angle
    assert abs(angle_difference(report["applied_angle"], angle)) < 1e-8
    assert report["geometry_preserved"] is True
    assert report["stroke_widths_preserved"] is True
    assert report["verified"] is True
    assert result["after"] == result["before"]
    assert result["reads"] >= 2, "Verification must read a fresh native GradientColor."
    actual = result["color"]
    matrix = actual["matrix"]
    physical_length = actual["length"] * math.hypot(matrix["mValueA"], matrix["mValueB"])
    expected_span = 140 * abs(math.cos(math.radians(angle))) + 60 * abs(math.sin(math.radians(angle)))
    assert physical_length == pytest.approx(expected_span, abs=1e-8)
    # Reading the unchanged angle property alone would falsely report 0 degrees.
    assert actual["angle"] == 0
    if angle == 0 and existing_angle == 0 and existing_scale == 1:
        assert result["calls"] == [], "A matching native fill should avoid redundant transforms."
    else:
        assert len(result["calls"]) == 1


@pytest.mark.parametrize("angle", [-90, 180, 270, 405])
def test_gradient_directions_are_equivalent_modulo_full_turns(node, angle):
    result = run_host(node, angle=angle)
    assert result["error"] is None, result
    assert result["report"]["verified"] is True
    assert abs(angle_difference(result["report"]["applied_angle"], angle)) < 1e-8
    assert result["after"] == result["before"]


def test_ignored_native_transform_is_not_reported_as_verified(node):
    result = run_host(node, angle=90, host_behavior="ignore_all")
    assert result["error"] is None, result
    assert result["report"]["applied_angle"] == 0
    assert result["report"]["geometry_preserved"] is True
    assert result["report"]["verified"] is False
    assert result["after"] == result["before"]


def test_geometry_drift_is_not_reported_as_verified(node):
    result = run_host(node, angle=90, host_behavior="geometry_drift")
    assert result["error"] is None, result
    assert result["report"]["geometry_preserved"] is False
    assert result["report"]["verified"] is False
    assert result["after"]["points"] == result["before"]["points"]
    assert result["after"]["strokeWidth"] == result["before"]["strokeWidth"]


def test_ignored_gradient_scaling_is_not_reported_as_fully_verified(node):
    result = run_host(node, angle=90, host_behavior="ignore_scale")
    assert result["error"] is None, result
    assert abs(angle_difference(result["report"]["applied_angle"], 90)) < 1e-8
    assert result["after"] == result["before"]
    assert result["report"]["verified"] is False, "A correct direction alone does not prove the projected gradient span."


@pytest.mark.parametrize("typename", ["PathItem", "TextFrame"])
def test_native_unity_factor_preserves_thin_and_mixed_strokes(node, typename):
    result = run_host(node, angle=60, typename=typename, stroke_width=0.4228,
                      text_stroke_widths=[0.2, 1.5, 0])
    assert result["error"] is None, result
    assert result["report"]["verified"] is True
    assert result["report"]["stroke_widths_preserved"] is True
    assert result["report"]["stroke_widths_checked"] == (3 if typename == "TextFrame" else 1)
    assert result["report"]["stroke_widths_restored"] == 0
    assert result["after"] == result["before"]


@pytest.mark.parametrize("typename", ["PathItem", "TextFrame"])
def test_native_stroke_drift_is_restored_without_normalizing_mixed_text(node, typename):
    result = run_host(node, angle=60, typename=typename, stroke_width=0.4228,
                      text_stroke_widths=[0.2, 1.5, 0], host_behavior="stroke_drift")
    assert result["error"] is None, result
    assert result["report"]["verified"] is True
    assert result["report"]["stroke_widths_restored"] == (2 if typename == "TextFrame" else 1)
    assert result["after"] == result["before"]


@pytest.mark.parametrize("typename", ["PathItem", "TextFrame"])
def test_failed_native_stroke_restoration_prevents_verified_result(node, typename):
    result = run_host(node, angle=60, typename=typename, host_behavior="stroke_restore_ignored")
    assert result["error"] is None, result
    assert result["report"]["geometry_preserved"] is True
    assert result["report"]["stroke_widths_preserved"] is False
    assert result["report"]["verified"] is False


@pytest.mark.parametrize("typename", ["PathItem", "TextFrame"])
def test_native_transform_error_still_restores_existing_strokes(node, typename):
    result = run_host(node, angle=60, typename=typename, stroke_width=0.4228,
                      text_stroke_widths=[0.2, 1.5, 0], host_behavior="transform_throw_after_stroke_drift")
    assert "Native transform failed" in result["error"]["message"], result
    assert result["report"] is None
    assert result["after"] == result["before"]


def native_point(anchor, left=None, right=None):
    return {"anchor":anchor, "leftDirection":left or anchor, "rightDirection":right or anchor}


def test_narrow_triangle_uses_actual_projection_instead_of_its_bounding_rectangle(node):
    # A narrow triangular path regression: native Illustrator read back
    # 18.859518 pt after repainting; the former bbox target was134.180475 pt.
    points=[native_point([388.187716535433,-256.67262992125984]),
            native_point([516.0225826771655,-328.5796535433071]),
            native_point([372.208251968504,-267.32551181102366])]
    result=run_host(node,angle=60,path_points=points,
                    bounds=[372.208251968504,-256.67262992125984,516.0225826771655,-328.5796535433071])
    assert result["error"] is None,result
    assert result["report"]["requested_span_basis"]=="bezier_path_projection"
    assert result["report"]["requested_span_pt"]==pytest.approx(18.8595225271608,abs=1e-8)
    assert result["report"]["applied_span_pt"]==pytest.approx(18.8595225271608,abs=1e-8)
    assert result["report"]["verified"] is True
    assert result["after"]==result["before"]


@pytest.mark.parametrize("angle,points,bounds,expected",[
    (45,[native_point([0,0],right=[0,100]),native_point([100,0],left=[100,100])],
        [0,75,100,0],100),
    (90,[native_point([0,0],right=[100/3,100]),native_point([100,0],left=[200/3,100])],
        [0,75,100,0],75),
    (90,[native_point([0,0],right=[100/3,100]),native_point([100,0],left=[200/3,-100])],
        [0,50/math.sqrt(3),100,-50/math.sqrt(3)],100/math.sqrt(3)),
])
def test_bezier_span_evaluates_projected_curve_extrema_not_just_anchors_or_handles(node,angle,points,bounds,expected):
    result=run_host(node,angle=angle,path_points=points,bounds=bounds,closed=False)
    assert result["error"] is None,result
    assert result["report"]["requested_span_pt"]==pytest.approx(expected,abs=1e-8)
    assert result["report"]["verified"] is True
    assert result["after"]==result["before"]


def test_closed_path_includes_extrema_on_its_last_to_first_segment(node):
    points=[native_point([0,0],left=[0,-100]),native_point([100,0],right=[100,-100])]
    result=run_host(node,angle=90,path_points=points,bounds=[0,0,100,-75],closed=True)
    assert result["error"] is None,result
    assert result["report"]["requested_span_pt"]==pytest.approx(75,abs=1e-8)
    assert result["report"]["verified"] is True
    assert result["after"]==result["before"]


def test_curve_projection_is_invariant_under_large_document_translation(node):
    offset=1_000_000
    points=[native_point([offset,offset],right=[offset,offset+100]),
            native_point([offset+100,offset],left=[offset+100,offset+100])]
    result=run_host(node,angle=45,path_points=points,bounds=[offset,offset+75,offset+100,offset],closed=False)
    assert result["error"] is None,result
    assert result["report"]["requested_span_pt"]==pytest.approx(100,abs=1e-8)
    assert result["report"]["verified"] is True
    assert result["after"]==result["before"]


@pytest.mark.parametrize("params,code", [
    ({"angle":"90"}, "INVALID_ARGUMENT"),
    ({"angle":90, "missing_gradient":True}, "GRADIENT_REQUIRED"),
    ({"angle":90, "length":0}, "DEGENERATE_GRADIENT"),
    ({"angle":90, "bounds":[10,50,10,50]}, "DEGENERATE_GRADIENT"),
])
def test_invalid_or_degenerate_input_fails_before_any_transform(node, params, code):
    result = run_host(node, **params)
    assert result["error"]["code"] == code, result
    assert result["report"] is None
    assert result["calls"] == []
    assert result["after"] == result["before"]
