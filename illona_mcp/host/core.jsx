/* Illona Illustrator host helpers. ExtendScript / ECMAScript 3. */
var Illona = {ops: {}};

(function (A) {
    var registryKey = "__ILLONA_STATE";
    if (!$.global[registryKey]) {
        $.global[registryKey] = {documents: [], nextId: 1, session: String(new Date().getTime())};
    }
    A.state = $.global[registryKey];

    A.fail = function (code, message) {
        var err = new Error(message);
        err.illonaCode = code;
        throw err;
    };
    A.object = function (value, label) {
        if (value === null || typeof value !== "object" || value instanceof Array) {
            A.fail("INVALID_ARGUMENT", label + " must be an object.");
        }
        return value;
    };
    A.number = function (value, label, min, max) {
        if (typeof value !== "number" || !isFinite(value)) {
            A.fail("INVALID_ARGUMENT", label + " must be a finite number.");
        }
        if ((min !== undefined && value < min) || (max !== undefined && value > max)) {
            A.fail("INVALID_ARGUMENT", label + " is outside its allowed range.");
        }
        return value;
    };
    A.integer = function (value, label, min, max) {
        A.number(value, label, min, max);
        if (Math.floor(value) !== value) { A.fail("INVALID_ARGUMENT", label + " must be an integer."); }
        return value;
    };
    A.string = function (value, label, max, allowEmpty) {
        if (typeof value !== "string" || (!allowEmpty && value.length === 0) || value.length > max) {
            A.fail("INVALID_ARGUMENT", label + " must be " + (allowEmpty ? "a" : "a nonempty") + " string of at most " + max + " characters.");
        }
        return value;
    };
    A.units = function (units) {
        units = units === undefined ? "mm" : units;
        if (units !== "mm" && units !== "pt") { A.fail("INVALID_ARGUMENT", "units must be mm or pt."); }
        return units;
    };
    A.length = function (value, units) {
        A.number(value, "length");
        return value * (A.units(units) === "mm" ? 72 / 25.4 : 1);
    };
    A.isOpen = function (document) {
        try {
            var ignored = document.name;
            for (var i = 0; i < app.documents.length; i++) {
                if (app.documents[i] === document) { return true; }
            }
        } catch (err) {}
        return false;
    };
    A.docId = function (document) {
        var records = A.state.documents;
        for (var i = 0; i < records.length; i++) {
            try {
                if (records[i].document === document) { return records[i].id; }
            } catch (ignored) {}
        }
        var id = "doc-" + A.state.session + "-" + A.state.nextId++;
        records.push({id: id, document: document});
        return id;
    };
    A.doc = function (id) {
        A.string(id, "document_id", 200, false);
        for (var i = 0; i < A.state.documents.length; i++) {
            var record = A.state.documents[i];
            if (record.id === id) {
                if (A.isOpen(record.document)) { return record.document; }
                A.fail("DOCUMENT_CLOSED", "The requested document has closed. Refresh status before continuing.");
            }
        }
        A.fail("DOCUMENT_NOT_FOUND", "Unknown document_id. Call status and use a current document ID.");
    };
    A.documentInfo = function (document) {
        var info = {
            id: A.docId(document), name: String(document.name),
            color_mode: document.documentColorSpace == DocumentColorSpace.CMYK ? "CMYK" : "RGB",
            artboard_count: document.artboards.length, layer_count: document.layers.length,
            object_count: document.pageItems.length, modified: !document.saved
        };
        /* New unsaved documents may expose a synthetic fullName without a file. */
        try {
            var file = document.fullName;
            info.path = file.exists ? file.fsName : null;
        } catch (ignored) { info.path = null; }
        return info;
    };
    A.artboard = function (document, index) {
        index = index === undefined ? 0 : index;
        A.integer(index, "artboard_index", 0, document.artboards.length - 1);
        return document.artboards[index];
    };
    A.point = function (document, params, x, y) {
        var rect = A.artboard(document, params.artboard_index).artboardRect;
        return [rect[0] + A.length(x, params.units), rect[1] - A.length(y, params.units)];
    };
    A.color = function (spec) {
        if (typeof spec === "string") {
            if (!/^#[0-9a-fA-F]{6}$/.test(spec)) { A.fail("INVALID_COLOR", "Hex colors must use #RRGGBB."); }
            spec = {space: "rgb", values: [parseInt(spec.substr(1, 2), 16), parseInt(spec.substr(3, 2), 16), parseInt(spec.substr(5, 2), 16)]};
        }
        A.object(spec, "color");
        var color, i;
        if (spec.space === "rgb") {
            if (!(spec.values instanceof Array) || spec.values.length !== 3) { A.fail("INVALID_COLOR", "rgb requires three values."); }
            for (i = 0; i < 3; i++) { A.number(spec.values[i], "rgb component", 0, 255); }
            color = new RGBColor();
            color.red = spec.values[0]; color.green = spec.values[1]; color.blue = spec.values[2];
        } else if (spec.space === "cmyk") {
            if (!(spec.values instanceof Array) || spec.values.length !== 4) { A.fail("INVALID_COLOR", "cmyk requires four values."); }
            for (i = 0; i < 4; i++) { A.number(spec.values[i], "cmyk component", 0, 100); }
            color = new CMYKColor();
            color.cyan = spec.values[0]; color.magenta = spec.values[1]; color.yellow = spec.values[2]; color.black = spec.values[3];
        } else { A.fail("INVALID_COLOR", "color.space must be rgb or cmyk."); }
        return color;
    };
    A.describe = function (color) {
        if (!color) { return null; }
        try {
            if (color.typename === "RGBColor") { return {space: "rgb", values: [color.red, color.green, color.blue]}; }
            if (color.typename === "CMYKColor") { return {space: "cmyk", values: [color.cyan, color.magenta, color.yellow, color.black]}; }
            if (color.typename === "GrayColor") { return {space: "gray", values: [color.gray]}; }
            if (color.typename === "SpotColor") { return {space: "spot", name: color.spot.name, tint: color.tint}; }
            return {space: color.typename};
        } catch (ignored) { return null; }
    };
    A.itemInfo = function (item) {
        var info = {id: String(item.uuid), name: String(item.name), type: String(item.typename)};
        try {
            var b = item.geometricBounds;
            info.bounds = {left: b[0], top: b[1], right: b[2], bottom: b[3], width: b[2] - b[0], height: b[1] - b[3], units: "pt", coordinates: "document"};
            info.locked = item.locked; info.hidden = item.hidden; info.opacity = item.opacity;
            info.layer = item.layer.name;
        } catch (ignored) {}
        if (item.typename === "TextFrame") {
            try { info.text = String(item.contents); info.text_kind = String(item.kind); } catch (ignoredText) {}
        }
        if (item.typename === "PathItem") {
            try { info.closed = item.closed; info.point_count = item.pathPoints.length; info.fill = item.filled ? A.describe(item.fillColor) : null; info.stroke = item.stroked ? A.describe(item.strokeColor) : null; info.stroke_width_pt = item.strokeWidth; } catch (ignoredPath) {}
        }
        return info;
    };
    A.findItem = function (document, id) {
        A.string(id, "object id", 200, false);
        /* Illustrator 30.8 can return a GroupItem proxy for a PlacedItem from
         * getPageItemFromUuid, despite the UUID matching. Collection lookup
         * preserves the native subtype and confines resolution to this document. */
        for (var i = 0; i < document.pageItems.length; i++) {
            try {
                var found = document.pageItems[i];
                if (String(found.uuid) === id) { return found; }
            } catch (ignored) {}
        }
        A.fail("OBJECT_NOT_FOUND", "Object " + id + " no longer exists in the requested document.");
    };
    A.assertEditable = function (item) {
        try {
            if (!item.editable || item.locked || item.hidden) { A.fail("OBJECT_NOT_EDITABLE", "Object is locked, hidden, or not editable: " + item.name); }
            var parent = item.parent;
            while (parent && parent.typename !== "Document") {
                if (parent.locked || (parent.typename === "Layer" && !parent.visible)) { A.fail("OBJECT_NOT_EDITABLE", "An ancestor layer or group is locked or hidden."); }
                parent = parent.parent;
            }
        } catch (err) {
            if (err.illonaCode) { throw err; }
            A.fail("OBJECT_NOT_EDITABLE", "Cannot verify object editability.");
        }
    };
    A.existingLayer = function (document, name) {
        A.string(name, "layer_name", 200, false);
        for (var i = 0; i < document.layers.length; i++) {
            if (document.layers[i].name === name) { return document.layers[i]; }
        }
        return null;
    };
    A.layer = function (document, name) {
        name = name === undefined ? "Illona" : name;
        var layer = A.existingLayer(document, name);
        if (layer) {
            if (layer.locked || !layer.visible) { A.fail("LAYER_NOT_EDITABLE", "Layer is locked or hidden: " + name); }
            return layer;
        }
        layer = document.layers.add(); layer.name = name;
        return layer;
    };
    A.font = function (name) {
        A.string(name, "font", 200, false);
        try { return app.textFonts.getByName(name); } catch (ignored) {}
        A.fail("FONT_NOT_FOUND", "Font is not installed. Use its PostScript name from list_fonts: " + name);
    };
    A.run = function (operation, params) {
        var previousSystem;
        try {
            if (!A.ops.hasOwnProperty(operation)) { A.fail("UNKNOWN_OPERATION", "Unsupported operation: " + operation); }
            A.object(params, "params");
            previousSystem = app.coordinateSystem;
            app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
            return {ok: true, data: A.ops[operation](params)};
        } catch (err) {
            return {ok: false, error: {code: err.illonaCode || "ILLUSTRATOR_ERROR", message: String(err.message || err)}};
        } finally {
            if (previousSystem !== undefined) { try { app.coordinateSystem = previousSystem; } catch (ignored) {} }
        }
    };
    A.ops.status = function (params) {
        var docs = [];
        for (var i = 0; i < app.documents.length; i++) { docs.push(A.documentInfo(app.documents[i])); }
        return {application: app.name, version: app.version, documents: docs, document_ids_are_session_scoped: true};
    };
    A.ops.create_document = function (params) {
        var units = A.units(params.units);
        var width = A.length(A.number(params.width, "width", 0.1), units);
        var height = A.length(A.number(params.height, "height", 0.1), units);
        if (width > 16348 || height > 16348) { A.fail("INVALID_ARGUMENT", "Document size exceeds the supported standard canvas limit of 16348 pt."); }
        var mode = params.color_mode === undefined ? "RGB" : params.color_mode;
        if (mode !== "RGB" && mode !== "CMYK") { A.fail("INVALID_ARGUMENT", "color_mode must be RGB or CMYK."); }
        if (params.name !== undefined) { A.string(params.name, "name", 200, false); }
        var boardCount = params.artboard_count === undefined ? 1 : A.integer(params.artboard_count, "artboard_count", 1, 20);
        var preset = new DocumentPreset();
        preset.width = width; preset.height = height;
        preset.colorMode = mode === "CMYK" ? DocumentColorSpace.CMYK : DocumentColorSpace.RGB;
        preset.units = units === "mm" ? RulerUnits.Millimeters : RulerUnits.Points;
        if (params.name !== undefined) { preset.title = params.name; }
        var presets = app.startupPresetsList;
        var document = app.documents.addDocument(presets.length ? presets[0] : "", preset, false);
        app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        document.artboards[0].name = "01 - Page 1";
        var origin = document.artboards[0].artboardRect;
        var gap = A.length(20, "mm");
        for (var bi = 1; bi < boardCount; bi++) {
            var left = origin[0] + bi * (width + gap);
            document.artboards.add([left, origin[1], left + width, origin[1] - height]);
            document.artboards[bi].name = (bi < 9 ? "0" : "") + (bi + 1) + " - Page " + (bi + 1);
        }
        return A.documentInfo(document);
    };
    A.ops.inspect_document = function (params) {
        var document = A.doc(params.document_id), limit = params.limit === undefined ? 200 : params.limit;
        A.integer(limit, "limit", 1, 1000);
        var result = A.documentInfo(document), items = [], layers = [], boards = [];
        var i;
        for (i = 0; i < document.pageItems.length && i < limit; i++) { items.push(A.itemInfo(document.pageItems[i])); }
        for (i = 0; i < document.layers.length; i++) { layers.push({name: document.layers[i].name, locked: document.layers[i].locked, visible: document.layers[i].visible}); }
        for (i = 0; i < document.artboards.length; i++) {
            var board = document.artboards[i], rect = board.artboardRect;
            boards.push({index: i, name: board.name, rect_pt: [rect[0], rect[1], rect[2], rect[3]], width_mm: (rect[2] - rect[0]) * 25.4 / 72, height_mm: (rect[1] - rect[3]) * 25.4 / 72});
        }
        result.items = items; result.items_truncated = document.pageItems.length > limit;
        result.layers = layers; result.artboards = boards;
        return result;
    };
    A.ops.inspect_selection = function (params) {
        var document = A.doc(params.document_id), selection = document.selection, items = [];
        if (selection && selection.typename === "TextRange") {
            return {document_id: params.document_id, selection_type: "text_range", text: String(selection.contents)};
        }
        if (selection) {
            for (var i = 0; i < selection.length && i < 1000; i++) { items.push(A.itemInfo(selection[i])); }
        }
        return {document_id: params.document_id, items: items, truncated: selection && selection.length > 1000 ? true : false};
    };
    A.ops.list_fonts = function (params) {
        var limit = params.limit === undefined ? 200 : params.limit;
        A.integer(limit, "limit", 1, 2000);
        var fonts = [];
        for (var i = 0; i < app.textFonts.length && i < limit; i++) {
            var font = app.textFonts[i];
            fonts.push({postscript_name: font.name, family: font.family, style: font.style});
        }
        return {fonts: fonts, total: app.textFonts.length, truncated: app.textFonts.length > limit};
    };
})(Illona);
