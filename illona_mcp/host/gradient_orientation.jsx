/* Native gradient direction, without moving or rotating artwork. ES3. */
(function (A) {
    A.orientGradientFill = function (item, angle) {
        A.number(angle, "gradient angle");
        function wrap(value) {
            value = ((value + 180) % 360 + 360) % 360 - 180;
            return value;
        }
        function fill(target) {
            return target.typename === "TextFrame" ? target.textRange.characterAttributes.fillColor : target.fillColor;
        }
        function pathSpan(target, radians) {
            var points = target.pathPoints, count = points.length, i;
            if (!count) { return 0; }
            var origin = points[0].anchor, ux = Math.cos(radians), uy = Math.sin(radians);
            var low = 0, high = 0;
            function project(point) {
                // Work relative to an anchor to avoid loss of precision on
                // artboards a long way from the native document origin.
                return (A.number(point[0], "path X") - origin[0]) * ux +
                    (A.number(point[1], "path Y") - origin[1]) * uy;
            }
            function include(value) { low = Math.min(low, value); high = Math.max(high, value); }
            function segment(p0, p1, p2, p3) {
                var a = -p0 + 3 * p1 - 3 * p2 + p3;
                var b = 3 * p0 - 6 * p1 + 3 * p2;
                var c = -3 * p0 + 3 * p1;
                var qa = 3 * a, qb = 2 * b, qc = c;
                var epsilon = 0.0000000001 * Math.max(1, Math.abs(qa), Math.abs(qb), Math.abs(qc));
                function at(t) {
                    if (!(t > 0 && t < 1)) { return; }
                    var u = 1 - t;
                    include(u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3);
                }
                include(p0); include(p3);
                if (Math.abs(qa) <= epsilon) {
                    if (Math.abs(qb) > epsilon) { at(-qc / qb); }
                    return;
                }
                var discriminant = qb * qb - 4 * qa * qc;
                if (discriminant < 0) {
                    if (discriminant < -0.000000000001 * Math.max(1, qb * qb, Math.abs(4 * qa * qc))) { return; }
                    discriminant = 0;
                }
                var root = Math.sqrt(discriminant);
                var q = -0.5 * (qb + (qb < 0 ? -root : root));
                if (Math.abs(q) > epsilon) { at(q / qa); at(qc / q); }
                else { at(-qb / (2 * qa)); }
            }
            for (i = 0; i < count; i++) { include(project(points[i].anchor)); }
            var segments = target.closed ? count : count - 1;
            for (i = 0; i < segments; i++) {
                var next = (i + 1) % count;
                segment(project(points[i].anchor), project(points[i].rightDirection),
                    project(points[next].leftDirection), project(points[next].anchor));
            }
            return high - low;
        }
        function strokeState(target) {
            var states = [], count, i;
            function remember(holder, key) {
                var width = holder[key];
                if (typeof width !== "number" || !isFinite(width) || width < 0) {
                    A.fail("STROKE_READBACK_UNAVAILABLE", "Cannot verify the existing native stroke width.");
                }
                states.push({holder: holder, key: key, width: width});
            }
            if (target.typename === "PathItem") {
                remember(target, "strokeWidth");
            } else if (target.typename === "TextFrame") {
                count = target.characters ? target.characters.length : 0;
                if (count > 100000) { A.fail("TEXT_TOO_LARGE", "Gradient stroke verification supports at most 100000 characters."); }
                // A frame may contain mixed stroke weights. A range-level setter
                // would normalize them, so retain the individual native holders.
                if (count) {
                    for (i = 0; i < count; i++) { remember(target.characters[i].characterAttributes, "strokeWeight"); }
                } else { remember(target.textRange.characterAttributes, "strokeWeight"); }
            }
            return states;
        }
        function restoreStrokes(states) {
            var preserved = true, restored = 0, i, state, actual;
            for (i = 0; i < states.length; i++) {
                state = states[i];
                try {
                    actual = state.holder[state.key];
                    if (typeof actual !== "number" || !isFinite(actual) || Math.abs(actual - state.width) > 0.000001) {
                        state.holder[state.key] = state.width; restored++;
                    }
                    actual = state.holder[state.key];
                    if (typeof actual !== "number" || !isFinite(actual) || Math.abs(actual - state.width) > 0.000001) { preserved = false; }
                } catch (ignoredStrokeRestore) { preserved = false; }
            }
            return {preserved: preserved, restored: restored};
        }
        var before = item.geometricBounds.slice(), color = fill(item);
        if (!color || color.typename !== "GradientColor") {
            A.fail("GRADIENT_REQUIRED", "Orientation requires a native gradient fill.");
        }
        var matrix = color.matrix;
        var oldAngle = Math.atan2(matrix.mValueB, matrix.mValueA) * 180 / Math.PI;
        var oldScale = Math.sqrt(matrix.mValueA * matrix.mValueA + matrix.mValueB * matrix.mValueB);
        var length = color.length * oldScale;
        var radians = angle * Math.PI / 180;
        var span, spanBasis;
        if (item.typename === "PathItem") {
            span = pathSpan(item, radians); spanBasis = "bezier_path_projection";
        } else if (item.typename === "TextFrame") {
            span = Math.abs((before[2] - before[0]) * Math.cos(radians)) + Math.abs((before[1] - before[3]) * Math.sin(radians));
            spanBasis = "text_geometric_bounds";
        } else { A.fail("UNSUPPORTED_GRADIENT_TARGET", "Gradient direction supports native paths and text frames."); }
        if (!(length > 0) || !(span > 0)) { A.fail("DEGENERATE_GRADIENT", "Gradient length and artwork bounds must be positive."); }
        var strokes = strokeState(item), strokeResult = {preserved: true, restored: 0};
        var delta = wrap(angle - oldAngle), scale = span / length;
        if (Math.abs(delta) > 0.00001 || Math.abs(scale - 1) > 0.00001) {
            var transform = app.getRotationMatrix(delta);
            transform.mValueA *= scale; transform.mValueB *= scale;
            transform.mValueC *= scale; transform.mValueD *= scale;
            /* The position flag is false: only the fill gradient is transformed.
             * Native Illustrator ignores assignments to GradientColor.angle and
             * can discard its matrix/origin setters. In native Illustrator 30.8.2,
             * changeLineWidths is a factor here: 100 enlarged a 0.4228 pt stroke
             * to 42.28 pt. Use unity and independently restore/read back widths. */
            try {
                item.transform(transform, false, false, true, false, 1, Transformation.CENTER);
            } finally { strokeResult = restoreStrokes(strokes); }
        }
        var after = item.geometricBounds, actualColor = fill(item), actual = actualColor.matrix;
        var applied = Math.atan2(actual.mValueB, actual.mValueA) * 180 / Math.PI;
        var preserved = true;
        for (var i = 0; i < 4; i++) { if (Math.abs(before[i] - after[i]) > 0.01) { preserved = false; } }
        var appliedSpan = actualColor.length * Math.sqrt(actual.mValueA * actual.mValueA + actual.mValueB * actual.mValueB);
        var spanVerified = Math.abs(appliedSpan - span) <= Math.max(0.01, span * 0.001);
        var verified = preserved && strokeResult.preserved && spanVerified && Math.abs(wrap(applied - angle)) < 0.05;
        return {id: String(item.uuid), requested_angle: angle, applied_angle: applied,
            geometry_preserved: preserved, requested_span_pt: span, applied_span_pt: appliedSpan,
            requested_span_basis: spanBasis,
            stroke_widths_preserved: strokeResult.preserved, stroke_widths_checked: strokes.length,
            stroke_widths_restored: strokeResult.restored,
            span_verified: spanVerified, verified: verified, method: "native_fill_transform",
            visual_review_required: true};
    };
})(Illona);
