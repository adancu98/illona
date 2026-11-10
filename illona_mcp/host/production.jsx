/* Illona preview, output and advisory preflight. ExtendScript / ECMAScript 3. */
(function (A) {
    function bool(value, label, fallback) {
        if (value === undefined) { return fallback; }
        if (typeof value !== "boolean") { A.fail("INVALID_ARGUMENT", label + " must be a boolean."); }
        return value;
    }
    function outputFile(path, extension, overwrite, source, allowSource) {
        A.string(path, "path", 4096, false);
        if (path.charAt(0) !== "/" || path.indexOf("\u0000") !== -1) {
            A.fail("INVALID_PATH", "Output path must be an absolute local path.");
        }
        if (!(new RegExp("\\." + extension + "$", "i")).test(path)) {
            A.fail("INVALID_PATH", "Output path must end in ." + extension + ".");
        }
        var file = new File(path);
        if (!file.parent.exists) { A.fail("OUTPUT_DIRECTORY_MISSING", "Output directory does not exist."); }
        if (file.exists && !overwrite) { A.fail("OUTPUT_EXISTS", "Output already exists. Choose another path or explicitly enable overwrite."); }
        for (var i = 0; i < app.documents.length; i++) {
            var openDocument = app.documents[i], openPath = null;
            try { openPath = openDocument.fullName.fsName; } catch (ignored) {}
            if (openPath === file.fsName && !(allowSource && (openDocument == source))) {
                A.fail("OUTPUT_DOCUMENT_OPEN", "Output is an open document. Use save_document for the explicitly targeted source, or choose another path.");
            }
        }
        return file;
    }
    function stageFile(extension) {
        var file;
        do {
            file = new File(Folder.temp.fsName + "/illona-output-" + String(new Date().getTime()) + "-" + String(Math.floor(Math.random() * 1000000000)) + "." + extension);
        } while (file.exists);
        return file;
    }
    function commitOutput(staged, target, overwrite) {
        if (!staged.exists || staged.length <= 0) { A.fail("OUTPUT_NOT_CREATED", "Illustrator did not produce a nonempty output file."); }
        if (target.exists && !overwrite) { A.fail("OUTPUT_EXISTS", "Output appeared during export; existing file was preserved."); }
        if (!staged.copy(target.fsName)) { A.fail("OUTPUT_COPY_FAILED", "Could not write the requested output path: " + staged.error); }
        var result = new File(target.fsName);
        if (!result.exists || result.length !== staged.length) { A.fail("OUTPUT_VERIFICATION_FAILED", "Output size verification failed. Inspect the destination before retrying."); }
        return {path: result.fsName, bytes: result.length};
    }
    function sourceFocus() {
        try { return app.documents.length ? app.activeDocument : null; } catch (ignored) { return null; }
    }
    function restoreFocus(previous) {
        if (previous && A.isOpen(previous)) { try { previous.activate(); } catch (ignored) {} }
    }
    function png(document, artboardIndex, file, widthPx) {
        var rect = A.artboard(document, artboardIndex).artboardRect;
        var options = new ExportOptionsPNG24();
        options.artBoardClipping = true;
        options.antiAliasing = true;
        options.transparency = true;
        options.matte = false;
        options.horizontalScale = 100 * widthPx / (rect[2] - rect[0]);
        options.verticalScale = options.horizontalScale;
        document.exportFile(new File(file.fsName.replace(/\.png$/i, "")), ExportType.PNG24, options);
    }
    function layerNodes(layer) {
        var nodes = [], items = [], i, item;
        for (i = 0; i < layer.layers.length; i++) { nodes.push(layer.layers[i]); }
        for (i = 0; i < layer.pageItems.length; i++) {
            item = layer.pageItems[i];
            if (item.parent == layer) { items.push(item); }
        }
        // Layer and PageItem zOrderPosition values use separate sequences.
        // Comparing them can silently reverse overlapping artwork.
        if (nodes.length && items.length) {
            A.fail("EXPORT_MIXED_LAYER_CONTENT_UNSUPPORTED", "This layer mixes sublayers and direct artwork. Their relative stack cannot be verified by this export-copy method. Save the native AI document or export this complex document in Illustrator.");
        }
        // Both collections enumerate their own siblings from front to back.
        return nodes.length ? nodes : items;
    }
    function intersectsOutput(item, rect) {
        try {
            var b = item.visibleBounds;
            return b[2] >= rect[0] && b[0] <= rect[2] && b[1] >= rect[3] && b[3] <= rect[1];
        } catch (ignoredBounds) { A.fail("EXPORT_BOUNDS_UNAVAILABLE", "Could not verify bounds for object " + item.name + "."); }
    }
    function cloneLayer(source, parent, stats) {
        if (!source.visible || !source.printable) { stats.skipped_layers++; return; }
        var target = parent.layers.add();
        target.name = source.name;
        target.move(parent, ElementPlacement.PLACEATEND);
        target.visible = true;
        target.locked = false;
        target.printable = true;
        try { target.opacity = source.opacity; target.blendingMode = source.blendingMode; } catch (ignoredAppearance) {}
        var nodes = layerNodes(source), i, item, copy, sourcePosition;
        for (i = 0; i < nodes.length; i++) {
            item = nodes[i];
            if (item.typename === "Layer") { cloneLayer(item, target, stats); }
            else if (!item.hidden && !(item.typename === "PathItem" && item.guides) && intersectsOutput(item, stats.bounds)) {
                try {
                    // Cross-document duplicate can compensate for differing
                    // artboard origins. Restore explicit document coordinates.
                    sourcePosition = [Number(item.position[0]), Number(item.position[1])];
                    copy = item.duplicate(target, ElementPlacement.PLACEATEND);
                    copy.position = sourcePosition;
                }
                catch (err) { A.fail("EXPORT_COPY_FAILED", "Could not copy object " + item.name + " into the temporary output document: " + err.message); }
                copy.selected = false;
                stats.copied_objects++;
            }
        }
        target.locked = source.locked;
    }
    function cloneArtwork(document, artboardIndex, state) {
        var rect = A.artboard(document, artboardIndex).artboardRect;
        var documentBleed = state.bleed_pt || 0;
        var preset = new DocumentPreset();
        preset.width = rect[2] - rect[0] + documentBleed * 2;
        preset.height = rect[1] - rect[3] + documentBleed * 2;
        preset.colorMode = document.documentColorSpace;
        preset.units = RulerUnits.Points;
        preset.title = "Illona temporary output";
        // Native PDF bleed offsets are ignored by some Illustrator versions.
        // Render the physical bleed inside an expanded temporary artboard;
        // Python verifies its media size and assigns real trim/bleed boxes.
        preset.documentBleedLink = true;
        preset.documentBleedOffsetRect = [0, 0, 0, 0];
        var presets = app.startupPresetsList;
        if (!presets || !presets.length) { A.fail("DOCUMENT_PRESET_MISSING", "Illustrator has no startup document preset for a temporary output document."); }
        var copy = app.documents.addDocument(presets[0], preset, false);
        state.document = copy;
        app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        copy.artboards[0].artboardRect = [rect[0] - documentBleed, rect[1] + documentBleed, rect[2] + documentBleed, rect[3] - documentBleed];
        app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        copy.artboards[0].name = document.artboards[artboardIndex].name;
        try { copy.rasterEffectSettings.resolution = document.rasterEffectSettings.resolution; } catch (ignoredRasterEffects) {}
        var defaultLayer = copy.layers[0];
        for (var i = 0; i < document.layers.length; i++) { cloneLayer(document.layers[i], copy, state); }
        if (copy.layers.length > 1) { defaultLayer.remove(); }
        return copy;
    }
    function cloneLimitations() {
        return [
            "Output contains the selected artboard and copied visible, printable artwork; hidden and nonprinting layers are excluded.",
            "Only top-level artwork intersecting the chosen artboard/bleed is copied; a crossing group can retain content outside the artboard inside the output data.",
            "Document metadata, color profile/output intent, variable bindings, linked text across separate frames, and layer-level live effects are not guaranteed to survive an artwork copy.",
            "This export is not a certified PDF/X or press-readiness validation. Compare the exported preview before production use."
        ];
    }

    A.ops.preview_document = function (p) {
        var document = A.doc(p.document_id), index = p.artboard_index === undefined ? 0 : p.artboard_index;
        A.artboard(document, index);
        var width = p.width_px === undefined ? 1400 : A.integer(p.width_px, "width_px", 64, 8192);
        var overwrite = bool(p.overwrite, "overwrite", false);
        var target = outputFile(p.path, "png", overwrite, document, false);
        var staged = stageFile("png"), board = document.artboards.getActiveArtboardIndex();
        var interaction = app.userInteractionLevel, previous = sourceFocus();
        try {
            app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
            document.activate();
            document.artboards.setActiveArtboardIndex(index);
            png(document, index, staged, width);
            var result = commitOutput(staged, target, overwrite), rect = document.artboards[index].artboardRect;
            result.document_id = p.document_id;
            result.artboard_index = index;
            result.width_px = width;
            result.estimated_height_px = Math.round(width * (rect[1] - rect[3]) / (rect[2] - rect[0]));
            result.format = "png";
            return result;
        } finally {
            try { document.artboards.setActiveArtboardIndex(board); } catch (ignoredBoard) {}
            try { app.userInteractionLevel = interaction; } catch (ignoredInteraction) {}
            restoreFocus(previous);
            if (staged.exists) { try { staged.remove(); } catch (ignoredFile) {} }
        }
    };

    A.ops.save_document = function (p) {
        var document = A.doc(p.document_id), overwrite = bool(p.overwrite, "overwrite", false);
        var target = outputFile(p.path, "ai", overwrite, document, true);
        var interaction = app.userInteractionLevel, previous = sourceFocus(), previousPath = null;
        try { previousPath = document.fullName.fsName; } catch (ignoredPath) {}
        try {
            app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
            document.activate();
            var options = new IllustratorSaveOptions();
            options.pdfCompatible = true;
            options.compressed = true;
            document.saveAs(target, options);
            if (!target.exists || target.length <= 0) { A.fail("OUTPUT_NOT_CREATED", "Illustrator did not produce the AI file."); }
            return {document: A.documentInfo(document), path: target.fsName, bytes: target.length, format: "ai", previous_path: previousPath, source_path_changed: previousPath !== target.fsName};
        } finally {
            try { app.userInteractionLevel = interaction; } catch (ignoredInteraction) {}
            restoreFocus(previous);
        }
    };

    A.ops.export_document = function (p) {
        var document = A.doc(p.document_id), format = p.format;
        if (format !== "png" && format !== "svg" && format !== "pdf" && format !== "ai") {
            A.fail("INVALID_ARGUMENT", "format must be png, svg, pdf, or ai.");
        }
        if (format === "png") { return A.ops.preview_document(p); }
        var index = p.artboard_index === undefined ? 0 : p.artboard_index;
        A.artboard(document, index);
        var overwrite = bool(p.overwrite, "overwrite", false), target = outputFile(p.path, format, overwrite, document, false);
        var bleed = p.bleed_mm === undefined ? 0 : A.number(p.bleed_mm, "bleed_mm", 0, 100);
        if (p.pdf_preset !== undefined) {
            if (format !== "pdf") { A.fail("INVALID_ARGUMENT", "pdf_preset applies only to PDF output."); }
            A.string(p.pdf_preset, "pdf_preset", 200, false);
            var foundPreset = false;
            for (var pi = 0; pi < app.PDFPresetsList.length; pi++) { if (String(app.PDFPresetsList[pi]) === p.pdf_preset) { foundPreset = true; break; } }
            if (!foundPreset) { A.fail("PDF_PRESET_NOT_FOUND", "The requested PDF preset is not installed."); }
        }
        var bounds = A.artboard(document, index).artboardRect, margin = format === "pdf" ? bleed * 72 / 25.4 : 0;
        var state = {document: null, copied_objects: 0, skipped_layers: 0, bleed_pt: margin, bounds: [bounds[0] - margin, bounds[1] + margin, bounds[2] + margin, bounds[3] - margin]};
        var previous = sourceFocus(), interaction = app.userInteractionLevel, staged = stageFile(format);
        try {
            app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
            var copy = cloneArtwork(document, index, state), options;
            if (format === "pdf") {
                options = new PDFSaveOptions();
                if (p.pdf_preset !== undefined) { options.pDFPreset = p.pdf_preset; }
                options.artboardRange = "1";
                options.viewAfterSaving = false;
                options.colorDownsampling = 0;
                options.grayscaleDownsampling = 0;
                options.preserveEditability = false;
                options.bleedLink = false;
                options.trimMarks = false;
                options.registrationMarks = false;
                options.colorBars = false;
                options.pageInformation = false;
                options.bleedOffsetRect = [0, 0, 0, 0];
                copy.saveAs(staged, options);
            } else if (format === "ai") {
                options = new IllustratorSaveOptions();
                options.pdfCompatible = true;
                options.compressed = true;
                copy.saveAs(staged, options);
            } else {
                options = new ExportOptionsSVG();
                options.embedRasterImages = true;
                options.coordinatePrecision = 4;
                options.preserveEditability = false;
                options.saveMultipleArtboards = false;
                copy.exportFile(new File(staged.fsName.replace(/\.svg$/i, "")), ExportType.SVG, options);
            }
            var result = commitOutput(staged, target, overwrite);
            result.document_id = p.document_id;
            result.artboard_index = index;
            result.format = format;
            result.export_method = "temporary_artwork_copy";
            result.copied_top_level_objects = state.copied_objects;
            result.skipped_hidden_or_nonprinting_layers = state.skipped_layers;
            result.source_path_changed = false;
            result.limitations = cloneLimitations();
            if (format === "pdf") {
                result.bleed_mm = bleed;
                result.pdf_preset = p.pdf_preset === undefined ? null : p.pdf_preset;
                result.requires_pdf_finalize = true;
                result.trim_width_pt = bounds[2] - bounds[0];
                result.trim_height_pt = bounds[1] - bounds[3];
                result.bleed_pt = margin;
                result.geometry_method = "expanded_artboard_with_verified_pdf_boxes";
                result.limitations.push("This PDF is a print copy without Illustrator-specific editability; use native AI save to preserve the full editable document.");
            }
            return result;
        } finally {
            if (state.document) { try { state.document.close(SaveOptions.DONOTSAVECHANGES); } catch (ignoredClose) {} }
            try { app.userInteractionLevel = interaction; } catch (ignoredInteraction) {}
            restoreFocus(previous);
            if (staged.exists) { try { staged.remove(); } catch (ignoredFile) {} }
        }
    };

    function imagePixels(file) {
        var data = "";
        try {
            file.encoding = "BINARY";
            if (!file.open("r")) { return null; }
            data = file.read(1048576);
        } catch (ignoredRead) { return null; }
        finally { try { file.close(); } catch (ignoredClose) {} }
        function readByte(at) { return data.charCodeAt(at) & 255; }
        function big32(at) { return readByte(at) * 16777216 + readByte(at + 1) * 65536 + readByte(at + 2) * 256 + readByte(at + 3); }
        if (data.length >= 24 && readByte(0) === 137 && data.substr(1, 3) === "PNG" && data.substr(12, 4) === "IHDR") {
            return {width: big32(16), height: big32(20), format: "png"};
        }
        if (data.length < 4 || readByte(0) !== 255 || readByte(1) !== 216) { return null; }
        var at = 2, marker, size;
        while (at + 9 < data.length) {
            if (readByte(at) !== 255) { return null; }
            while (at < data.length && readByte(at) === 255) { at++; }
            marker = readByte(at++);
            if (marker === 217 || marker === 218) { return null; }
            if (marker === 1 || (marker >= 208 && marker <= 215)) { continue; }
            size = readByte(at) * 256 + readByte(at + 1);
            if (size < 2 || at + size > data.length) { return null; }
            if ((marker >= 192 && marker <= 195) || (marker >= 197 && marker <= 199) || (marker >= 201 && marker <= 203) || (marker >= 205 && marker <= 207)) {
                return {width: readByte(at + 5) * 256 + readByte(at + 6), height: readByte(at + 3) * 256 + readByte(at + 4), format: "jpeg"};
            }
            at += size;
        }
        return null;
    }
    function effectivePpi(item, pixels) {
        var box = item.boundingBox, m = item.matrix;
        var width = Math.abs(box[2] - box[0]) * Math.sqrt(m.mValueA * m.mValueA + m.mValueB * m.mValueB);
        var height = Math.abs(box[1] - box[3]) * Math.sqrt(m.mValueC * m.mValueC + m.mValueD * m.mValueD);
        if (width <= 0 || height <= 0 || pixels.width <= 0 || pixels.height <= 0) { return null; }
        return {x: Math.round(pixels.width * 72 / width), y: Math.round(pixels.height * 72 / height)};
    }
    function shortItem(item) {
        var id = null, name = "";
        try { id = String(item.uuid); name = String(item.name); } catch (ignored) {}
        return {id: id, name: name};
    }
    function nonprintingTextLayers(item) {
        var parent = item, names = [];
        while (parent && parent.typename !== "Document") {
            if (parent.typename === "Layer") {
                if (!parent.visible) { return []; }
                if (!parent.printable) { names.push(String(parent.name)); }
            } else if (parent.hidden) { return []; }
            parent = parent.parent;
        }
        return names;
    }
    A.ops.preflight_document = function (p) {
        var document = A.doc(p.document_id), threshold = p.min_effective_ppi === undefined ? 250 : A.number(p.min_effective_ppi, "min_effective_ppi", 1, 2400);
        var result = {document: A.documentInfo(document), advisory_only: true, certified_pdfx_validation: false, issues: [], artboards: [], empty_text: [], nonprinting_text: [], missing_links: [], low_resolution_images: [], overprint_objects: [], image_resolution_unknown: [], min_effective_ppi: threshold};
        var i, item, info, file, pixels, ppi, rect, capped = false, limit = 20000;
        for (i = 0; i < document.artboards.length; i++) {
            rect = document.artboards[i].artboardRect;
            result.artboards.push({index: i, name: String(document.artboards[i].name), width_mm: (rect[2] - rect[0]) * 25.4 / 72, height_mm: (rect[1] - rect[3]) * 25.4 / 72});
        }
        for (i = 0; i < document.textFrames.length && i < limit; i++) {
            item = document.textFrames[i];
            if (String(item.contents).replace(/\s/g, "").length === 0) { result.empty_text.push(shortItem(item)); }
            else {
                var nonprinting = nonprintingTextLayers(item);
                if (nonprinting.length) {
                    info = shortItem(item); info.nonprinting_layers = nonprinting;
                    result.nonprinting_text.push(info);
                }
            }
        }
        if (document.textFrames.length > limit) { capped = true; }
        for (i = 0; i < document.placedItems.length && i < limit; i++) {
            item = document.placedItems[i]; info = shortItem(item); file = null;
            try { file = item.file; } catch (ignoredLink) {}
            if (!file || !file.exists) { info.path = file ? file.fsName : null; result.missing_links.push(info); continue; }
            pixels = imagePixels(file); ppi = null;
            if (pixels) { try { ppi = effectivePpi(item, pixels); } catch (ignoredGeometry) {} }
            if (!ppi) { info.reason = "Source pixel dimensions or transformed geometry could not be verified (only linked PNG/JPEG are measured)."; result.image_resolution_unknown.push(info); }
            else if (Math.min(ppi.x, ppi.y) < threshold) { info.effective_ppi = ppi; info.path = file.fsName; result.low_resolution_images.push(info); }
        }
        if (document.placedItems.length > limit) { capped = true; }
        for (i = 0; i < document.rasterItems.length && i < limit; i++) {
            info = shortItem(document.rasterItems[i]); info.reason = "Embedded raster pixel dimensions are not exposed reliably by this check.";
            result.image_resolution_unknown.push(info);
        }
        if (document.rasterItems.length > limit) { capped = true; }
        for (i = 0; i < document.pathItems.length && i < limit; i++) {
            item = document.pathItems[i];
            try {
                if ((item.filled && item.fillOverprint) || (item.stroked && item.strokeOverprint)) {
                    info = shortItem(item); info.fill = item.filled && item.fillOverprint; info.stroke = item.stroked && item.strokeOverprint; result.overprint_objects.push(info);
                }
            } catch (ignoredOverprint) {}
        }
        if (document.pathItems.length > limit) { capped = true; }
        if (result.empty_text.length) { result.issues.push({code: "EMPTY_TEXT", count: result.empty_text.length, severity: "warning"}); }
        if (result.nonprinting_text.length) { result.issues.push({code: "NONPRINTING_TEXT", count: result.nonprinting_text.length, severity: "error", message: "Visible nonempty text is inside a nonprinting layer and will be omitted from print/PDF export."}); }
        if (result.missing_links.length) { result.issues.push({code: "MISSING_LINKS", count: result.missing_links.length, severity: "error"}); }
        if (result.low_resolution_images.length) { result.issues.push({code: "LOW_EFFECTIVE_PPI", count: result.low_resolution_images.length, severity: "warning"}); }
        if (result.overprint_objects.length) { result.issues.push({code: "OVERPRINT_REQUIRES_REVIEW", count: result.overprint_objects.length, severity: "info"}); }
        result.scan_truncated = capped;
        result.status = result.issues.length ? "review_required" : "no_issues_in_completed_checks";
        result.unverified_checks = ["Missing or substituted fonts", "Overset text", "Color-profile/output-intent correctness", "Bleed artwork coverage", "Text and plugin-specific overprint", "Trapping, separations, transparency flattening, and PDF/X compliance"];
        if (result.image_resolution_unknown.length) { result.unverified_checks.push("Effective PPI for images listed under image_resolution_unknown"); }
        if (capped) { result.unverified_checks.push("Items beyond the per-type scan limit of 20000"); }
        return result;
    };
})(Illona);
