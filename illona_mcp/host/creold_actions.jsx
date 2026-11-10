/* Headless, explicitly targeted adaptations of the Creold Illustrator scripts.
 * Source: https://github.com/creold/illustrator-scripts (pinned by Illona's catalog).
 * See sourceFor below for the original file behind each action. ScriptUI,
 * preferences, file writes, implicit selection and menu-command execution are
 * intentionally absent from this adaptation. Geometry uses document points/Y up.
 *
 * MIT License -- Copyright (c) 2025 Sergey Osokin
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
(function (A) {
    var sourceFor = {
        reverse_gradient_colors: "ReverseGradientColor.jsx",
        distribute_gradient_stops: "DistributeGradientStops.jsx",
        remove_gradient_stops: "RemoveGradientStops.jsx",
        cycle_gradient_colors: "CycleGradientForward.jsx",
        stroke_color_from_fill: "StrokeColorFromFill.jsx",
        average_stroke_width: "AverageStrokesWidth.jsx",
        align_text_baselines: "AlignTextBaseline.jsx",
        round_coordinates: "RoundCoordinates.jsx",
        set_point_coordinates: "SetPointsCoordinates.jsx",
        transform_points: "TransformPoints.jsx",
        draw_artboard_rectangles: "DrawRectanglesByArtboards.jsx",
        change_opacity: "ChangeOpacity.jsx",
        average_colors: "AverageColors.jsx",
        trace_images: "BatchTrace.jsx"
    };
    var allowed = {
        reverse_gradient_colors: ["target"], distribute_gradient_stops: ["target"],
        remove_gradient_stops: ["target"], cycle_gradient_colors: ["target", "steps"],
        stroke_color_from_fill: ["shift_percent", "width_pt"], average_stroke_width: ["precision"],
        align_text_baselines: ["baseline_y_pt", "reference_uuid", "spacing_pt"],
        round_coordinates: ["step_pt", "reference", "include_stroke"],
        set_point_coordinates: ["point_indices", "x_pt", "y_pt", "relative"],
        transform_points: ["point_indices", "scale_x_pct", "scale_y_pct", "angle_deg", "dx_pt", "dy_pt", "origin_x_pt", "origin_y_pt"],
        draw_artboard_rectangles: ["artboard_indices", "bleed_pt", "layer_name", "fill", "stroke"],
        change_opacity: ["mode", "value"], average_colors: ["target", "average_method"],
        trace_images: ["preset", "ignore_white"]
    };
    function has(obj, key) { return obj.hasOwnProperty(key) && obj[key] !== undefined && obj[key] !== null; }
    function num(obj, key, fallback, min, max) {
        return has(obj, key) ? A.number(obj[key], key, min, max) : fallback;
    }
    function choice(obj, key, fallback, choices) {
        var v = has(obj, key) ? obj[key] : fallback;
        for (var i = 0; i < choices.length; i++) { if (v === choices[i]) { return v; } }
        A.fail("INVALID_ARGUMENT", "Invalid " + key + ".");
    }
    function boolOption(obj, key, fallback) {
        if (!has(obj, key)) { return fallback; }
        if (typeof obj[key] !== "boolean") { A.fail("INVALID_ARGUMENT", key + " must be boolean."); }
        return obj[key];
    }
    function finitePair(value, label) {
        if (!value || value.length !== 2) { A.fail("INVALID_GEOMETRY", "Invalid " + label + "."); }
        return [A.number(value[0], label, -10000000, 10000000), A.number(value[1], label, -10000000, 10000000)];
    }
    function id(item) { return String(item.uuid); }
    function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }
    function validateOptions(action, o) {
        A.object(o, "options");
        var fields = allowed[action], key, found, i;
        for (key in o) {
            if (!o.hasOwnProperty(key)) { continue; }
            found = false;
            for (i = 0; i < fields.length; i++) { if (key === fields[i]) { found = true; break; } }
            if (!found) { A.fail("INVALID_ARGUMENT", "Option " + key + " is not used by " + action + "."); }
        }
    }
    function resolve(document, ids, allowEmpty) {
        if (!(ids instanceof Array) || ids.length > 500 || (!allowEmpty && ids.length < 1)) {
            A.fail("INVALID_ARGUMENT", "object_ids must contain " + (allowEmpty ? "0" : "1") + " to 500 explicit UUIDs.");
        }
        var out = [], seen = {}, key, item;
        for (var i = 0; i < ids.length; i++) {
            key = A.string(ids[i], "object UUID", 200, false);
            if (seen["$" + key]) { A.fail("INVALID_ARGUMENT", "Duplicate object UUID: " + key); }
            item = A.findItem(document, key); A.assertEditable(item);
            seen["$" + key] = true; out.push(item);
        }
        return out;
    }
    function noSelectedAncestors(items) {
        var chosen = {}, parent, steps;
        for (var i = 0; i < items.length; i++) { chosen["$" + id(items[i])] = true; }
        for (i = 0; i < items.length; i++) {
            parent = items[i].parent; steps = 0;
            while (parent && parent.typename !== "Document" && steps++ < 100) {
                if (parent.typename !== "Layer" && chosen["$" + id(parent)]) {
                    A.fail("INVALID_ARGUMENT", "Select an ancestor or its child, rather than both, for object-level transformations.");
                }
                parent = parent.parent;
            }
        }
    }
    function leaves(items, types, skipped) {
        var out = [], seen = {};
        function walk(item, depth) {
            if (depth > 50) { A.fail("LIMIT_EXCEEDED", "Group nesting exceeds 50 levels."); }
            var key = "$" + id(item), i;
            if (seen[key]) { return; }
            seen[key] = true;
            if (item.typename === "GroupItem") {
                for (i = 0; i < item.pageItems.length; i++) { walk(item.pageItems[i], depth + 1); }
            } else if (item.typename === "CompoundPathItem") {
                for (i = 0; i < item.pathItems.length; i++) { walk(item.pathItems[i], depth + 1); }
            } else if (types[item.typename] && !(item.typename === "PathItem" && (item.guides || item.clipping))) {
                A.assertEditable(item); out.push(item);
                if (out.length > 5000) { A.fail("LIMIT_EXCEEDED", "More than 5000 applicable descendants."); }
            } else { skipped.push({id: id(item), reason: "Unsupported object type, guide, or clipping path"}); }
        }
        for (var j = 0; j < items.length; j++) { walk(items[j], 0); }
        return out;
    }
    function solidSpec(color) {
        var spec, base, i;
        if (!color) { A.fail("UNSUPPORTED_COLOR", "Missing color."); }
        if (color.typename === "RGBColor") { spec = {space: "rgb", values: [color.red, color.green, color.blue]}; }
        else if (color.typename === "CMYKColor") { spec = {space: "cmyk", values: [color.cyan, color.magenta, color.yellow, color.black]}; }
        else if (color.typename === "GrayColor") { spec = {space: "gray", values: [color.gray]}; }
        else if (color.typename === "SpotColor") {
            spec = solidSpec(color.spot.color);
            for (i = 0; i < spec.values.length; i++) {
                base = spec.space === "rgb" ? 255 : 0;
                spec.values[i] = base + (spec.values[i] - base) * color.tint / 100;
            }
        } else { A.fail("UNSUPPORTED_COLOR", "This action supports RGB, CMYK, Gray and spot-tint colors; encountered " + color.typename + "."); }
        for (i = 0; i < spec.values.length; i++) { A.number(spec.values[i], "color component", 0, spec.space === "rgb" ? 255 : 100); }
        return spec;
    }
    function nativeColor(spec) {
        if (spec.space === "gray") { var gray = new GrayColor(); gray.gray = spec.values[0]; return gray; }
        return A.color(spec);
    }
    function averageSpecs(specs, rms) {
        if (!specs.length) { A.fail("NO_APPLICABLE_OBJECTS", "No colors to average."); }
        var space = specs[0].space, sums = [], i, j, val;
        for (j = 0; j < specs[0].values.length; j++) { sums[j] = 0; }
        for (i = 0; i < specs.length; i++) {
            if (specs[i].space !== space) { A.fail("UNSUPPORTED_COLOR", "Averaged colors must share the same color space."); }
            for (j = 0; j < sums.length; j++) {
                val = specs[i].values[j]; sums[j] += rms && space === "rgb" ? val * val : val;
            }
        }
        for (j = 0; j < sums.length; j++) { sums[j] = rms && space === "rgb" ? Math.sqrt(sums[j] / specs.length) : sums[j] / specs.length; }
        return {space: space, values: sums};
    }
    function fillSpec(color, rms) {
        if (color.typename !== "GradientColor") { return solidSpec(color); }
        var stops = color.gradient.gradientStops, specs = [];
        if (stops.length < 2 || stops.length > 256) { A.fail("UNSUPPORTED_GRADIENT", "Only gradients with 2 to 256 stops are supported."); }
        for (var i = 0; i < stops.length; i++) { specs.push(solidSpec(stops[i].color)); }
        return averageSpecs(specs, rms === true);
    }
    /* HSL lightness adaptation from StrokeColorFromFill.jsx. Positive shifts
     * interpolate toward white; negative shifts toward black. */
    function shifted(spec, shift) {
        if (shift === 0) { return spec; }
        if (spec.space === "gray") { return {space: "gray", values: [clamp(spec.values[0] - shift, 0, 100)]}; }
        var rgb = spec.values;
        if (spec.space === "cmyk") { rgb = app.convertSampleColor(ImageColorSpace.CMYK, rgb, ImageColorSpace.RGB, ColorConvertPurpose.defaultpurpose); }
        var r = rgb[0] / 255, g = rgb[1] / 255, b = rgb[2] / 255;
        var max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, h = 0, s = 0, d = max - min;
        if (max !== min) {
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max === r) { h = (g - b) / d + (g < b ? 6 : 0); }
            else if (max === g) { h = (b - r) / d + 2; }
            else { h = (r - g) / d + 4; }
            h /= 6;
        }
        l = clamp(l + (shift < 0 ? l * shift / 100 : (1 - l) * shift / 100), 0, 1);
        function hue(p, q, t) {
            if (t < 0) { t += 1; } if (t > 1) { t -= 1; }
            if (t < 1 / 6) { return p + (q - p) * 6 * t; }
            if (t < 1 / 2) { return q; }
            if (t < 2 / 3) { return p + (q - p) * (2 / 3 - t) * 6; }
            return p;
        }
        if (s === 0) { rgb = [l * 255, l * 255, l * 255]; }
        else {
            var q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
            rgb = [hue(p, q, h + 1 / 3) * 255, hue(p, q, h) * 255, hue(p, q, h - 1 / 3) * 255];
        }
        if (spec.space === "cmyk") { rgb = app.convertSampleColor(ImageColorSpace.RGB, rgb, ImageColorSpace.CMYK, ColorConvertPurpose.defaultpurpose); }
        return {space: spec.space, values: rgb};
    }
    function gradientPlan(paths, o, action, skipped) {
        var target = choice(o, "target", "fill", ["fill", "stroke", "both"]), plans = [], i, j, c, stops, snap, prop, props;
        var steps = has(o, "steps") ? A.integer(o.steps, "steps", -256, 256) : 1;
        for (i = 0; i < paths.length; i++) {
            props = target === "both" ? ["fillColor", "strokeColor"] : [target === "fill" ? "fillColor" : "strokeColor"];
            for (var pi = 0; pi < props.length; pi++) {
                prop = props[pi]; c = paths[i][prop];
                if (!(prop === "fillColor" ? paths[i].filled : paths[i].stroked) || !c || c.typename !== "GradientColor") { continue; }
                stops = c.gradient.gradientStops;
                if (stops.length < 2 || stops.length > 256) { A.fail("UNSUPPORTED_GRADIENT", "Only gradients with 2 to 256 stops are supported."); }
                snap = [];
                for (j = 0; j < stops.length; j++) {
                    snap.push({color: stops[j].color, opacity: A.number(stops[j].opacity, "stop opacity", 0, 100),
                        position: A.number(stops[j].rampPoint, "stop position", 0, 100), midpoint: A.number(stops[j].midPoint, "stop midpoint", 13, 87)});
                }
                var original = snap.slice(0), n = snap.length;
                if (action === "reverse_gradient_colors") {
                    for (j = 0; j < n; j++) {
                        snap[j] = {color: original[n - 1 - j].color, opacity: original[n - 1 - j].opacity,
                            position: original[j].position, midpoint: original[j].midpoint};
                    }
                } else if (action === "distribute_gradient_stops") {
                    var first = snap[0].position, dist = snap[n - 1].position - first;
                    for (j = 0; j < n; j++) { snap[j].position = first + dist * j / (n - 1); }
                } else if (action === "remove_gradient_stops") { snap = [snap[0], snap[n - 1]]; }
                else {
                    var offset = ((steps % n) + n) % n;
                    for (j = 0; j < n; j++) {
                        snap[j] = {color: original[(j - offset + n) % n].color, opacity: original[j].opacity,
                            position: original[j].position, midpoint: original[j].midpoint};
                    }
                }
                plans.push({item: paths[i], prop: prop, paint: c, type: c.gradient.type, stops: snap});
            }
        }
        return plans;
    }
    function createIsolatedGradient(document, plan, index) {
        var gradient = document.gradients.add(), stops = plan.stops, i, gs;
        try {
            gradient.name = ("IC " + new Date().getTime() + " " + index).substr(0, 31);
            gradient.type = plan.type;
            function assign(stop, data) {
                stop.color = data.color; stop.opacity = data.opacity; stop.midPoint = data.midpoint;
                stop.rampPoint = data.position;
            }
            assign(gradient.gradientStops[0], stops[0]);
            assign(gradient.gradientStops[1], stops[stops.length - 1]);
            for (i = 1; i < stops.length - 1; i++) { gs = gradient.gradientStops.add(); assign(gs, stops[i]); }
            var paint = plan.paint;
            paint.gradient = gradient;
            plan.item[plan.prop] = paint;
            return String(gradient.name);
        } catch (err) {
            try { gradient.remove(); } catch (ignoredCleanup) {}
            throw err;
        }
    }
    function pointPlans(paths, o, action) {
        var refs = [], seen = {}, i, j, idx, pp, indices = has(o, "point_indices") ? o.point_indices : null;
        if (indices !== null) {
            if (!(indices instanceof Array) || indices.length < 1 || indices.length > 5000) { A.fail("INVALID_ARGUMENT", "point_indices must have 1 to 5000 indices."); }
            for (i = 0; i < indices.length; i++) {
                idx = A.integer(indices[i], "point index", 0, 99999);
                if (seen["$" + idx]) { A.fail("INVALID_ARGUMENT", "Duplicate point index."); } seen["$" + idx] = true;
            }
        }
        for (i = 0; i < paths.length; i++) {
            var count = indices === null ? paths[i].pathPoints.length : indices.length;
            for (j = 0; j < count; j++) {
                idx = indices === null ? j : indices[j];
                if (idx >= paths[i].pathPoints.length) { A.fail("INVALID_ARGUMENT", "Point index " + idx + " does not exist on " + id(paths[i]) + "."); }
                pp = paths[i].pathPoints[idx];
                refs.push({item: paths[i], point: pp, index: idx, anchor: finitePair(pp.anchor, "anchor"),
                    left: finitePair(pp.leftDirection, "left handle"), right: finitePair(pp.rightDirection, "right handle")});
                if (refs.length > 5000) { A.fail("LIMIT_EXCEEDED", "More than 5000 selected points."); }
            }
        }
        if (!refs.length) { A.fail("NO_APPLICABLE_OBJECTS", "No path points to transform."); }
        var x = num(o, "x_pt", null, -1000000, 1000000), y = num(o, "y_pt", null, -1000000, 1000000);
        var relative = boolOption(o, "relative", false), sx, sy, angle, dx, dy, ox, oy;
        if (action === "set_point_coordinates") {
            if (x === null && y === null) { A.fail("INVALID_ARGUMENT", "Specify x_pt or y_pt."); }
            for (i = 0; i < refs.length; i++) {
                dx = x === null ? 0 : (relative ? x : x - refs[i].anchor[0]);
                dy = y === null ? 0 : (relative ? y : y - refs[i].anchor[1]);
                refs[i].next = {anchor: [refs[i].anchor[0] + dx, refs[i].anchor[1] + dy],
                    left: [refs[i].left[0] + dx, refs[i].left[1] + dy], right: [refs[i].right[0] + dx, refs[i].right[1] + dy]};
            }
        } else {
            sx = num(o, "scale_x_pct", 100, -10000, 10000) / 100;
            sy = num(o, "scale_y_pct", 100, -10000, 10000) / 100;
            angle = num(o, "angle_deg", 0, -360000, 360000) * Math.PI / 180;
            dx = num(o, "dx_pt", 0, -1000000, 1000000); dy = num(o, "dy_pt", 0, -1000000, 1000000);
            if (has(o, "origin_x_pt") !== has(o, "origin_y_pt")) { A.fail("INVALID_ARGUMENT", "Supply both transform origin coordinates."); }
            if (has(o, "origin_x_pt")) {
                ox = A.number(o.origin_x_pt, "origin_x_pt", -1000000, 1000000); oy = A.number(o.origin_y_pt, "origin_y_pt", -1000000, 1000000);
            } else {
                var minX = refs[0].anchor[0], maxX = minX, minY = refs[0].anchor[1], maxY = minY;
                for (i = 1; i < refs.length; i++) {
                    minX = Math.min(minX, refs[i].anchor[0]); maxX = Math.max(maxX, refs[i].anchor[0]);
                    minY = Math.min(minY, refs[i].anchor[1]); maxY = Math.max(maxY, refs[i].anchor[1]);
                }
                ox = (minX + maxX) / 2; oy = (minY + maxY) / 2;
            }
            function transform(pair) {
                var px = (pair[0] - ox) * sx, py = (pair[1] - oy) * sy;
                return [ox + px * Math.cos(angle) - py * Math.sin(angle) + dx,
                    oy + px * Math.sin(angle) + py * Math.cos(angle) + dy];
            }
            for (i = 0; i < refs.length; i++) {
                refs[i].next = {anchor: transform(refs[i].anchor), left: transform(refs[i].left), right: transform(refs[i].right)};
            }
        }
        for (i = 0; i < refs.length; i++) {
            finitePair(refs[i].next.anchor, "resulting anchor"); finitePair(refs[i].next.left, "resulting left handle"); finitePair(refs[i].next.right, "resulting right handle");
        }
        return refs;
    }
    function bounds(item, includeStroke) {
        if (item.typename === "GroupItem" && item.clipped) {
            for (var i = 0; i < item.pageItems.length; i++) {
                var child = item.pageItems[i];
                if (child.clipping || (child.typename === "CompoundPathItem" && child.pathItems.length && child.pathItems[0].clipping)) {
                    return child.geometricBounds;
                }
            }
            A.fail("INVALID_GEOMETRY", "Cannot identify the clipping boundary of " + id(item) + ".");
        }
        return includeStroke ? item.visibleBounds : item.geometricBounds;
    }
    function traceImages(document, roots, o, result) {
        if (roots.length > 10) { A.fail("LIMIT_EXCEEDED", "trace_images accepts at most 10 explicit image UUIDs; use one image per call for complex photographs."); }
        var preset = has(o, "preset") ? A.string(o.preset, "preset", 200, false) : "16 Colors";
        var ignoreWhite = boolOption(o, "ignore_white", true), nativePresets = app.tracingPresetsList;
        var presetNames = [], presetFound = false, plans = [], i, j, source, bounds;
        for (i = 0; i < nativePresets.length; i++) {
            presetNames.push(String(nativePresets[i]));
            if (String(nativePresets[i]) === preset) { presetFound = true; }
        }
        if (!presetFound) { A.fail("UNKNOWN_TRACING_PRESET", "Unknown installed tracing preset: " + preset + ". Available: " + presetNames.join(", ")); }
        // Validate the complete input set before the first duplication or trace.
        for (i = 0; i < roots.length; i++) {
            source = roots[i];
            if (source.typename !== "PlacedItem" && source.typename !== "RasterItem") {
                A.fail("UNSUPPORTED_IMAGE_TYPE", "trace_images accepts only explicit PlacedItem or RasterItem UUIDs.");
            }
            if (source.typename === "PlacedItem" && (!source.file || !source.file.exists)) {
                A.fail("MISSING_IMAGE_FILE", "The placed image file is missing for " + id(source) + ".");
            }
            bounds = source.geometricBounds.slice();
            for (j = 0; j < 4; j++) { A.number(bounds[j], "image bounds", -10000000, 10000000); }
            if (!(bounds[2] > bounds[0]) || !(bounds[1] > bounds[3])) { A.fail("INVALID_GEOMETRY", "Image bounds must have positive width and height."); }
            plans.push({item: source, id: id(source), name: String(source.name || "Traced image"), bounds: bounds});
        }
        function present(uuid) {
            for (var pi = 0; pi < document.pageItems.length; pi++) {
                try { if (id(document.pageItems[pi]) === uuid) { return true; } } catch (ignoredInvalidItem) {}
            }
            return false;
        }
        function discard(artifact, messages) {
            if (!artifact) { return; }
            var uuid = null;
            try { uuid = id(artifact); } catch (ignoredConsumedArtifact) { return; }
            if (!present(uuid)) { return; }
            try { artifact.remove(); }
            catch (removeError) { messages.push("Could not remove temporary artifact " + uuid + ": " + String(removeError.message || removeError)); }
            if (present(uuid)) { messages.push("Temporary artifact remains: " + uuid); }
        }
        function inventory(root) {
            var counts = {path_count: 0, compound_path_count: 0, group_count: 0,
                raster_count: 0, placed_count: 0, plugin_count: 0, other_count: 0, node_count: 0};
            var seen = {};
            function visit(item, depth) {
                if (depth > 100 || counts.node_count >= 200000) { A.fail("TRACE_RESULT_TOO_LARGE", "Trace inspection exceeded its bounded node/depth limit."); }
                var key = "$" + id(item), k;
                if (seen[key]) { return; } seen[key] = true; counts.node_count++;
                if (item.typename === "GroupItem") {
                    counts.group_count++;
                    for (k = 0; k < item.pageItems.length; k++) { visit(item.pageItems[k], depth + 1); }
                } else if (item.typename === "CompoundPathItem") {
                    counts.compound_path_count++;
                    for (k = 0; k < item.pathItems.length; k++) { visit(item.pathItems[k], depth + 1); }
                } else if (item.typename === "PathItem") { counts.path_count++; }
                else if (item.typename === "RasterItem") { counts.raster_count++; }
                else if (item.typename === "PlacedItem") { counts.placed_count++; }
                else if (item.typename === "PluginItem") { counts.plugin_count++; }
                else { counts.other_count++; }
            }
            visit(root, 0); return counts;
        }
        result.preset = preset; result.ignore_white = ignoreWhite; result.expanded = true;
        result.selection_preserved = false; result.replaced = []; result.traces = [];
        result.warnings.push("Tracing replaces targeted images with new vector group UUIDs. White removal may crop bounds; inspect the result before scaling or print delivery.");
        var previousDocument = null, previousInteraction = app.userInteractionLevel;
        try { previousDocument = app.activeDocument; } catch (ignoredNoActiveDocument) {}
        try {
            app.activeDocument = document;
            app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
            for (i = 0; i < plans.length; i++) {
                var plan = plans[i], copy = null, plugin = null, expanded = null, createdInfo = null, traceInfo = null;
                var committed = false, cleanupMessages = [];
                try {
                    // Keep the source until the expanded copy is proved to contain
                    // only editable paths, so failed tracing can discard its work.
                    copy = plan.item.duplicate(plan.item, ElementPlacement.PLACEBEFORE);
                    plugin = copy.trace();
                    var tracing = plugin.tracing, options = tracing.tracingOptions;
                    if (options.loadFromPreset(preset) === false) { A.fail("TRACE_PRESET_LOAD_FAILED", "Illustrator did not load the installed tracing preset."); }
                    options.ignoreWhite = ignoreWhite; options.livePaintOutput = false;
                    if (options.ignoreWhite !== ignoreWhite) { A.fail("TRACE_OPTION_NOT_APPLIED", "Illustrator did not retain ignore_white."); }
                    // Native tracing is asynchronous. Adobe requires redraw before
                    // reading its result or expanding the PluginItem.
                    app.redraw();
                    expanded = tracing.expandTracing(false);
                    if (!expanded || expanded.typename !== "GroupItem") { A.fail("TRACE_NOT_EXPANDED", "Native tracing did not expand to an editable GroupItem."); }
                    expanded.name = ("Creold vector / " + plan.name).substr(0, 200);
                    var counts = inventory(expanded);
                    if (!counts.path_count || counts.raster_count || counts.placed_count || counts.plugin_count || counts.other_count) {
                        A.fail("TRACE_NOT_VECTOR_ONLY", "Expanded trace must contain paths only; counts: paths=" + counts.path_count +
                            ", raster=" + counts.raster_count + ", placed=" + counts.placed_count + ", plugin=" + counts.plugin_count + ", other=" + counts.other_count + ".");
                    }
                    var afterBounds = expanded.geometricBounds.slice(), sameBounds = true;
                    for (j = 0; j < 4; j++) {
                        A.number(afterBounds[j], "expanded bounds", -10000000, 10000000);
                        if (Math.abs(afterBounds[j] - plan.bounds[j]) > 0.01) { sameBounds = false; }
                    }
                    createdInfo = A.itemInfo(expanded);
                    traceInfo = {source_id: plan.id, created_id: id(expanded), preset: preset, ignore_white: ignoreWhite,
                        input_bounds_pt: plan.bounds, output_bounds_pt: afterBounds, bounds_preserved: sameBounds,
                        vector_only: true, counts: counts};
                    plan.item.remove();
                    if (present(plan.id)) { A.fail("TRACE_SOURCE_REMAINS", "The original source image remains after replacement."); }
                    committed = true;
                } catch (traceError) {
                    // A source remove may throw after committing. Keep a verified
                    // expanded group if it is now the only surviving artwork.
                    if (expanded && createdInfo && traceInfo && !present(plan.id)) { committed = true; }
                    if (!committed) { discard(expanded, cleanupMessages); discard(plugin, cleanupMessages); discard(copy, cleanupMessages); }
                    result.errors.push({object_id: plan.id, index: i, code: traceError.illonaCode || "TRACE_ERROR",
                        message: String(traceError.message || traceError), source_preserved: present(plan.id),
                        created_id: committed && traceInfo ? traceInfo.created_id : null, cleanup_errors: cleanupMessages});
                }
                if (committed) {
                    result.created.push(createdInfo); result.traces.push(traceInfo);
                    result.replaced.push({source_id: plan.id, created_id: traceInfo.created_id});
                }
            }
        } finally {
            try { app.userInteractionLevel = previousInteraction; } catch (ignoredInteractionRestore) {}
            if (previousDocument && A.isOpen(previousDocument)) {
                try { app.activeDocument = previousDocument; } catch (ignoredDocumentRestore) {}
            }
        }
        result.created_count = result.created.length; result.replaced_count = result.replaced.length;
        result.success = result.errors.length === 0; result.partial = !result.success;
        return result;
    }
    A.ops.creold_action = function (p) {
        var document = A.doc(p.document_id), action = A.string(p.action, "action", 100, false);
        if (!sourceFor.hasOwnProperty(action)) { A.fail("INVALID_ARGUMENT", "Unknown Creold action."); }
        var o = p.options || {}; validateOptions(action, o);
        var roots = resolve(document, p.object_ids, action === "draw_artboard_rectangles");
        var skipped = [], warnings = [], plans = [], paths, i, j, item, b, value, target, color, method;
        var result = {success: true, document_id: p.document_id, action: action, source_script: sourceFor[action],
            coordinates: "native document points, Y up", changed_count: 0, changed: [], created: [], skipped: skipped,
            warnings: warnings, errors: [], selection_preserved: true};
        if (action === "trace_images") { return traceImages(document, roots, o, result); }
        var mode;
        if (/^(reverse_gradient_colors|distribute_gradient_stops|remove_gradient_stops|cycle_gradient_colors)$/.test(action)) {
            paths = leaves(roots, {PathItem: true}, skipped); plans = gradientPlan(paths, o, action, skipped); mode = "gradient";
            warnings.push("Edited gradients are isolated copies; unselected artwork sharing the original gradient is preserved.");
        } else if (action === "stroke_color_from_fill") {
            paths = leaves(roots, {PathItem: true}, skipped);
            var shift = num(o, "shift_percent", 0, -100, 100), width = num(o, "width_pt", null, 0.01, 1000);
            for (i = 0; i < paths.length; i++) {
                if (!paths[i].filled) { skipped.push({id: id(paths[i]), reason: "No fill"}); continue; }
                color = nativeColor(shifted(fillSpec(paths[i].fillColor), shift));
                plans.push({item: paths[i], color: color, width: width === null ? (paths[i].stroked ? A.number(paths[i].strokeWidth, "existing stroke width", 0.01, 1000) : 1) : width});
            }
            mode = "stroke";
        } else if (action === "average_stroke_width") {
            paths = leaves(roots, {PathItem: true, TextFrame: true}, skipped);
            var total = 0, precision = has(o, "precision") ? A.integer(o.precision, "precision", 0, 4) : 2;
            for (i = 0; i < paths.length; i++) {
                item = paths[i];
                if (item.typename === "TextFrame") {
                    var attrs = item.textRange.characterAttributes;
                    if (!attrs.strokeColor || attrs.strokeColor.typename === "NoColor") { continue; }
                    if (typeof attrs.strokeWeight === "number" && attrs.strokeWeight <= 0) { continue; }
                    value = A.number(attrs.strokeWeight, "text stroke weight", 0.0001, 1000);
                } else { if (!item.stroked || item.strokeWidth <= 0) { continue; } value = A.number(item.strokeWidth, "stroke width", 0.0001, 1000); }
                total += value; plans.push({item: item});
            }
            if (plans.length) {
                value = Math.round(total / plans.length * Math.pow(10, precision)) / Math.pow(10, precision);
                if (value <= 0) { A.fail("INVALID_ARGUMENT", "Rounded average stroke width must be positive; increase precision."); }
                result.average_width_pt = value;
                for (i = 0; i < plans.length; i++) { plans[i].width = value; }
            }
            warnings.push("A selected text frame receives one common stroke weight; mixed stroke weights are normalized."); mode = "width";
        } else if (action === "align_text_baselines") {
            paths = leaves(roots, {TextFrame: true}, skipped);
            if (has(o, "baseline_y_pt") && has(o, "reference_uuid")) { A.fail("INVALID_ARGUMENT", "Use baseline_y_pt or reference_uuid."); }
            var baseline = num(o, "baseline_y_pt", null, -1000000, 1000000), spacing = num(o, "spacing_pt", 0, 0, 10000), reference = null;
            if (has(o, "reference_uuid")) { A.string(o.reference_uuid, "reference_uuid", 200, false); }
            for (i = 0; i < paths.length; i++) {
                if (paths[i].kind !== TextType.POINTTEXT) { A.fail("UNSUPPORTED_TEXT", "Baseline actions require point text; area/path text is not supported."); }
                b = finitePair(paths[i].anchor, "text anchor");
                if (has(o, "reference_uuid") && id(paths[i]) === o.reference_uuid) { reference = b[1]; }
            }
            if (has(o, "reference_uuid") && reference === null) { A.fail("INVALID_ARGUMENT", "reference_uuid must identify a targeted point-text frame."); }
            if (baseline === null && paths.length) { baseline = reference === null ? paths[0].anchor[1] : reference; }
            for (i = 0; i < paths.length; i++) {
                var destinationBaseline = A.number(baseline - i * spacing, "resulting baseline", -10000000, 10000000);
                plans.push({item: paths[i], dx: 0, dy: destinationBaseline - paths[i].anchor[1]});
            }
            result.baseline_y_pt = baseline; mode = "translate";
        } else if (action === "round_coordinates") {
            noSelectedAncestors(roots);
            var step = num(o, "step_pt", 1, 0.000001, 10000), ref = choice(o, "reference", "center", ["center", "top_left"]), include = boolOption(o, "include_stroke", false), x, y;
            for (i = 0; i < roots.length; i++) {
                b = bounds(roots[i], include);
                if (!b || b.length !== 4) { A.fail("INVALID_GEOMETRY", "Object bounds are unavailable."); }
                for (j = 0; j < 4; j++) { A.number(b[j], "bounds", -10000000, 10000000); }
                x = ref === "center" ? (b[0] + b[2]) / 2 : b[0]; y = ref === "center" ? (b[1] + b[3]) / 2 : b[1];
                plans.push({item: roots[i], dx: Math.round(x / step) * step - x, dy: Math.round(y / step) * step - y});
            }
            mode = "translate";
        } else if (action === "set_point_coordinates" || action === "transform_points") {
            paths = leaves(roots, {PathItem: true}, skipped); plans = pointPlans(paths, o, action); mode = "points";
        } else if (action === "draw_artboard_rectangles") {
            if (roots.length) { A.fail("INVALID_ARGUMENT", "draw_artboard_rectangles requires object_ids: []; use artboard_indices."); }
            var indices = o.artboard_indices, seen = {}, bleed = num(o, "bleed_pt", 0, 0, 10000);
            if (!(indices instanceof Array) || indices.length < 1 || indices.length > 100) { A.fail("INVALID_ARGUMENT", "artboard_indices must contain 1 to 100 indices."); }
            var layerName = has(o, "layer_name") ? A.string(o.layer_name, "layer_name", 200, false) : "Creold / Artboard rectangles";
            var existing = A.existingLayer(document, layerName);
            if (existing && (existing.locked || !existing.visible)) { A.fail("LAYER_NOT_EDITABLE", "The target rectangle layer is locked or hidden."); }
            var fill = has(o, "fill") ? A.color(o.fill) : null, stroke = null, strokeWidth = 1;
            if (has(o, "stroke")) {
                A.object(o.stroke, "stroke"); stroke = A.color(o.stroke.color); strokeWidth = A.number(o.stroke.width_pt, "stroke width_pt", 0.01, 1000);
            } else if (!fill) { stroke = A.color("#182C30"); }
            for (i = 0; i < indices.length; i++) {
                var index = A.integer(indices[i], "artboard index", 0, document.artboards.length - 1);
                if (seen["$" + index]) { A.fail("INVALID_ARGUMENT", "Duplicate artboard index."); } seen["$" + index] = true;
                b = A.artboard(document, index).artboardRect;
                for (j = 0; j < 4; j++) { A.number(b[j], "artboard bounds", -10000000, 10000000); }
                var rw = b[2] - b[0] + 2 * bleed, rh = b[1] - b[3] + 2 * bleed;
                A.number(rw, "rectangle width", 0.0001, 1000000); A.number(rh, "rectangle height", 0.0001, 1000000);
                plans.push({index: index, left: b[0] - bleed, top: b[1] + bleed, width: rw, height: rh});
            }
            mode = "rectangles";
        } else if (action === "change_opacity") {
            noSelectedAncestors(roots);
            var opacityMode = choice(o, "mode", "absolute", ["absolute", "delta", "multiply"]);
            if (!has(o, "value")) { A.fail("INVALID_ARGUMENT", "change_opacity requires value."); }
            var opacityValue = A.number(o.value, "value", opacityMode === "delta" ? -100 : 0, 100);
            result.opacity_mode = opacityMode; result.requested_value = opacityValue;
            for (i = 0; i < roots.length; i++) {
                var previous = A.number(roots[i].opacity, "existing opacity", 0, 100);
                // ExtendScript evaluates this nested ternary differently from V8.
                // Keep the modes explicit and verify each native setter below.
                var opacityNext = opacityValue;
                if (opacityMode === "delta") { opacityNext = previous + opacityValue; }
                else if (opacityMode === "multiply") { opacityNext = previous * opacityValue; }
                plans.push({item: roots[i], value: clamp(opacityNext, 0, 100)});
            }
            mode = "opacity";
        } else if (action === "average_colors") {
            target = choice(o, "target", "fill", ["fill", "stroke"]); method = choice(o, "average_method", "arithmetic", ["arithmetic", "rms"]);
            paths = leaves(roots, {PathItem: true}, skipped); var specs = [], property = target === "fill" ? "fillColor" : "strokeColor";
            for (i = 0; i < paths.length; i++) {
                if (!(target === "fill" ? paths[i].filled : paths[i].stroked)) { skipped.push({id: id(paths[i]), reason: "No " + target}); continue; }
                specs.push(fillSpec(paths[i][property], method === "rms")); plans.push({item: paths[i], prop: property});
            }
            color = nativeColor(averageSpecs(specs, method === "rms")); result.average_color = A.describe(color); mode = "color";
        }
        if (!plans.length) { A.fail("NO_APPLICABLE_OBJECTS", "No applicable editable objects for " + action + "."); }
        /* All document/object/option/geometry/color validation above precedes
         * the first mutation. Native failures below report partial results. */
        var changed = {}, newLayer = null;
        if (mode === "rectangles") { newLayer = A.layer(document, layerName); }
        for (i = 0; i < plans.length; i++) {
            var plan = plans[i], created = null;
            try {
                if (mode === "gradient") {
                    var gradientName = createIsolatedGradient(document, plan, i);
                    if (!result.gradients) { result.gradients = []; }
                    result.gradients.push({object_id: id(plan.item), property: plan.prop, name: gradientName, stop_count: plan.stops.length});
                } else if (mode === "stroke") {
                    plan.item.strokeColor = plan.color; plan.item.strokeWidth = plan.width; plan.item.stroked = true;
                } else if (mode === "width") {
                    if (plan.item.typename === "TextFrame") { plan.item.textRange.characterAttributes.strokeWeight = plan.width; }
                    else { plan.item.strokeWidth = plan.width; }
                } else if (mode === "translate") { plan.item.translate(plan.dx, plan.dy); }
                else if (mode === "points") {
                    plan.point.anchor = plan.next.anchor; plan.point.leftDirection = plan.next.left; plan.point.rightDirection = plan.next.right;
                } else if (mode === "opacity") {
                    plan.item.opacity = plan.value;
                    if (Math.abs(plan.item.opacity - plan.value) > 0.001) {
                        A.fail("NATIVE_VALUE_MISMATCH", "Opacity requested " + plan.value + ", read back " + plan.item.opacity + ".");
                    }
                }
                else if (mode === "color") { plan.item[plan.prop] = color; }
                else if (mode === "rectangles") {
                    created = newLayer.pathItems.rectangle(plan.top, plan.left, plan.width, plan.height);
                    created.name = "Creold artboard " + (plan.index + 1); created.filled = false; created.stroked = false;
                    if (fill) { created.fillColor = fill; created.filled = true; }
                    if (stroke) { created.strokeColor = stroke; created.strokeWidth = strokeWidth; created.stroked = true; }
                    created.zOrder(ZOrderMethod.SENDTOBACK); result.created.push(A.itemInfo(created));
                }
                if (mode !== "rectangles") { changed["$" + id(plan.item)] = plan.item; }
            } catch (err) {
                if (created) { try { created.remove(); } catch (ignoredRemove) {} }
                result.errors.push({object_id: plan.item ? id(plan.item) : null, index: i, message: String(err.message || err)});
            }
        }
        for (var changedKey in changed) { if (changed.hasOwnProperty(changedKey)) { result.changed.push(A.itemInfo(changed[changedKey])); } }
        result.changed_count = result.changed.length; result.created_count = result.created.length;
        result.success = result.errors.length === 0;
        /* A native property setter can throw after changing part of an item. */
        result.partial = !result.success;
        if (mode === "points") { result.point_count = plans.length; }
        return result;
    };
})(Illona);
