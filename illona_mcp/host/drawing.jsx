/* Native editable drawing operations; no arbitrary script evaluation. */
(function (A) {
    A.imageAsset = function (element) {
        A.string(element.path, "image.path", 4096, false);
        if (element.path.charAt(0) !== "/" || element.path.indexOf("\u0000") !== -1 || !/\.(jpe?g|png)$/i.test(element.path)) {
            A.fail("INVALID_IMAGE_PATH", "Images require an absolute local JPG, JPEG or PNG path.");
        }
        var file = new File(element.path), bytes = "", width = 0, height = 0;
        if (!file.exists) { A.fail("IMAGE_NOT_FOUND", "Image file does not exist: " + element.path); }
        if (file.length <= 0 || file.length > 104857600) { A.fail("INVALID_IMAGE", "Image must contain 1 byte to 100 MiB."); }
        try {
            file.encoding = "BINARY";
            if (!file.open("r")) { A.fail("IMAGE_NOT_READABLE", "Cannot read image: " + element.path); }
            bytes = file.read(Math.min(file.length, 1048576));
        } finally { try { file.close(); } catch (ignoredClose) {} }
        function readByte(at) { return bytes.charCodeAt(at) & 255; }
        function big32(at) { return readByte(at) * 16777216 + readByte(at + 1) * 65536 + readByte(at + 2) * 256 + readByte(at + 3); }
        if (/\.png$/i.test(element.path) && bytes.length >= 24 && readByte(0) === 137 && bytes.substr(1, 7) === "PNG\r\n\u001a\n" && bytes.substr(12, 4) === "IHDR") {
            width = big32(16); height = big32(20);
        } else if (/\.jpe?g$/i.test(element.path) && bytes.length >= 4 && readByte(0) === 255 && readByte(1) === 216) {
            var at = 2, marker, size;
            while (at + 8 < bytes.length) {
                if (readByte(at) !== 255) { break; }
                while (at < bytes.length && readByte(at) === 255) { at++; }
                marker = readByte(at++);
                if (marker === 217 || marker === 218) { break; }
                if (marker === 1 || (marker >= 208 && marker <= 215)) { continue; }
                size = readByte(at) * 256 + readByte(at + 1);
                if (size < 2 || at + size > bytes.length) { break; }
                if ((marker >= 192 && marker <= 195) || (marker >= 197 && marker <= 199) || (marker >= 201 && marker <= 203) || (marker >= 205 && marker <= 207)) {
                    height = readByte(at + 3) * 256 + readByte(at + 4); width = readByte(at + 5) * 256 + readByte(at + 6); break;
                }
                at += size;
            }
        }
        if (!width || !height || width > 60000 || height > 60000 || width * height > 100000000) {
            A.fail("INVALID_IMAGE", "Image header must describe a supported PNG/JPEG with positive dimensions, at most 60000 pixels per side and 100 megapixels.");
        }
        return file;
    };
    A.validateStyle = function (element, text) {
        if (element.name !== undefined) { A.string(element.name, "name", 200, true); }
        if (element.fill !== undefined && element.fill !== null) { A.color(element.fill); }
        if (element.color !== undefined && element.color !== null) { A.color(element.color); }
        if (element.stroke !== undefined && element.stroke !== null) { A.color(element.stroke); }
        if (element.width_pt !== undefined) { A.number(element.width_pt, "width_pt", 0, 1000); }
        if (element.stroke_width_pt !== undefined) { A.number(element.stroke_width_pt, "stroke_width_pt", 0, 1000); }
        if (element.opacity !== undefined) { A.number(element.opacity, "opacity", 0, 100); }
        if (text) {
            if (element.font !== undefined) { A.font(element.font); }
            if (element.size_pt !== undefined) { A.number(element.size_pt, "size_pt", 0.1, 1296); }
            if (element.leading_pt !== undefined) { A.number(element.leading_pt, "leading_pt", 0.1, 1296); }
            if (element.tracking !== undefined) { A.number(element.tracking, "tracking", -1000, 10000); }
        }
    };
    A.validateElement = function (document, params, element) {
        A.object(element, "element");
        var type = element.type;
        if (type !== "rect" && type !== "ellipse" && type !== "path" && type !== "text" && type !== "image") { A.fail("INVALID_ARGUMENT", "element.type must be rect, ellipse, path, text, or image."); }
        A.validateStyle(element, type === "text");
        if (type === "rect" || type === "ellipse" || type === "image") {
            A.point(document, params, A.number(element.x, "x"), A.number(element.y, "y"));
            A.number(A.length(A.number(element.width, "width", 0.001), params.units), "width in points", 0.001, 16348);
            A.number(A.length(A.number(element.height, "height", 0.001), params.units), "height in points", 0.001, 16348);
            if (type === "image") {
                if (element.fit !== undefined && element.fit !== "contain" && element.fit !== "cover") { A.fail("INVALID_ARGUMENT", "image.fit must be contain or cover."); }
                if (element.embed !== undefined && typeof element.embed !== "boolean") { A.fail("INVALID_ARGUMENT", "image.embed must be boolean."); }
                return A.imageAsset(element);
            }
        } else if (type === "text") {
            A.point(document, params, A.number(element.x, "x"), A.number(element.y, "y"));
            A.string(element.text, "text", 100000, true);
            if ((element.width === undefined) !== (element.height === undefined)) { A.fail("INVALID_ARGUMENT", "Area text requires both width and height."); }
            if (element.width !== undefined) {
                A.number(A.length(A.number(element.width, "width", 0.001), params.units), "width in points", 0.001, 16348);
                A.number(A.length(A.number(element.height, "height", 0.001), params.units), "height in points", 0.001, 16348);
            }
        } else {
            if (!(element.points instanceof Array) || element.points.length < 2 || element.points.length > 10000) { A.fail("INVALID_ARGUMENT", "path.points requires 2 to 10000 points."); }
            if (element.closed !== undefined && typeof element.closed !== "boolean") { A.fail("INVALID_ARGUMENT", "closed must be boolean."); }
            for (var i = 0; i < element.points.length; i++) {
                var point = A.object(element.points[i], "path point");
                A.point(document, params, A.number(point.x, "point.x"), A.number(point.y, "point.y"));
                if (point.left !== undefined) { A.handle(document, params, point.left); }
                if (point.right !== undefined) { A.handle(document, params, point.right); }
                if (point.smooth !== undefined && typeof point.smooth !== "boolean") { A.fail("INVALID_ARGUMENT", "point.smooth must be boolean."); }
            }
        }
    };
    A.handle = function (document, params, value) {
        if (value instanceof Array) {
            if (value.length !== 2) { A.fail("INVALID_ARGUMENT", "A Bézier handle must contain x and y."); }
            return A.point(document, params, A.number(value[0], "handle.x"), A.number(value[1], "handle.y"));
        }
        A.object(value, "Bézier handle");
        return A.point(document, params, A.number(value.x, "handle.x"), A.number(value.y, "handle.y"));
    };
    A.applyTextStyle = function (item, element, trace) {
        function stage(name) { if (trace) { trace(name); } }
        stage("text.characterAttributes");
        var attrs = item.textRange.characterAttributes;
        if (element.font !== undefined) { stage("text.font"); attrs.textFont = A.font(element.font); }
        if (element.size_pt !== undefined) { stage("text.size"); attrs.size = element.size_pt; }
        if (element.tracking !== undefined) { stage("text.tracking"); attrs.tracking = element.tracking; }
        if (element.leading_pt !== undefined) { stage("text.autoLeading"); attrs.autoLeading = false; stage("text.leading"); attrs.leading = element.leading_pt; }
        var fill = element.color !== undefined ? element.color : element.fill;
        if (fill !== undefined) { stage("text.fillColor"); attrs.fillColor = fill === null ? new NoColor() : A.color(fill); }
        if (element.stroke !== undefined) { stage("text.strokeColor"); attrs.strokeColor = element.stroke === null ? new NoColor() : A.color(element.stroke); }
        var strokeWidth = element.stroke_width_pt !== undefined ? element.stroke_width_pt : element.width_pt;
        if (strokeWidth !== undefined) { stage("text.strokeWeight"); attrs.strokeWeight = strokeWidth; }
    };
    A.applyPathStyle = function (item, element) {
        if (element.fill !== undefined) { item.filled = element.fill !== null; if (item.filled) { item.fillColor = A.color(element.fill); } }
        if (element.stroke !== undefined) { item.stroked = element.stroke !== null; if (item.stroked) { item.strokeColor = A.color(element.stroke); } }
        var strokeWidth = element.stroke_width_pt !== undefined ? element.stroke_width_pt : element.width_pt;
        if (strokeWidth !== undefined) { item.strokeWidth = strokeWidth; }
    };
    A.drawElement = function (document, params, element, layer) {
        var asset = A.validateElement(document, params, element);
        var item = null, areaPath = null, placed = null, currentStage = "create";
        try {
            var position;
            if (element.type === "rect" || element.type === "ellipse") {
                position = A.point(document, params, element.x, element.y);
                if (element.type === "rect") { item = layer.pathItems.rectangle(position[1], position[0], A.length(element.width, params.units), A.length(element.height, params.units)); }
                else { item = layer.pathItems.ellipse(position[1], position[0], A.length(element.width, params.units), A.length(element.height, params.units)); }
            } else if (element.type === "text") {
                if (element.width !== undefined && element.height !== undefined) {
                    currentStage = "text.area.path";
                    position = A.point(document, params, element.x, element.y);
                    areaPath = layer.pathItems.rectangle(position[1], position[0], A.length(element.width, params.units), A.length(element.height, params.units));
                    areaPath.filled = false; areaPath.stroked = false;
                    item = document.textFrames.areaText(areaPath);
                    /* areaText can inherit the active layer (including nonprinting Guides). */
                    currentStage = "text.area.moveToLayer";
                    /* Match the front-of-layer order of new paths and point type.
                     * PLACEATEND hid type behind an earlier page background. */
                    item.move(layer, ElementPlacement.PLACEATBEGINNING);
                    currentStage = "text.area.pathFill"; item.textPath.filled = false;
                    currentStage = "text.area.pathStroke"; item.textPath.stroked = false;
                } else { currentStage = "text.point.add"; item = layer.textFrames.add(); }
                currentStage = "text.contents";
                item.contents = element.text;
                /* Resolve the explicit font before paragraph access; leave proven point-text behavior unchanged. */
                A.applyTextStyle(item, element, function (name) { currentStage = name; });
                var newCharacter;
                if (element.size_pt === undefined) {
                    currentStage = "text.defaultSize"; item.textRange.characterAttributes.size = 12;
                }
                if (element.color === undefined && element.fill === undefined) {
                    currentStage = "text.defaultFill"; item.textRange.characterAttributes.fillColor = A.color("#000000");
                }
                if (element.width !== undefined) {
                    currentStage = "text.area.characterAttributes"; newCharacter = item.textRange.characterAttributes;
                    currentStage = "text.area.tracking"; newCharacter.tracking = element.tracking === undefined ? 0 : element.tracking;
                    currentStage = "text.area.horizontalScale"; newCharacter.horizontalScale = 100;
                    currentStage = "text.area.verticalScale"; newCharacter.verticalScale = 100;
                    currentStage = "text.area.baselineShift"; newCharacter.baselineShift = 0;
                    currentStage = "text.area.overprintFill"; newCharacter.overprintFill = false;
                    currentStage = "text.area.paragraphAttributes"; var newParagraph = item.textRange.paragraphAttributes;
                    currentStage = "text.area.justification"; newParagraph.justification = Justification.LEFT;
                    currentStage = "text.area.leftIndent"; newParagraph.leftIndent = 0;
                    currentStage = "text.area.rightIndent"; newParagraph.rightIndent = 0;
                    currentStage = "text.area.firstLineIndent"; newParagraph.firstLineIndent = 0;
                    currentStage = "text.area.spaceBefore"; newParagraph.spaceBefore = 0;
                    currentStage = "text.area.spaceAfter"; newParagraph.spaceAfter = 0;
                    currentStage = "text.area.hyphenation"; newParagraph.hyphenation = false;
                } else { currentStage = "text.point.position"; item.position = A.point(document, params, element.x, element.y); }
            } else if (element.type === "image") {
                item = layer.groupItems.add();
                placed = layer.placedItems.add();
                placed.file = asset;
                placed.move(item, ElementPlacement.PLACEATEND);
                var sourceWidth = A.number(placed.width, "native image width", 0.001), sourceHeight = A.number(placed.height, "native image height", 0.001);
                var boxWidth = A.length(element.width, params.units), boxHeight = A.length(element.height, params.units);
                var ratio = element.fit === "cover" ? Math.max(boxWidth / sourceWidth, boxHeight / sourceHeight) : Math.min(boxWidth / sourceWidth, boxHeight / sourceHeight);
                placed.resize(ratio * 100, ratio * 100);
                position = A.point(document, params, element.x, element.y);
                placed.position = [position[0] + (boxWidth - placed.width) / 2, position[1] - (boxHeight - placed.height) / 2];
                /* embed replaces the PlacedItem; the containing group's UUID survives. */
                if (element.embed !== false) { placed.embed(); placed = null; }
                if (element.fit === "cover") {
                    var mask = item.pathItems.rectangle(position[1], position[0], boxWidth, boxHeight);
                    mask.filled = false; mask.stroked = false; mask.clipping = true;
                    mask.zOrder(ZOrderMethod.BRINGTOFRONT); item.clipped = true;
                }
            } else {
                item = layer.pathItems.add();
                for (var i = 0; i < element.points.length; i++) {
                    var source = element.points[i], point = item.pathPoints.add();
                    var anchor = A.point(document, params, source.x, source.y);
                    point.anchor = anchor;
                    point.leftDirection = source.left !== undefined ? A.handle(document, params, source.left) : anchor;
                    point.rightDirection = source.right !== undefined ? A.handle(document, params, source.right) : anchor;
                    point.pointType = source.smooth === true ? PointType.SMOOTH : PointType.CORNER;
                }
                item.closed = element.closed === true;
            }
            if (element.type !== "text" && element.type !== "image") {
                /* Deterministic defaults, independent of Illustrator's last-used style. */
                item.filled = false; item.stroked = false;
                A.applyPathStyle(item, element);
                if (element.fill === undefined && element.stroke === undefined) {
                    item.stroked = true; item.strokeColor = A.color("#000000"); item.strokeWidth = 1;
                }
            }
            if (element.name !== undefined) { item.name = element.name; }
            if (element.opacity !== undefined) { item.opacity = element.opacity; }
            return item;
        } catch (err) {
            if (item) { try { item.remove(); } catch (ignored) {} }
            if (placed) { try { placed.remove(); } catch (ignoredPlaced) {} }
            if (areaPath) { try { areaPath.remove(); } catch (ignoredAreaPath) {} }
            A.fail(err.illonaCode || "ILLUSTRATOR_ERROR", "Element " + (element.name ? "\"" + element.name + "\" " : "") + "(" + element.type + ") at " + currentStage + ": " + String(err.message || err));
        }
    };
    A.ops.create_elements = function (params) {
        var document = A.doc(params.document_id);
        A.units(params.units); A.artboard(document, params.artboard_index);
        if (!(params.elements instanceof Array) || params.elements.length < 1 || params.elements.length > 500) { A.fail("INVALID_ARGUMENT", "elements requires 1 to 500 items."); }
        var layerName = params.layer_name === undefined ? "Illona" : params.layer_name;
        var existing = A.existingLayer(document, layerName);
        if (existing && (existing.locked || !existing.visible)) { A.fail("LAYER_NOT_EDITABLE", "Layer is locked or hidden."); }
        var i;
        for (i = 0; i < params.elements.length; i++) { A.validateElement(document, params, params.elements[i]); }
        var layer = A.layer(document, layerName), created = [], info = [];
        try {
            for (i = 0; i < params.elements.length; i++) {
                var item = A.drawElement(document, params, params.elements[i], layer);
                created.push(item); info.push(A.itemInfo(item));
            }
        } catch (err) {
            for (i = created.length - 1; i >= 0; i--) { try { created[i].remove(); } catch (ignored) {} }
            if (!existing) { try { layer.remove(); } catch (ignoredLayer) {} }
            throw err;
        }
        app.redraw();
        return {document_id: params.document_id, created: info, count: info.length, text_coordinates: "Text x/y position the top-left geometric frame, not the typographic baseline."};
    };
    A.ops.update_objects = function (params) {
        var document = A.doc(params.document_id);
        A.units(params.units); A.artboard(document, params.artboard_index);
        if (!(params.changes instanceof Array) || params.changes.length < 1 || params.changes.length > 500) { A.fail("INVALID_ARGUMENT", "changes requires 1 to 500 objects."); }
        var items = [], seen = {}, i, change, item;
        for (i = 0; i < params.changes.length; i++) {
            change = A.object(params.changes[i], "change");
            item = A.findItem(document, change.id); A.assertEditable(item);
            if (seen[change.id]) { A.fail("INVALID_ARGUMENT", "Each object may appear only once in a batch."); }
            seen[change.id] = true;
            if (change.x !== undefined) { A.number(change.x, "x"); }
            if (change.y !== undefined) { A.number(change.y, "y"); }
            if (change.width !== undefined) { A.number(A.length(A.number(change.width, "width", 0.001), params.units), "width in points", 0.001, 16348); }
            if (change.height !== undefined) { A.number(A.length(A.number(change.height, "height", 0.001), params.units), "height in points", 0.001, 16348); }
            var isText = item.typename === "TextFrame", isPath = item.typename === "PathItem";
            A.validateStyle(change, isText);
            if (change.text !== undefined) { if (!isText) { A.fail("TYPE_MISMATCH", "text replacement requires a text frame."); } A.string(change.text, "text", 100000, true); }
            if ((change.font !== undefined || change.size_pt !== undefined || change.leading_pt !== undefined || change.tracking !== undefined || change.color !== undefined) && !isText) { A.fail("TYPE_MISMATCH", "Typography properties require a text frame."); }
            if ((change.fill !== undefined || change.stroke !== undefined || change.stroke_width_pt !== undefined || change.width_pt !== undefined) && !isText && !isPath) { A.fail("TYPE_MISMATCH", "Fill/stroke editing currently supports path and text objects."); }
            items.push(item);
        }
        var results = [], warnings = [], completed = [];
        try {
            for (i = 0; i < params.changes.length; i++) {
                change = params.changes[i]; item = items[i];
                if (change.name !== undefined) { item.name = change.name; }
                if (change.text !== undefined) { item.contents = change.text; warnings.push("Replacing all contents of " + change.id + " may reset mixed character formatting. Explicit typography changes apply to its entire text range."); }
                if (item.typename === "TextFrame") { A.applyTextStyle(item, change); }
                else if (item.typename === "PathItem") { A.applyPathStyle(item, change); }
                if (change.width !== undefined) { item.width = A.length(change.width, params.units); }
                if (change.height !== undefined) { item.height = A.length(change.height, params.units); }
                if (change.x !== undefined || change.y !== undefined) {
                    var pos = item.position, target = A.point(document, params, change.x === undefined ? 0 : change.x, change.y === undefined ? 0 : change.y);
                    item.position = [change.x === undefined ? pos[0] : target[0], change.y === undefined ? pos[1] : target[1]];
                }
                if (change.opacity !== undefined) { item.opacity = change.opacity; }
                completed.push(change.id); results.push(A.itemInfo(item));
            }
        } catch (err) {
            A.fail("PARTIAL_UPDATE", "Illustrator stopped during an update. Completed object IDs: " + completed.join(", ") + ". Current object may be partly changed. Refresh inspection before retrying. " + String(err.message || err));
        }
        app.redraw();
        return {document_id: params.document_id, updated: results, count: results.length, warnings: warnings};
    };
})(Illona);
