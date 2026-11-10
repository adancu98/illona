/* The IE3 helpers precede this file inside a private function scope.
 * Scripts come exclusively from the pinned adapter, never from an MCP argument.
 * This body is also valid standalone ES3 for syntax verification. */
function illonaRunIe3(_illonaRequest) {
var _illonaCaptured = null;
var _illonaHasResult = false;
var PARAMS_PATH = "illona:in-memory-params";
var RESULT_PATH = "illona:in-memory-result";

readParamsFile = function () { return _illonaRequest.params; };
writeResultFile = function (ignoredPath, value) {
    if (value && typeof value === "object" && !(value instanceof Array)) {
        if (_versionWarning) {
            if (!(value.warnings instanceof Array)) { value.warnings = []; }
            value.warnings.push(_versionWarning);
        }
    }
    _illonaCaptured = value;
    _illonaHasResult = true;
};

/* Use Illustrator's UUIDs throughout both tool families. Reading never adds
 * IDs to user notes, and duplicated items already receive distinct native IDs. */
ensureUUID = function (item) { return String(item.uuid); };
reassignUUID = function (item) { return String(item.uuid); };
reassignUUIDDeep = function (item) { return []; };
getUUIDDuplicates = function () { return []; };
findItemByUUID = function (id) {
    try { return Illona.findItem(app.activeDocument, String(id)); }
    catch (ignoredMissing) { return null; }
};

var _illonaTarget = null;
var _illonaPreviousBoard = null;
var _illonaInteraction = app.userInteractionLevel;
try {
    app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
    if (_illonaRequest.document_id) {
        _illonaTarget = Illona.doc(_illonaRequest.document_id);
        app.activeDocument = _illonaTarget;
        app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        if (_illonaRequest.target_artboard !== undefined) {
            Illona.artboard(_illonaTarget, _illonaRequest.target_artboard);
            _illonaPreviousBoard = _illonaTarget.artboards.getActiveArtboardIndex();
            _illonaTarget.artboards.setActiveArtboardIndex(_illonaRequest.target_artboard);
        }
    }
    if (_illonaRequest.tool_name === "import_svg_as_editable") {
        var _illonaSource = new File(_illonaRequest.params.file_path).fsName;
        for (var _illonaDi = 0; _illonaDi < app.documents.length; _illonaDi++) {
            var _illonaOpenPath = null;
            try { _illonaOpenPath = app.documents[_illonaDi].fullName.fsName; } catch (ignoredPath) {}
            if (_illonaOpenPath === _illonaSource) {
                Illona.fail("SOURCE_ALREADY_OPEN", "Close the source SVG before importing it; Illona will not close an existing user document.");
            }
        }
    }
    if ((_illonaRequest.tool_name === "save_document" && (_illonaRequest.params.mode || "save") === "save") ||
        (_illonaRequest.tool_name === "close_document" && _illonaRequest.params.save === true)) {
        var _illonaSavedPath = null;
        try { _illonaSavedPath = _illonaTarget.fullName; } catch (ignoredSavedPath) {}
        if (!_illonaSavedPath || !_illonaSavedPath.exists) {
            Illona.fail("UNSAVED_DOCUMENT", "Use save_as with an output path for an unsaved document.");
        }
        if (_illonaSavedPath.fsName !== _illonaRequest.allowed_save_path) {
            Illona.fail("SAVE_PATH_CHANGED", "Document path changed since validation. Inspect before saving again.");
        }
    }
    eval("(function(){\n" + _illonaRequest.script + "\n})();");
    if (!_illonaHasResult) { Illona.fail("MISSING_RESULT", "The advanced Illustrator script did not produce a result."); }
    if (_illonaRequest.tool_name === "create_gradient" && _illonaRequest.params.type !== "radial" &&
        _illonaCaptured && !_illonaCaptured.error && _illonaCaptured.success !== false) {
        var _illonaGradientReports = [], _illonaGradientFailures = [];
        var _illonaGradientTargets = _illonaRequest.params.apply_to_uuids || [];
        for (var _illonaGi = 0; _illonaGi < _illonaGradientTargets.length; _illonaGi++) {
            var _illonaGradientRoot = findItemByUUID(_illonaGradientTargets[_illonaGi]);
            if (!_illonaGradientRoot) { continue; }
            var _illonaGradientLeaves = collectPaintLeaves(_illonaGradientRoot, {});
            for (var _illonaGj = 0; _illonaGj < _illonaGradientLeaves.length; _illonaGj++) {
                try {
                    var _illonaGradientReport = Illona.orientGradientFill(_illonaGradientLeaves[_illonaGj], _illonaRequest.params.angle || 0);
                    _illonaGradientReports.push(_illonaGradientReport);
                    if (!_illonaGradientReport.verified) { _illonaGradientFailures.push("Gradient direction was not verified for " + _illonaGradientReport.id); }
                } catch (_illonaGradientError) { _illonaGradientFailures.push(String(_illonaGradientError.message || _illonaGradientError)); }
            }
        }
        _illonaCaptured.gradient_direction = _illonaGradientReports;
        if (_illonaGradientFailures.length) {
            _illonaCaptured.success = false;
            _illonaCaptured.errors = (_illonaCaptured.errors || []).concat(_illonaGradientFailures);
        }
    }
    var _illonaResponse = {result: _illonaCaptured};
    if (_illonaRequest.creates_document && _illonaCaptured && !_illonaCaptured.error && _illonaCaptured.success !== false) {
        _illonaResponse.document = Illona.documentInfo(app.activeDocument);
    }
    return _illonaResponse;
} finally {
    try { app.userInteractionLevel = _illonaInteraction; } catch (ignoredInteraction) {}
    if (_illonaTarget && _illonaPreviousBoard !== null && Illona.isOpen(_illonaTarget)) {
        try { _illonaTarget.artboards.setActiveArtboardIndex(_illonaPreviousBoard); } catch (ignoredBoard) {}
    }
}
}
