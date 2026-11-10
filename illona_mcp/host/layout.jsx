/* Illona composition workflows. All artwork stays editable. ES3 / ExtendScript. */
(function (A) {
    var PT = 72 / 25.4;

    function number(p, key, fallback, min, max) {
        var value = p[key] === undefined ? fallback : p[key];
        return A.number(value, key, min, max);
    }
    function text(value, fallback, limit) {
        value = value === undefined ? fallback : value;
        return A.string(value, "text", limit || 10000, true);
    }
    function palette(p) {
        var source = p.palette || {}, result, i;
        if (source instanceof Array) {
            result = {ink: source[0] || "#173E48", accent: source[1] || "#DF765F", paper: source[2] || "#F5F0E6", leaf: source[3] || "#779481", light: source[4] || "#D9DFCE"};
        } else {
            A.object(source, "palette");
            result = {ink: source.ink || source.navy || "#173E48", accent: source.accent || source.coral || "#DF765F", paper: source.paper || source.cream || "#F5F0E6", leaf: source.leaf || "#779481", light: source.light || "#D9DFCE"};
        }
        for (i in result) { if (result.hasOwnProperty(i)) { A.color(result[i]); } }
        return result;
    }
    function context(document, colors) {
        return {doc: document, board: 0, colors: colors, paths: 0, textFrames: 0, serial: 0, warnings: []};
    }
    function point(c, x, y) {
        var r = c.doc.artboards[c.board].artboardRect;
        return [r[0] + x * PT, r[1] - y * PT];
    }
    function appearance(c, item, name, fill, stroke, width, opacity) {
        item.name = "ILLONA / " + name + " / " + (++c.serial);
        /* New Illustrator paths can inherit the current document appearance. */
        item.opacity = opacity === undefined ? 100 : opacity;
        item.blendingMode = BlendModes.NORMAL;
        item.fillOverprint = false; item.strokeOverprint = false;
        item.strokeDashes = []; item.strokeDashOffset = 0;
        item.strokeCap = StrokeCap.BUTTENDCAP; item.strokeJoin = StrokeJoin.MITERENDJOIN;
        item.strokeMiterLimit = 4;
        item.filled = fill !== null && fill !== undefined;
        if (item.filled) { item.fillColor = A.color(fill); }
        item.stroked = stroke !== null && stroke !== undefined;
        if (item.stroked) { item.strokeColor = A.color(stroke); item.strokeWidth = width === undefined ? 1.4 : width; }
        c.paths++;
        return item;
    }
    /* Points are [x,y] or [x,y,leftX,leftY,rightX,rightY], in mm, y down. */
    function path(c, parent, name, points, fill, stroke, width, closed, opacity) {
        var item = parent.pathItems.add(), anchors = [], i, p, pp;
        for (i = 0; i < points.length; i++) { anchors.push(point(c, points[i][0], points[i][1])); }
        item.setEntirePath(anchors);
        for (i = 0; i < points.length; i++) {
            p = points[i]; pp = item.pathPoints[i];
            if (p.length === 6) { pp.leftDirection = point(c, p[2], p[3]); pp.rightDirection = point(c, p[4], p[5]); }
            pp.pointType = PointType.CORNER;
        }
        item.closed = !!closed;
        return appearance(c, item, name, fill, stroke, width, opacity);
    }
    function rect(c, parent, name, x, y, width, height, fill, stroke, lineWidth, opacity) {
        var p = point(c, x, y), item = parent.pathItems.rectangle(p[1], p[0], width * PT, height * PT);
        return appearance(c, item, name, fill, stroke, lineWidth, opacity);
    }
    function ellipse(c, parent, name, x, y, width, height, fill, stroke, lineWidth, opacity) {
        var p = point(c, x, y), item = parent.pathItems.ellipse(p[1], p[0], width * PT, height * PT);
        return appearance(c, item, name, fill, stroke, lineWidth, opacity);
    }
    function line(c, parent, name, x1, y1, x2, y2, color, width, opacity) {
        return path(c, parent, name, [[x1, y1], [x2, y2]], null, color, width, false, opacity);
    }
    function layer(document, name) { var item = document.layers.add(); item.name = name; return item; }
    function group(parent, name) { var item = parent.groupItems.add(); item.name = name; return item; }
    function fonts(p, warnings) {
        function find(requested, candidates, role) {
            var i;
            if (requested !== undefined) {
                A.string(requested, role + " font", 200, false);
                try { return app.textFonts.getByName(requested); } catch (ignored) {
                    warnings.push("Fontul " + requested + " nu este instalat; am folosit un font disponibil pentru " + role + ".");
                }
            }
            for (i = 0; i < candidates.length; i++) { try { return app.textFonts.getByName(candidates[i]); } catch (ignoredCandidate) {} }
            if (!app.textFonts.length) { A.fail("FONT_NOT_FOUND", "No fonts are available in Illustrator."); }
            return app.textFonts[0];
        }
        return {
            body: find(p.font, ["AvenirNext-Regular", "Helvetica", "ArialMT", "MyriadPro-Regular"], "body"),
            heading: find(p.heading_font, ["AvenirNext-DemiBold", "Helvetica-Bold", "Arial-BoldMT", "MyriadPro-Bold"], "heading")
        };
    }
    function estimatedLines(contents, widthMM, sizePT) {
        /* Conservative character-width model; this is not a native overset detector. */
        var paragraphs = contents.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
        var capacity = Math.max(1, Math.floor(widthMM * PT / (sizePT * 0.58))), lines = 0, i, j, words, used;
        for (i = 0; i < paragraphs.length; i++) {
            words = paragraphs[i].split(/\s+/); used = 0; lines++;
            for (j = 0; j < words.length; j++) {
                if (!words[j].length) { continue; }
                if (words[j].length > capacity) {
                    if (used) { lines++; used = 0; }
                    lines += Math.floor((words[j].length - 1) / capacity);
                    used = words[j].length % capacity || capacity;
                } else if (used && used + 1 + words[j].length > capacity) {
                    lines++; used = words[j].length;
                } else { used += (used ? 1 : 0) + words[j].length; }
            }
        }
        return lines;
    }
    function areaText(c, parent, name, contents, x, y, width, height, style) {
        var size = style.size, min = style.min || size, leading = style.leading || 1.4;
        var lines, capacity, p = point(c, x, y), framePath, frame, attributes;
        contents = text(contents, "", 15000);
        while (true) {
            lines = estimatedLines(contents, width, size);
            capacity = Math.max(1, Math.floor((height * PT - size * 0.15) / (size * leading)));
            if (lines <= capacity || size <= min) { break; }
            size = Math.max(min, size - 0.5);
        }
        if (lines > capacity) { c.warnings.push(name + ": textul poate depăși caseta; conținutul integral este păstrat pentru ajustare manuală."); }
        framePath = parent.pathItems.rectangle(p[1], p[0], width * PT, height * PT);
        framePath.filled = false; framePath.stroked = false; framePath.opacity = 100;
        frame = c.doc.textFrames.areaText(framePath, TextOrientation.HORIZONTAL);
        /* Illustrator may create area text on the active layer, independently
           of the source path's parent. Keep printable copy on its requested
           typography layer/group rather than the nonprinting Guides layer. */
        frame.move(parent, ElementPlacement.PLACEATEND);
        frame.name = "ILLONA / " + name;
        frame.opacity = 100; frame.blendingMode = BlendModes.NORMAL;
        frame.contents = contents.replace(/\r\n/g, "\r").replace(/\n/g, "\r");
        attributes = frame.textRange.characterAttributes;
        attributes.textFont = style.font; attributes.size = size;
        attributes.fillColor = A.color(style.color); attributes.autoLeading = false; attributes.leading = size * leading;
        attributes.tracking = style.tracking === undefined ? 0 : style.tracking;
        attributes.horizontalScale = 100; attributes.verticalScale = 100; attributes.baselineShift = 0;
        attributes.overprintFill = false;
        var paragraph = frame.textRange.paragraphAttributes;
        paragraph.hyphenation = false; paragraph.justification = Justification.LEFT;
        paragraph.leftIndent = 0; paragraph.rightIndent = 0; paragraph.firstLineIndent = 0;
        paragraph.spaceBefore = 0; paragraph.spaceAfter = 0;
        c.textFrames++;
        return {frame: frame, font_size_pt: size, estimated_lines: lines, estimated_capacity: capacity, fit_is_estimated: true};
    }
    function label(c, parent, name, contents, x, y, font, size, color, tracking) {
        var p = point(c, x, y), frame = parent.textFrames.add();
        frame.move(parent, ElementPlacement.PLACEATEND);
        frame.name = "ILLONA / " + name; frame.contents = contents;
        frame.opacity = 100; frame.blendingMode = BlendModes.NORMAL;
        var attributes = frame.textRange.characterAttributes;
        attributes.textFont = font; attributes.size = size; attributes.fillColor = A.color(color);
        attributes.tracking = tracking === undefined ? 0 : tracking;
        attributes.horizontalScale = 100; attributes.verticalScale = 100; attributes.baselineShift = 0;
        attributes.overprintFill = false;
        var paragraph = frame.textRange.paragraphAttributes;
        paragraph.justification = Justification.LEFT; paragraph.leftIndent = 0;
        paragraph.rightIndent = 0; paragraph.firstLineIndent = 0; paragraph.spaceBefore = 0; paragraph.spaceAfter = 0;
        /* Position is a bounding-box property: set it after changing font metrics. */
        frame.position = p;
        c.textFrames++;
        return frame;
    }
    function newDocument(p, width, height, defaultName, mode) {
        var info = A.ops.create_document({width: width, height: height, units: "mm", color_mode: mode || "RGB", name: text(p.name, defaultName, 200)});
        return A.doc(info.id);
    }
    function finish(c, extra) {
        var key, result = {document: A.documentInfo(c.doc), created_count: c.doc.pageItems.length, editable_path_count: c.paths, text_frame_count: c.textFrames, warnings: c.warnings};
        for (key in extra) { if (extra.hasOwnProperty(key)) { result[key] = extra[key]; } }
        try { c.doc.artboards.setActiveArtboardIndex(0); c.doc.selection = null; app.redraw(); } catch (ignored) {}
        return result;
    }
    function leaf(c, parent, name, x, y, length, breadth, degrees, fill, veinColor) {
        var angle = degrees * Math.PI / 180, dx = Math.cos(angle), dy = Math.sin(angle), px = -dy, py = dx;
        var tx = x + dx * length, ty = y + dy * length;
        var item = path(c, parent, name, [
            [x, y, x + dx * length * 0.38 - px * breadth, y + dy * length * 0.38 - py * breadth, x + dx * length * 0.38 + px * breadth, y + dy * length * 0.38 + py * breadth],
            [tx, ty, tx - dx * length * 0.32 + px * breadth, ty - dy * length * 0.32 + py * breadth, tx - dx * length * 0.32 - px * breadth, ty - dy * length * 0.32 - py * breadth]
        ], fill, null, 0, true);
        if (veinColor) { line(c, parent, name + " vein", x + dx * length * 0.1, y + dy * length * 0.1, tx - dx * length * 0.12, ty - dy * length * 0.12, veinColor, 0.45, 65); }
        return item;
    }
    function sprig(c, parent, name, x, y, scale, color, secondary) {
        var g = group(parent, name), i, stemX, stemY;
        path(c, g, "curved stem", [[x, y, x, y, x - 3 * scale, y - 13 * scale], [x + 2 * scale, y - 47 * scale, x - 1 * scale, y - 31 * scale, x + 2 * scale, y - 47 * scale]], null, color, 0.9, false);
        for (i = 0; i < 5; i++) {
            stemX = x + (i > 2 ? 0.8 * scale : -0.4 * scale); stemY = y - (8 + i * 7.5) * scale;
            leaf(c, g, "left leaf " + (i + 1), stemX, stemY, (17 - i) * scale, (3.3 - i * 0.2) * scale, -145 + i * 4, i % 2 ? secondary : color, null);
            leaf(c, g, "right leaf " + (i + 1), stemX, stemY - 2.5 * scale, (16 - i) * scale, (3.1 - i * 0.15) * scale, -43 - i * 3, i % 2 ? color : secondary, null);
        }
        leaf(c, g, "terminal leaf", x + 1.3 * scale, y - 43 * scale, 13 * scale, 2.7 * scale, -89, color, null);
        return g;
    }

    A.ops.plan_brochure = function (p) {
        var format = p.format === undefined ? "trifold" : p.format;
        if (format === "tri_fold") { format = "trifold"; }
        if (format !== "trifold" && format !== "bifold") { A.fail("INVALID_ARGUMENT", "format must be trifold or bifold."); }
        var width = number(p, "width_mm", 297, 120, 1000), height = number(p, "height_mm", 210, 80, 1000);
        var margin = number(p, "margin_mm", 6, 2, 40), bleed = number(p, "bleed_mm", 3, 0, 20);
        var compensation = number(p, "fold_compensation_mm", 2, 0, 15), count = format === "trifold" ? 3 : 2;
        var regular = format === "trifold" ? (width + compensation) / 3 : width / 2;
        var flap = format === "trifold" ? regular - compensation : regular;
        if (flap <= margin * 2 + 12 || height <= margin * 2 + 25) { A.fail("INVALID_ARGUMENT", "Panel dimensions are too small for the requested safe margin."); }
        var widths = format === "trifold" ? [[flap, regular, regular], [regular, regular, flap]] : [[regular, regular], [regular, regular]];
        var roles = format === "trifold" ? [["flap", "back_cover", "front_cover"], ["inside_left", "inside_middle", "inside_right"]] : [["back_cover", "front_cover"], ["inside_left", "inside_right"]];
        var panels = [], folds = [], side, i, x, sideFolds;
        for (side = 0; side < 2; side++) {
            x = 0; sideFolds = [];
            for (i = 0; i < count; i++) {
                panels.push({index: panels.length, side: side === 0 ? "outside" : "inside", artboard_index: side, role: roles[side][i], x_mm: x, y_mm: 0, width_mm: widths[side][i], height_mm: height, safe_mm: {x: x + margin, y: margin, width: widths[side][i] - margin * 2, height: height - margin * 2}});
                x += widths[side][i]; if (i < count - 1) { sideFolds.push(x); }
            }
            folds.push({side: side === 0 ? "outside" : "inside", artboard_index: side, x_mm: sideFolds});
        }
        return {format: format, trim_mm: {width: width, height: height}, margin_mm: margin, bleed_mm: bleed, fold_compensation_mm: format === "trifold" ? compensation : 0, panel_count: panels.length, panels: panels, folds: folds, panel_order: format === "trifold" ? ["outside_flap", "outside_back", "outside_front", "inside_left", "inside_middle", "inside_right"] : ["outside_back", "outside_front", "inside_left", "inside_right"], coordinates: "millimetres from each artboard's top-left; mirrored fold positions between sides", print_note: "Confirm the fold direction, compensation and duplex orientation with your printer before production."};
    };

    A.ops.create_brochure = function (p) {
        var plan = A.ops.plan_brochure(p), colors = palette(p), content = p.panels || [], i;
        if (!(content instanceof Array) || content.length > plan.panel_count) { A.fail("INVALID_ARGUMENT", "panels must be an array with at most " + plan.panel_count + " entries."); }
        for (i = 0; i < content.length; i++) {
            A.object(content[i], "panel"); text(content[i].title, "", 2000); text(content[i].body, "", 15000);
        }
        var doc = newDocument(p, plan.trim_mm.width, plan.trim_mm.height, "ILLONA - Editorial brochure", "CMYK");
        var c = context(doc, colors), faceFonts = fonts(p, c.warnings), width = plan.trim_mm.width, height = plan.trim_mm.height, b = plan.bleed_mm;
        var gap = Math.max(25, b * 2 + 10), first = doc.artboards[0].artboardRect;
        doc.artboards[0].name = "01 - Outside - back / front";
        doc.artboards.add([first[0] + (width + gap) * PT, first[1], first[0] + (width * 2 + gap) * PT, first[1] - height * PT]);
        doc.artboards[1].name = "02 - Inside - reading order";
        var backgrounds = layer(doc, "Background"), art = layer(doc, "Illustration"), typography = layer(doc, "Typography"), guides = layer(doc, "Guides");
        guides.printable = false;
        var defaults = {
            flap: {title: "O idee care\nprinde formă", body: "Un început clar pentru povestea ta.\n\nÎnlocuiește acest text cu o introducere scurtă: ce propui, pentru cine și de ce contează."},
            back_cover: {title: "Continuăm\npovestea", body: "Acest spațiu este pregătit pentru datele de contact, adresa web și următorul pas.\n\nTextele, culorile și ilustrațiile sunt editabile."},
            front_cover: {title: text(p.title, "Natură,\nîn echilibru", 2000), body: "Un concept editorial.\nO poveste spusă cu claritate."},
            inside_left: {title: "01 / Viziune", body: "Prezintă ideea principală într-un paragraf scurt și bine structurat.\n\nAdaugă un beneficiu concret, un detaliu util și o imagine care susține mesajul."},
            inside_middle: {title: "02 / Detalii", body: "Organizează aici informația de care cititorul are nevoie pentru a înțelege oferta sau proiectul.\n\nFolosește propoziții scurte și păstrează o singură idee în fiecare paragraf."},
            inside_right: {title: "03 / Mai departe", body: "Încheie cu o invitație clară și cu informațiile necesare pentru următorul pas.\n\nÎnlocuiește conținutul demonstrativ cu textul final înainte de livrare."}
        };
        var panel, item, titleValue, bodyValue, cover, outside, fill, ink, mx, usableWidth, headingTop, headingHeight, bodyTop, bodyHeight, titleFit, bodyFit, fitResults = [], safe, guide, f;
        for (i = 0; i < 2; i++) {
            c.board = i; rect(c, backgrounds, "full bleed paper " + i, -b, -b, width + b * 2, height + b * 2, colors.paper, null);
            guide = rect(c, guides, "trim " + i, 0, 0, width, height, null, colors.accent, 0.25); guide.guides = true;
            guide = rect(c, guides, "bleed " + i, -b, -b, width + b * 2, height + b * 2, null, colors.accent, 0.25); guide.guides = true;
            for (f = 0; f < plan.folds[i].x_mm.length; f++) { guide = line(c, guides, "fold " + i + " / " + f, plan.folds[i].x_mm[f], 0, plan.folds[i].x_mm[f], height, colors.ink, 0.25); guide.guides = true; }
        }
        for (i = 0; i < plan.panels.length; i++) {
            panel = plan.panels[i]; c.board = panel.artboard_index; outside = panel.side === "outside"; cover = panel.role === "front_cover";
            item = content[i] || {}; titleValue = text(item.title, defaults[panel.role].title, 2000); bodyValue = text(item.body, defaults[panel.role].body, 15000);
            fill = cover ? colors.ink : (panel.role === "flap" ? colors.accent : colors.paper); ink = cover ? colors.paper : colors.ink;
            rect(c, backgrounds, "panel " + panel.role, panel.x_mm, -b, panel.width_mm, height + b * 2, fill, null);
            /* Extend outermost edge panels into bleed, keeping the fold positions exact. */
            if (panel.x_mm === 0 && fill !== colors.paper) { rect(c, backgrounds, "left bleed " + panel.role, -b, -b, b, height + 2 * b, fill, null); }
            if (Math.abs(panel.x_mm + panel.width_mm - width) < 0.01 && fill !== colors.paper) { rect(c, backgrounds, "right bleed " + panel.role, width, -b, b, height + 2 * b, fill, null); }
            mx = Math.max(plan.margin_mm, panel.width_mm * 0.09); usableWidth = panel.width_mm - mx * 2;
            safe = panel.safe_mm; guide = rect(c, guides, "safe " + panel.role, safe.x, safe.y, safe.width, safe.height, null, colors.leaf, 0.25); guide.guides = true;
            label(c, typography, "eyebrow " + panel.role, cover ? "ILLONA / EDITORIAL" : (outside ? "DESCHIDE / DESCOPERĂ" : "POVESTEA / " + (i - (plan.panel_count / 2) + 1)), panel.x_mm + mx, Math.max(mx, 12), faceFonts.body, 7, ink, 130);
            headingTop = cover ? height * 0.24 : height * 0.19; headingHeight = cover ? height * 0.23 : height * 0.19;
            titleFit = areaText(c, typography, "headline " + panel.role, titleValue, panel.x_mm + mx, headingTop, usableWidth, headingHeight, {font: faceFonts.heading, size: cover ? 28 : 19, min: 14, leading: 1.08, color: ink});
            line(c, art, "editorial rule " + panel.role, panel.x_mm + mx, headingTop + headingHeight + 3, panel.x_mm + mx + usableWidth * 0.28, headingTop + headingHeight + 3, cover ? colors.accent : colors.ink, 1.1);
            bodyTop = headingTop + headingHeight + 11; bodyHeight = Math.max(28, height * 0.81 - bodyTop);
            bodyFit = areaText(c, typography, "body " + panel.role, bodyValue, panel.x_mm + mx, bodyTop, usableWidth, bodyHeight, {font: faceFonts.body, size: cover ? 10.5 : 9.5, min: 8.5, leading: 1.48, color: ink});
            fitResults.push({panel_index: i, role: panel.role, headline_font_size_pt: titleFit.font_size_pt, body_font_size_pt: bodyFit.font_size_pt, body_estimated_lines: bodyFit.estimated_lines, body_estimated_capacity: bodyFit.estimated_capacity, fit_is_estimated: true});
            if (cover) {
                sprig(c, art, "Cover / botanical illustration", panel.x_mm + panel.width_mm * 0.68, height * 0.985, Math.min(panel.width_mm / 100, height / 210) * 0.64, colors.leaf, colors.accent);
            } else if (panel.side === "inside") {
                ellipse(c, art, "small botanical sun " + panel.role, panel.x_mm + panel.width_mm - mx - 19, height * 0.86, 15, 15, colors.accent, null, 0, 75);
                leaf(c, art, "editorial leaf " + panel.role, panel.x_mm + mx, height * 0.93, Math.min(usableWidth * 0.6, 35), 5, -18, colors.leaf, colors.paper);
            }
            label(c, typography, "folio " + panel.role, cover ? "ILLONA" : ("0" + (i + 1)), panel.x_mm + mx, height - Math.max(plan.margin_mm, 9), faceFonts.body, 7, ink, 70);
        }
        guides.locked = true;
        c.warnings.push("Încadrarea textelor este estimată conservator; verifică vizual casetele înainte de tipar.");
        if (!p.panels || p.panels.length < plan.panel_count) { c.warnings.push("Panourile fără conținut furnizat conțin texte demonstrative editabile."); }
        c.warnings.push("Fundalurile includ bleed geometric. La exportul PDF setează explicit bleed-ul și confirmă pliurile cu tipografia.");
        return finish(c, {layout: plan, text_fit: fitResults, fonts: {body: faceFonts.body.name, heading: faceFonts.heading.name}, bleed_background_extended: true, guide_layer: "Guides", source_documents_untouched: true});
    };

    A.ops.create_icon_set = function (p) {
        var width = number(p, "width_mm", 210, 150, 600), height = number(p, "height_mm", 160, 120, 600), colors = palette(p);
        var names = p.labels || ["Natură", "Lumină", "Relief", "Apă", "Direcție", "Creștere"], i;
        if (!(names instanceof Array) || names.length > 6) { A.fail("INVALID_ARGUMENT", "labels must contain at most six strings."); }
        for (i = 0; i < names.length; i++) { A.string(names[i], "icon label", 120, true); }
        var doc = newDocument(p, width, height, "ILLONA - Botanical icon collection", "RGB"), c = context(doc, colors), fs = fonts(p, c.warnings);
        var bg = layer(doc, "Background"), icons = layer(doc, "Icons - editable vectors"), type = layer(doc, "Typography");
        rect(c, bg, "paper", 0, 0, width, height, colors.paper, null);
        areaText(c, type, "collection title", text(p.title, "Forme din natură", 300), 14, 11, width - 28, 15, {font: fs.heading, size: 21, min: 16, leading: 1.1, color: colors.ink});
        label(c, type, "collection subtitle", "ILLONA / VECTOR ICON COLLECTION / 01", 14, 32, fs.body, 7, colors.ink, 95);
        var left = 14, top = 42, gap = 5, cellW = (width - 28 - gap * 2) / 3, cellH = (height - top - 12 - gap) / 2;
        var cx, cy, cellX, cellY, g, a, radians, scale = Math.min(cellW / 55, cellH / 45), ids = [], labelText;
        for (i = 0; i < 6; i++) {
            cellX = left + (i % 3) * (cellW + gap); cellY = top + Math.floor(i / 3) * (cellH + gap);
            rect(c, bg, "icon card " + (i + 1), cellX, cellY, cellW, cellH, "#FFFFFF", null, 0, 58);
            cx = cellX + cellW / 2; cy = cellY + cellH * 0.43;
            g = group(icons, "ILLONA / icon " + (i + 1) + " / " + ["leaf", "sun", "mountain", "water", "compass", "sprout"][i]);
            if (i === 0) {
                leaf(c, g, "leaf silhouette", cx - 9 * scale, cy + 8 * scale, 27 * scale, 8 * scale, -43, colors.leaf, colors.paper);
                path(c, g, "leaf petiole", [[cx - 12 * scale, cy + 11 * scale], [cx + 7 * scale, cy - 7 * scale]], null, colors.ink, 1.3, false);
            } else if (i === 1) {
                ellipse(c, g, "sun disc", cx - 5.5 * scale, cy - 5.5 * scale, 11 * scale, 11 * scale, colors.accent, null);
                for (a = 0; a < 8; a++) { radians = a * Math.PI / 4; line(c, g, "sun ray " + a, cx + Math.cos(radians) * 8.5 * scale, cy + Math.sin(radians) * 8.5 * scale, cx + Math.cos(radians) * 12 * scale, cy + Math.sin(radians) * 12 * scale, colors.ink, 1.4); }
            } else if (i === 2) {
                path(c, g, "mountain rear", [[cx - 13 * scale, cy + 9 * scale], [cx - 2 * scale, cy - 10 * scale], [cx + 5 * scale, cy + 2 * scale], [cx + 10 * scale, cy - 6 * scale], [cx + 17 * scale, cy + 9 * scale]], null, colors.ink, 1.5, false);
                path(c, g, "mountain snow", [[cx - 6 * scale, cy - 3 * scale], [cx - 2 * scale, cy - 10 * scale], [cx + 2 * scale, cy - 3 * scale], [cx - 1 * scale, cy - 4 * scale], [cx - 3 * scale, cy - 2 * scale]], colors.accent, null, 0, true);
                line(c, g, "mountain ground", cx - 15 * scale, cy + 9 * scale, cx + 18 * scale, cy + 9 * scale, colors.ink, 1.5);
            } else if (i === 3) {
                for (a = 0; a < 3; a++) { path(c, g, "wave " + a, [[cx - 15 * scale, cy + (a * 6 - 7) * scale, cx - 15 * scale, cy + (a * 6 - 7) * scale, cx - 10 * scale, cy + (a * 6 - 14) * scale], [cx, cy + (a * 6 - 7) * scale, cx - 5 * scale, cy + (a * 6 - 1) * scale, cx + 5 * scale, cy + (a * 6 - 13) * scale], [cx + 15 * scale, cy + (a * 6 - 7) * scale, cx + 10 * scale, cy + (a * 6 - 1) * scale, cx + 15 * scale, cy + (a * 6 - 7) * scale]], null, a === 1 ? colors.accent : colors.ink, 1.8, false); }
            } else if (i === 4) {
                ellipse(c, g, "compass ring", cx - 11 * scale, cy - 11 * scale, 22 * scale, 22 * scale, null, colors.ink, 1.4);
                path(c, g, "compass north", [[cx - 3 * scale, cy + 2 * scale], [cx + 6 * scale, cy - 7 * scale], [cx + 2 * scale, cy + 3 * scale]], colors.accent, null, 0, true);
                path(c, g, "compass south", [[cx - 3 * scale, cy + 2 * scale], [cx - 6 * scale, cy + 7 * scale], [cx + 2 * scale, cy + 3 * scale]], colors.ink, null, 0, true);
                ellipse(c, g, "compass pivot", cx - 1 * scale, cy - 1 * scale, 2 * scale, 2 * scale, colors.paper, null);
            } else {
                path(c, g, "sprout stem", [[cx, cy + 5 * scale, cx, cy + 5 * scale, cx - 1 * scale, cy - 1 * scale], [cx, cy - 9 * scale, cx + 1 * scale, cy - 5 * scale, cx, cy - 9 * scale]], null, colors.ink, 1.4, false);
                leaf(c, g, "sprout left", cx, cy - 2 * scale, 14 * scale, 4 * scale, -145, colors.leaf, null);
                leaf(c, g, "sprout right", cx, cy - 5 * scale, 14 * scale, 4 * scale, -37, colors.accent, null);
                path(c, g, "planter", [[cx - 8 * scale, cy + 5 * scale], [cx + 8 * scale, cy + 5 * scale], [cx + 6 * scale, cy + 13 * scale], [cx - 6 * scale, cy + 13 * scale]], null, colors.ink, 1.4, true);
            }
            labelText = names[i] === undefined ? ["Natură", "Lumină", "Relief", "Apă", "Direcție", "Creștere"][i] : names[i];
            areaText(c, type, "icon label " + (i + 1), labelText, cellX + 5, cellY + cellH - 11, cellW - 10, 8, {font: fs.body, size: 9, min: 7.5, leading: 1.1, color: colors.ink});
            ids.push({name: g.name, id: String(g.uuid), label: labelText});
        }
        return finish(c, {icons: ids, grid: {columns: 3, rows: 2}, style: {palette: colors, stroke_width_pt: "1.3-1.8", native_editable_vectors: true}, fonts: {body: fs.body.name, heading: fs.heading.name}, source_documents_untouched: true});
    };

    A.ops.create_illustration = function (p) {
        var width = number(p, "width_mm", 240, 120, 1000), height = number(p, "height_mm", 180, 100, 1000), colors = palette(p);
        var theme = p.theme === undefined ? "botanical" : p.theme;
        if (theme !== "botanical" && theme !== "landscape") { A.fail("INVALID_ARGUMENT", "theme must be botanical or landscape."); }
        if (p.title !== undefined) { text(p.title, "", 400); }
        var doc = newDocument(p, width, height, "ILLONA - Botanical landscape", "RGB"), c = context(doc, colors), fs = fonts(p, c.warnings);
        var bg = layer(doc, "Background"), atmosphere = layer(doc, "Atmosphere"), landscape = layer(doc, "Landscape - Bezier contours"), plants = layer(doc, "Botanical - editable branches"), type = layer(doc, "Typography");
        rect(c, bg, "warm paper", 0, 0, width, height, colors.paper, null);
        ellipse(c, atmosphere, "sun halo", width * 0.665, height * 0.105, height * 0.39, height * 0.39, colors.accent, null, 0, 13);
        var sun = ellipse(c, atmosphere, "sun", width * 0.705, height * 0.16, height * 0.265, height * 0.265, colors.accent, null);
        var gradientUsed = false, gradient, gradientColor;
        try {
            gradient = doc.gradients.add(); gradient.name = "ILLONA - Sunlight"; gradient.type = GradientType.RADIAL;
            gradient.gradientStops[0].rampPoint = 0; gradient.gradientStops[0].color = A.color(colors.paper);
            gradient.gradientStops[1].rampPoint = 100; gradient.gradientStops[1].color = A.color(colors.accent);
            gradientColor = new GradientColor(); gradientColor.gradient = gradient; sun.fillColor = gradientColor; gradientUsed = true;
        } catch (gradientError) { c.warnings.push("Gradientul radial nu a putut fi aplicat; discul solar păstrează culoarea editabilă."); }
        /* Sculpted silhouettes are real cubic Bezier paths, not raster images. */
        path(c, landscape, "distant ridge", [
            [0, height * 0.57, 0, height * 0.57, width * 0.13, height * 0.39],
            [width * 0.29, height * 0.5, width * 0.15, height * 0.34, width * 0.39, height * 0.62],
            [width * 0.58, height * 0.45, width * 0.44, height * 0.5, width * 0.73, height * 0.27],
            [width, height * 0.48, width * 0.88, height * 0.36, width, height * 0.48],
            [width, height], [0, height]
        ], colors.light, null, 0, true);
        path(c, landscape, "sage rolling hills", [
            [0, height * 0.64, 0, height * 0.64, width * 0.16, height * 0.48],
            [width * 0.38, height * 0.61, width * 0.21, height * 0.48, width * 0.53, height * 0.73],
            [width * 0.72, height * 0.58, width * 0.56, height * 0.62, width * 0.87, height * 0.47],
            [width, height * 0.62, width * 0.93, height * 0.56, width, height * 0.62],
            [width, height], [0, height]
        ], colors.leaf, null, 0, true);
        path(c, landscape, "river ribbon", [
            [width * 0.55, height * 0.57, width * 0.55, height * 0.57, width * 0.73, height * 0.66],
            [width * 0.48, height * 0.77, width * 0.7, height * 0.7, width * 0.25, height * 0.86],
            [width * 0.67, height, width * 0.43, height * 0.93, width * 0.67, height],
            [width * 0.89, height, width * 0.89, height, width * 0.57, height * 0.85],
            [width * 0.58, height * 0.79, width * 0.39, height * 0.87, width * 0.79, height * 0.7],
            [width * 0.55, height * 0.57, width * 0.73, height * 0.65, width * 0.55, height * 0.57]
        ], colors.paper, null, 0, true);
        path(c, landscape, "foreground dark bank", [
            [0, height * 0.85, 0, height * 0.85, width * 0.13, height * 0.72],
            [width * 0.3, height * 0.88, width * 0.19, height * 0.77, width * 0.43, height * 0.98],
            [width * 0.56, height, width * 0.48, height * 0.97, width * 0.56, height], [0, height]
        ], colors.ink, null, 0, true);
        /* Contours add a restrained editorial rhythm to the illustration. */
        var i, offset, stemColor = colors.ink, plantScale = Math.min(width / 240, height / 180);
        for (i = 0; i < 5; i++) {
            offset = i * height * 0.012;
            path(c, landscape, "terrain contour " + (i + 1), [[width * 0.03, height * 0.665 + offset, width * 0.03, height * 0.665 + offset, width * 0.14, height * 0.58 + offset], [width * 0.34, height * 0.66 + offset, width * 0.22, height * 0.6 + offset, width * 0.34, height * 0.66 + offset]], null, colors.paper, 0.55, false, 36);
        }
        sprig(c, plants, "left botanical branch", width * 0.12, height * 0.98, plantScale * (theme === "botanical" ? 1.8 : 1.3), colors.ink, colors.leaf);
        sprig(c, plants, "right botanical branch", width * 0.9, height * 1.02, plantScale * (theme === "botanical" ? 1.7 : 1.15), colors.ink, colors.accent);
        sprig(c, plants, "foreground accent branch", width * 0.31, height * 1.08, plantScale * 1.05, colors.accent, colors.light);
        /* Small seed heads are grouped editable native paths. */
        var seeds = group(plants, "ILLONA / seed heads"), seedX, seedY, j, theta;
        for (i = 0; i < 3; i++) {
            seedX = width * (0.68 + i * 0.055); seedY = height * (0.83 - i * 0.045);
            path(c, seeds, "seed stem " + i, [[seedX - 3 * plantScale, height, seedX - 3 * plantScale, height, seedX + 3 * plantScale, height * 0.9], [seedX, seedY, seedX + 1 * plantScale, seedY + 6 * plantScale, seedX, seedY]], null, colors.ink, 0.8, false);
            for (j = 0; j < 7; j++) {
                theta = -Math.PI + j * Math.PI / 6;
                line(c, seeds, "seed ray " + i + " / " + j, seedX, seedY, seedX + Math.cos(theta) * 7 * plantScale, seedY + Math.sin(theta) * 7 * plantScale, colors.ink, 0.6);
                ellipse(c, seeds, "seed cap " + i + " / " + j, seedX + Math.cos(theta) * 7 * plantScale - 0.7 * plantScale, seedY + Math.sin(theta) * 7 * plantScale - 0.7 * plantScale, 1.4 * plantScale, 1.4 * plantScale, colors.accent, null);
            }
        }
        /* Deterministic stippling: reproducible, vector and intentionally sparse. */
        var seed = 117, rx, ry, radius;
        for (i = 0; i < 36; i++) {
            seed = (seed * 9301 + 49297) % 233280; rx = seed / 233280;
            seed = (seed * 9301 + 49297) % 233280; ry = seed / 233280;
            radius = (0.22 + (i % 3) * 0.09) * plantScale;
            ellipse(c, atmosphere, "paper fleck " + i, width * (0.1 + rx * 0.8), height * (0.08 + ry * 0.48), radius, radius, colors.ink, null, 0, 16);
        }
        if (p.title !== undefined && p.title.length) {
            areaText(c, type, "illustration title", p.title, width * 0.07, height * 0.09, width * 0.48, height * 0.23, {font: fs.heading, size: Math.min(34, width * 0.13), min: 17, leading: 1.07, color: colors.ink});
            label(c, type, "illustration caption", "ILLONA / BOTANICAL STUDY", width * 0.073, height * 0.36, fs.body, 7, colors.ink, 130);
        }
        return finish(c, {theme: theme, native_editable_vectors: true, radial_gradient_applied: gradientUsed, palette: colors, layers: ["Background", "Atmosphere", "Landscape - Bezier contours", "Botanical - editable branches", "Typography"], source_documents_untouched: true});
    };
})(Illona);
