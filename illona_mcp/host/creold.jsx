/* Guarded host for fixed, staged Sergey Osokin / Creold originals (MIT).
 * Script source is selected and integrity checked by Python, never supplied by a tool caller. */
(function (A) {
    A.ops.creold_script = function (p) {
        var document = A.doc(p.document_id), originals = [], selection = [], preferences = [];
        var previousInteraction = app.userInteractionLevel, previousLocalize = $.localize;
        var previousSystem = app.coordinateSystem;
        var oldOrigin = document.rulerOrigin.slice(), oldBoardOrigins = [], i;
        function snapshot() {
            var list = [];
            for (var di = 0; di < app.documents.length; di++) { list.push(A.documentInfo(app.documents[di])); }
            return list;
        }
        function allowed(file) {
            var path = file.fsName;
            return path === p.output_root || path.indexOf(p.output_root + "/") === 0 || path === p.job_root || path.indexOf(p.job_root + "/") === 0;
        }
        A.creoldMessages = []; A.creoldWindows = [];
        A.creoldGuardWrite = function (file) {
            file = file instanceof File || file instanceof Folder ? file : new File(file);
            if (!allowed(file)) {
                A.creoldMessages.push("Blocked output outside Illona: " + file.fsName);
                A.fail("OUTPUT_OUTSIDE_ILLONA", "Creold output must stay inside " + p.output_root);
            }
            return file;
        };
        A.creoldOpenForWrite = function (file, mode) { A.creoldGuardWrite(file); return file.open(mode); };
        A.creoldSaveAs = function (doc, file, options) {
            file = A.creoldGuardWrite(file);
            if (options === undefined) { return doc.saveAs(file); }
            return doc.saveAs(file, options);
        };
        A.creoldExportFile = function (doc, file, format, options) {
            file = A.creoldGuardWrite(file);
            if (options === undefined) { return doc.exportFile(file, format); }
            return doc.exportFile(file, format, options);
        };
        A.creoldSave = function (doc) {
            var file = null;
            try { file = doc.fullName; } catch (ignoredUnsaved) {}
            if (!file || !file.exists) { A.fail("UNSAVED_DOCUMENT", "Save a copy inside Illona before using this original save operation."); }
            A.creoldGuardWrite(file); return doc.save();
        };
        A.creoldSelectFolder = function (prompt, initial) {
            var folder = Folder.selectDialog(prompt, initial || new Folder(p.output_root));
            if (folder) { A.creoldGuardWrite(folder); }
            return folder;
        };
        A.creoldSaveDialog = function (prompt, filter) {
            var file = File.saveDialog(prompt, filter);
            if (file) { A.creoldGuardWrite(file); }
            return file;
        };
        A.creoldWindow = function (type, title, bounds, properties) {
            if (p.mode === "automatic") { A.fail("DIALOG_NOT_ALLOWED", "This original requires interactive mode."); }
            var window = new Window(type, title, bounds, properties);
            A.creoldWindows.push(window); return window;
        };
        // Resolve every selected UUID before any original script can modify artwork.
        for (i = 0; i < p.object_ids.length; i++) { selection.push(A.findItem(document, p.object_ids[i])); }
        for (i = 0; i < document.artboards.length; i++) { oldBoardOrigins.push(document.artboards[i].rulerOrigin.slice()); }
        var keys = p.preference_keys || [];
        for (i = 0; i < keys.length; i++) {
            try {
                preferences.push({kind: keys[i].kind, key: keys[i].key,
                    value: app.preferences["get" + keys[i].kind + "Preference"](keys[i].key)});
            } catch (ignoredPreference) { A.creoldMessages.push("Preference could not be snapshotted: " + keys[i].key); }
        }
        var before = snapshot();
        try {
            app.activeDocument = document;
            app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
            app.userInteractionLevel = p.mode === "interactive" ? UserInteractionLevel.DISPLAYALERTS : UserInteractionLevel.DONTDISPLAYALERTS;
            if (p.selection_mode !== "preserve") {
                document.selection = null;
                for (i = 0; i < selection.length; i++) { selection[i].selected = true; }
            }
            var file = new File(p.script_path);
            if (!file.exists || file.fsName.indexOf(p.job_root + "/") !== 0) { A.fail("INVALID_CREOLD_SCRIPT", "Only a staged fixed script may execute."); }
            $.evalFile(file);
            return {script_id: p.script_id, status: "script_returned", modification_verified: false,
                result_note: "The original returned. It may catch its own errors or be cancelled; inspect artwork and preview before claiming success.",
                messages: A.creoldMessages, documents_before: before, documents_after: snapshot()};
        } finally {
            for (i = 0; i < A.creoldWindows.length; i++) {
                try {
                    if (A.creoldWindows[i].visible) {
                        A.creoldWindows[i].close();
                        A.creoldMessages.push("A remaining modeless window was closed when its original script returned.");
                    }
                } catch (ignoredWindow) {}
            }
            for (i = preferences.length - 1; i >= 0; i--) {
                try { app.preferences["set" + preferences[i].kind + "Preference"](preferences[i].key, preferences[i].value); }
                catch (restorePreference) { A.creoldMessages.push("Could not restore preference: " + preferences[i].key); }
            }
            try { $.localize = previousLocalize; } catch (ignoredLocalize) {}
            try { app.userInteractionLevel = previousInteraction; } catch (ignoredInteraction) {}
            try { app.coordinateSystem = previousSystem; } catch (ignoredSystem) {}
            if (A.isOpen(document)) {
                try { document.rulerOrigin = oldOrigin; } catch (ignoredOrigin) {}
                for (i = 0; i < oldBoardOrigins.length && i < document.artboards.length; i++) {
                    try { document.artboards[i].rulerOrigin = oldBoardOrigins[i]; } catch (ignoredBoardOrigin) {}
                }
            }
        }
    };
})(Illona);
