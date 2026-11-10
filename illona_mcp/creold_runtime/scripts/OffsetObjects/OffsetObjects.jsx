/*
  OffsetObjects.jsx for Adobe Illustrator
  Description: Offsets objects like the native Offset Path command, 
  but works on paths, symbols, rasters and offers additional options
  Date: July, 2025
  Modification date: September, 2025
  Author: Sergey Osokin, email: hi@sergosokin.ru

  Installation: https://github.com/creold/illustrator-scripts#how-to-run-scripts
  ********************************************************************************************
  * NOTE: Download "offsetObjects_style.ai". And put the file in the folder with this script *
  ********************************************************************************************

  Release notes:
  0.1.4 Added apply last used stroke limit, cap, and join
  0.1.3 Added Japanese localization. Minor improvements
  0.1.2 Fixed offset of groups with hidden or locked nested elements
  0.1.1 Added Joins and Miter limit options from the Offset Path dialog
  0.1 Initial version

  Donate (optional):
  If you find this script helpful, you can buy me a coffee
  - via Buymeacoffee: https://www.buymeacoffee.com/aiscripts
  - via Donatty https://donatty.com/sergosokin
  - via DonatePay https://new.donatepay.ru/en/@osokin
  - via YooMoney https://yoomoney.ru/to/410011149615582

  NOTICE:
  Tested with Adobe Illustrator CC 2019-2025 (Mac/Win).
  This script is provided "as is" without warranty of any kind.
  Free to use, not for sale

  Released under the MIT license
  http://opensource.org/licenses/mit-license.php

  Check my other scripts: https://github.com/creold
*/

//@target illustrator
app.preferences.setBooleanPreference('ShowExternalJSXWarning', false); // Fix drag and drop a .jsx file
$.localize = true; // Automatic UI localization

// Main function
function main() {
  var SCRIPT = {
        name: { en: 'Offset Objects', ja: 'オフセットオブジェクト' },
        version: 'v0.1.4'
      };

  var CFG = {
        isUseSwatch: false, // true - apply spot swatch, false - apply solid color
        swatchName: 'Cut', // Default spot swatch
        swatchValue: [0, 100, 0, 0], // Default CMYK values
        layerName: 'Contour', // Layen name for "Move to New Layer" option
        minArea: 1, // Remove resulting smallest paths. Units: px
        graphStyleFile: 'OffsetObjects_Style.ai',
        graphStyleName: 'Offset_AIS',
        aiVers: parseFloat(app.version),
        isMac: /mac/i.test($.os),
      }

  var LANG = {
        error: { en: 'Script error', ja: 'スクリプトエラー' },
        alertApp: { en: 'Wrong application\nRun script from Adobe Illustrator', 
                    ja: 'アプリケーションが違います\nAdobe Illustratorで実行してください' },
        alertDoc: { en: 'No documents\nOpen a document and try again',
                    ja: 'ドキュメントが開かれていません。\nドキュメントを開いて再実行してください'},
        alertSelect: { en: 'Few objects are selected\nPlease select at least 1 object and try again',
                          ja: '少なくとも 1 個以上のオブジェクトを選択してから実行してください。' },
        alertVersion: { en: 'Wrong app version\nSorry, script only works in Illustrator v16 and later',
                        ja: 'このスクリプトは Illustrator v16 以降でのみ動作します。' },
        alertStyleFile: { en: 'The ' + CFG.graphStyleFile + ' file for the script was not found\n'
                          + 'Download from https://github.com/creold/illustrator-scripts\n\n'
                          + 'And put the file in the folder with this script',
                      ja: 'スクリプト実行のためのファイル（' + CFG.graphStyleFile + '）が見つかりません。\n'
                          + 'ダウンロード：https://github.com/creold/illustrator-scripts\n\n'
                          + 'ダウンロードしたファイルをこのスクリプトと同じフォルダに入れてください。' },
        alertStyle: { en: 'The ' + CFG.graphStyleName + ' style was not found\nYou may have changed the template.\n\n'
                          + 'Download from https://github.com/creold/illustrator-scripts\n\n'
                          + 'And put the file in the folder with this script',
                      ja: 'テンプレートファイルに ' + CFG.graphStyleName + ' スタイルが見つかりませんでした。テンプレートが修正されてしまったかもしれません。\n\n'
                          + 'ダウンロード：https://github.com/creold/illustrator-scripts\n\n'
                          + 'ダウンロードしたファイルをこのスクリプトと同じフォルダに入れてください。' },
        offset: { en: 'Offset:', ja: 'オフセット:' },
        joins: { en: 'Joins:', ja: '角の形状:' },
        miterLimit: { en: 'Miter Limit:', ja: '比率:' },
        stroke: { en: 'Stroke:', ja: '線幅:' },
        miter: { en: 'Miter', ja: 'マイター' },
        round: { en: 'Round', ja: 'ラウンド' },
        bevel: { en: 'Bevel', ja: 'ベベル' },
        position: { en: 'Position', ja: '位置' },
        under: { en: 'Under Object', ja: 'オブジェクトの背面' },
        above: { en: 'Above Object', ja: 'オブジェクトの前面' },
        container: { en: 'Container', ja: 'レイヤー' },
        sameLayer: { en: 'Keep in Same Layer', ja: '同じレイヤーのまま' },
        newLayer: { en: 'Move to New Layer', ja: '新しいレイヤーに移動' },
        group: { en: 'Group with Object', ja: '元のオブジェクトとグループ化' },
        cancel: { en: 'Cancel', ja: 'キャンセル' },
        ok: { en: 'OK', ja: '実行' },
        helpCancel: { en: 'Press Esc to Close', ja: 'Escキーで閉じる' },
        helpOk: { en: 'Press Enter to Run', ja: 'Enterキーで実行' },
        copyright: { en: '\u00A9 Sergey Osokin. Visit Github', ja: '\u00A9 Sergey Osokin　Githubを開く' },
      };

  var SETTINGS = {
    name: SCRIPT.name.en.replace(/\s/g, '_') + '_data.json',
    folder: Folder.myDocuments + '/Adobe Scripts/'
  };

  if (!/illustrator/i.test(app.name)) {
    alert(LANG.alertApp, LANG.error);
    return;
  }

  if (!app.documents.length) {
    alert(LANG.alertDoc, LANG.error);
    return;
  }

  if (!app.selection.length || app.selection.typename === 'TextRange') {
    alert(LANG.alertSelect, LANG.error);
    return;
  }

  if (CFG.aiVers < 16) {
    alert(LANG.alertVersion, LANG.error);
    return;
  }

  var doc = app.activeDocument;
  var sel = app.selection;
  var scriptPath = File($.fileName).parent;
  var styleFile = new File(scriptPath.fsName + '/' + CFG.graphStyleFile);

  if (!styleFile.exists) {
    alert(LANG.alertStyleFile, LANG.error);
    return;
  }

  // DIALOG
  var win = new Window('dialog', SCRIPT.name + ' ' + SCRIPT.version);
      win.orientation = 'column';
      win.alignChildren = ['fill', 'top'];
      win.spacing = 10;
      win.opacity = 0.97;

  // WRAPPER
  var wrapper = win.add('group');
      wrapper.orientation = 'row';
      wrapper.alignChildren = ['left', 'center'];

  // LABELS
  var labelsGrp = wrapper.add('group');
      labelsGrp.orientation = 'column';
      labelsGrp.alignChildren = ['left', 'top'];
      labelsGrp.spacing = 18;

  labelsGrp.add('statictext', undefined, LANG.offset);
  labelsGrp.add('statictext', undefined, LANG.joins);
  labelsGrp.add('statictext', undefined, LANG.miterLimit);
  labelsGrp.add('statictext', undefined, LANG.stroke);

  // INPUTS
  var inputsGrp = wrapper.add('group');
      inputsGrp.orientation = 'column';
      inputsGrp.alignChildren = ['left', 'top'];
      inputsGrp.spacing = 10;

  // OFFSET
  var offsetGrp = inputsGrp.add('group');
      offsetGrp.alignChildren = ['left', 'center'];

  var offsetInp = offsetGrp.add('edittext', undefined, 0);
      offsetInp.preferredSize.width = 50;

  // Focus input field on compatible versions
  if (CFG.isMac || CFG.aiVers >= 26.4 || CFG.aiVers <= 17) {
    offsetInp.active = true;
  }

  var offsetUnits = offsetGrp.add('dropdownlist', undefined, ['pt', 'pc', 'in', 'mm', 'cm', 'px']);
      offsetUnits.preferredSize.width = 52;
      offsetUnits.selection = 0;

  // JOINS
  var joinGrp = inputsGrp.add('group');
      joinGrp.alignChildren = ['left', 'center'];

  var joinList = joinGrp.add('dropdownlist', undefined, [LANG.miter, LANG.round, LANG.bevel]);
      joinList.preferredSize.width = 110;
      joinList.selection = 0;

  // STROKE WEIGHT
  var miterGrp = inputsGrp.add('group');
      miterGrp.alignChildren = ['left', 'center'];

  var miterInp = miterGrp.add('edittext', undefined, 4);
      miterInp.preferredSize.width = 110;

  // STROKE WEIGHT
  var strokeGrp = inputsGrp.add('group');
      strokeGrp.alignChildren = ['left', 'center'];

  var strokeInp = strokeGrp.add('edittext', undefined, 0.25);
      strokeInp.preferredSize.width = 50;

  var strokeUnits = strokeGrp.add('dropdownlist', undefined, ['pt', 'pc', 'in', 'mm', 'cm', 'px']);
      strokeUnits.preferredSize.width = 52;
      strokeUnits.selection = 0;

  // CONTOUR HIERARCHY
  var posPnl = win.add('panel', undefined, LANG.position);
      posPnl.orientation = 'column';
      posPnl.alignChildren = ['fill', 'top'];
      posPnl.margins = [10, 15, 10, 7];

  var isUnder = posPnl.add('radiobutton', undefined, LANG.under);
      isUnder.value = true;
  var isAbove = posPnl.add('radiobutton', undefined, LANG.above);

  var cntnrPnl = win.add('panel', undefined, LANG.container);
      cntnrPnl.orientation = 'column';
      cntnrPnl.alignChildren = ['fill', 'top'];
      cntnrPnl.margins = [10, 15, 10, 7];

  var isSameLayer = cntnrPnl.add('radiobutton', undefined, LANG.sameLayer);
      isSameLayer.value = true;
  var isNewLayer = cntnrPnl.add('radiobutton', undefined, LANG.newLayer);
  var isGroup = cntnrPnl.add('radiobutton', undefined, LANG.group);

  // BUTTONS
  var btns = win.add('group');
      btns.orientation = 'row';
      btns.alignChildren = ['fill', 'fill'];

  // Platform-specific button order
  var cancel, ok;
  if (CFG.isMac) {
    cancel = btns.add('button', undefined, LANG.cancel, { name: 'cancel' });
    ok = btns.add('button', undefined, LANG.ok, { name: 'ok' });
  } else {
    ok = btns.add('button', undefined, LANG.ok, { name: 'ok' });
    cancel = btns.add('button', undefined, LANG.cancel, { name: 'cancel' });
  }

  cancel.helpTip = LANG.helpCancel;
  ok.helpTip = LANG.helpOk;

  var copyright = win.add('statictext', undefined, LANG.copyright);
  copyright.justify = 'center';

  // EVENTS
  loadSettings(SETTINGS);

  // Use Up / Down arrow keys (+ Shift) to change value
  bindStepperKeys(offsetInp, -5000, 5000);
  bindStepperKeys(miterInp, -16000, -16000);
  bindStepperKeys(strokeInp, 0, 1000);

  joinList.onChange = offsetUnits.onChange = strokeUnits.onChange = function() {
    offsetInp.active = false;
    strokeInp.active = false;
  }

  cancel.onClick = win.close;
  ok.onClick = okClick;

  copyright.addEventListener('mousedown', function () {
    openURL('https://github.com/creold');
  });

  /**
   * Handle the click event for the OK button.
   * Save settings, import style, and process selected items
   */
  function okClick() {
    saveSettings(SETTINGS);
    var isImported = importStyle(styleFile, CFG.graphStyleName);

    if (!isImported) {
      alert(LANG.alertStyle, LANG.error);
      win.close();
      return;
    }

    var options = {
      isUnder: isUnder.value,
      isNewLayer: isNewLayer.value,
      isGroup: isGroup.value,
      offsetStyle: {},
      offsetValue: convertToPt( strToNum(offsetInp.text), offsetUnits),
      miterValue: strToNum(miterInp.text, 4),
      joinType: joinList.selection.index === 0 ? 2 : (joinList.selection.index === 1 ? 0 : 1),
      strokeValue: convertToPt( Math.abs(strToNum(strokeInp.text)), strokeUnits),
      strokeMiter: doc.defaultStrokeMiterLimit,
      strokeCap: doc.defaultStrokeCap,
      strokeJoin: doc.defaultStrokeJoin,
      minArea: CFG.minArea,
      layerName: CFG.layerName,
    }

    try { 
      options.offsetStyle = doc.graphicStyles.getByName(CFG.graphStyleName)
    } catch (err) { 
      win.close();
      return;
    }

    deselect();

    // Prepare a new layer for the contours
    if (options.isNewLayer) {
      var targetLayer;
      try {
        targetLayer = doc.layers[options.layerName];
      } catch (err) {
        targetLayer = doc.layers.add();
        targetLayer.name = options.layerName;
      }
      // Set up the layer properties
      targetLayer.visible = true;
      targetLayer.locked = false;
      targetLayer.zOrder(options.isUnder ? ZOrderMethod.SENDTOBACK : ZOrderMethod.BRINGTOFRONT);
    }

    // Prepare the color for filling the contours
    var targetColor;
    if (CFG.isUseSwatch) {
      getSpotSwatch(CFG.swatchName, CFG.swatchValue);
      targetColor = doc.swatches[CFG.swatchName].color;
    } else {
      targetColor = setCMYKColor(CFG.swatchValue);
    }

    // Process selected items
    var results = [];
    for (var i = 0, len = sel.length; i < len; i++) {
      var paths = process(doc, sel[i], options, targetColor);
      if (paths == null || !paths) {
        continue;
      }
      results = results.concat(paths);
    }

    // Select all contours
    if (results.length) {
      app.selection = results;
    }

    offsetStyle.remove();
    win.close();
  }

  win.onClose = function () {
    try {
      doc.graphicStyles.getByName(CFG.graphStyleName).remove();
    } catch (err) {}
  }

  /**
   * Handle keyboard input to shift numerical values
   * @param {Object} input - The input element to which the event listener will be attached
   * @param {number} min - The minimum allowed value for the numerical input
   * @param {number} max - The maximum allowed value for the numerical input
   * @returns {void}
   */
  function bindStepperKeys(input, min, max) {
    input.addEventListener('keydown', function (kd) {
      var step = ScriptUI.environment.keyboardState['shiftKey'] ? 10 : 1;
      var num = parseFloat(this.text);
      if (kd.keyName == 'Down' || kd.keyName == 'LeftBracket') {
        this.text = (typeof min !== 'undefined' && (num - step) < min) ? min : num - step;
        kd.preventDefault();
      }
      if (kd.keyName == 'Up' || kd.keyName == 'RightBracket') {
        this.text = (typeof max !== 'undefined' && (num + step) > max) ? max : num + step;
        kd.preventDefault();
      }
    });
  }

  /**
   * Save UI options to a file
   * @param {object} prefs - Object containing preferences
   * @returns {void}
   */
  function saveSettings(prefs) {
    if (!Folder(prefs.folder).exists) {
      Folder(prefs.folder).create();
    }

    var f = new File(prefs.folder + prefs.name);
    f.encoding = 'UTF-8';
    f.open('w');

    var data = {};
    data.win_x = win.location.x;
    data.win_y = win.location.y;

    data.offset = offsetInp.text;
    data.offsetUnits = offsetUnits.selection.index;

    data.joins = joinList.selection.index;
    data.miter = miterInp.text;

    data.stroke = strokeInp.text;
    data.strokeUnits = strokeUnits.selection.index;

    data.position = isUnder.value ? 0 : 1;
    data.container = isSameLayer.value ? 0 : (isNewLayer.value ? 1 : 2);

    f.write( stringify(data) );
    f.close();
  }

  /**
   * Load options from a file
   * @param {object} prefs - Object containing preferences
   * @returns {void}
   */
  function loadSettings(prefs) {
    var f = File(prefs.folder + prefs.name);
    if (!f.exists) return;

    try {
      f.encoding = 'UTF-8';
      f.open('r');
      var json = f.readln();
      try { var data = new Function('return (' + json + ')')(); }
      catch (err) { return; }
      f.close();

      if (typeof data != 'undefined') {
        win.location = [
          data.win_x && !isNaN(parseInt(data.win_x)) ? parseInt(data.win_x) : 300,
          data.win_y && !isNaN(parseInt(data.win_y)) ? parseInt(data.win_y) : 300
        ];

        offsetInp.text = data.offset || 0;
        offsetUnits.selection = parseInt(data.offsetUnits) || 0;

        joinList.selection = parseInt(data.joins) || 0;
        miterInp.text = data.miter || 4;

        strokeInp.text = data.stroke || 0;
        strokeUnits.selection = parseInt(data.strokeUnits) || 0;

        posPnl.children[parseInt(data.position) || 0].value = true;
        cntnrPnl.children[parseInt(data.container) || 0].value = true;
      }
    } catch (err) { return; }
  }

  win.show();
}

/**
 * Import a graphic style from a specified file to the active document
 * @param {File} file - The file from which to import the style
 * @param {string} styleName - The name of the style to import
 */
function importStyle(file, styleName) {
  var activeDoc = app.activeDocument;
  var styleDoc = app.open(file);

  var item;
  // Create a default rectangle item in the template document
  if (!styleDoc.pathItems.length) {
    item = styleDoc.layers[0].pathItems.rectangle(0, 0, 10, 10);
    item.filled = true;
    item.stroked = false;
  } else { 
    // Prepare an existing item in the template document
    item = styleDoc.pathItems[0];
    styleDoc.layers[0].locked = false;
    styleDoc.layers[0].visible = true;
    item.locked = false;
    item.hidden = false;
  }

  // Apply a graphic style
  try {
    var targetStyle = styleDoc.graphicStyles.getByName(styleName);
    targetStyle.applyTo(item);
  } catch (err) {
    styleDoc.close(SaveOptions.DONOTSAVECHANGES);
    return false;
  }

  // Duplicate an item to the active document for import a graphic style
  var dup = item.duplicate(activeDoc.selection[0].layer, ElementPlacement.PLACEATEND);
  dup.position = [-4000, -4000]
  dup.remove();

  activeDoc.activate();
  styleDoc.close(SaveOptions.DONOTSAVECHANGES);

  return true;
}

/**
 * Convert string to number
 * @param {string} str - The string to convert to a number
 * @param {number} def - The default value to return if the conversion fails
 * @returns {number} The converted number
 */
function strToNum(str, def) {
  if (arguments.length == 1 || def == undefined) def = 0;
  str = str.replace(/,/g, '.').replace(/[^\d.-]/g, '');
  str = str.split('.');
  str = str[0] ? str[0] + '.' + str.slice(1).join('') : '';
  str = str.substr(0, 1) + str.substr(1).replace(/-/g, '');
  if (isNaN(str) || !str.length) return parseFloat(def);
  else return parseFloat(str);
}

/**
 * Recalculate the value in the selected units
 * @param {number} value - The input value to be converted
 * @param {Dropdown} dropdown - The dropdown list containing unit names
 * @returns {number} The recalculated value in points
 */
function convertToPt(value, dropdown) {
  return convertUnits(value, dropdown.selection.text.slice(0, 2), 'px');
}

/**
 * Convert units of measurement from one unit to another
 * @param {number|string} value - The numeric data to be converted
 * @param {string} currUnits - The current units of the value (e.g., 'px', 'mm')
 * @param {string} newUnits - The target units for conversion (e.g., 'pt', 'in')
 * @returns {number} The converted value in the new units
 */
function convertUnits(value, currUnits, newUnits) {
  return UnitValue(value, currUnits).as(newUnits);
}

/**
 * Retrieve an existing swatch or creates a new one
 * @param {string} name - The name of the spot color to add
 * @param {Array} value - The CMYK color values to use for the spot color
 * @returns {Object} The newly created spot color object
 */
function getSpotSwatch(name, value) {
  var doc = app.activeDocument;
  var color = setCMYKColor(value);
  var swatch = null;

  try {
    swatch = doc.spots.getByName(name);
  } catch (err) {
    swatch = doc.spots.add();
    swatch.name = name;
    swatch.colorType = ColorModel.SPOT;
    swatch.color = color;
  }

  var spotColor = new SpotColor();
  spotColor.spot = color;
  spotColor.tint = 100;
}

/**
 * Create a CMYK object with validated CMYK values
 * @param {Array} cmyk - An array of four numbers representing CMYK values
 * @returns {Object} A CMYK color with validated and clamped CMYK values
 */
function setCMYKColor(cmyk) {
  var defaultCMYK = [0, 0, 0, 100];

  // Validate and clamp each CMYK value
  for (var i = 0; i < 4; i++) {
    if (cmyk[i] !== undefined && typeof cmyk[i] === 'number') {
      defaultCMYK[i] = Math.max(0, Math.min(100, cmyk[i]));
    }
  }

  // Create and return a new CMYKColor object
  var color = new CMYKColor();
  color.cyan = defaultCMYK[0];
  color.magenta = defaultCMYK[1];
  color.yellow = defaultCMYK[2];
  color.black = defaultCMYK[3];

  return color;
}

/**
 * Process an Illustrator document item by offsetting, styling, and repositioning it
 * @param {Object} doc - The working Illustrator document
 * @param {Object} origItem - The original item to process
 * @param {Object} options - Configuration options for processing
 * @param {Object} targetColor - The target color to apply to the processed item
 * @returns {Object} The processed item
 */
function process(doc, origItem, options, targetColor) {
  try {
    var offsetItem = offsetObject(origItem, options);
  } catch (err) {}

  if (offsetItem == null || !offsetItem) return null;
  
  // Extracts paths from the processed item
  var paths = [];
  if (/group/i.test(offsetItem.typename)) {
    paths = getPaths(offsetItem.pageItems);
  } else if (/compound/i.test(offsetItem.typename)) {
    paths = offsetItem.pathItems;
  } else {
    paths = [offsetItem];
  }

  stylePaths(paths, targetColor, options);

  // Unite and simplify group paths
  if (/group/i.test(offsetItem.typename)) {
    offsetItem = mergeGroup(offsetItem, options.minArea);
  }

  // Change z-order
  offsetItem.move(origItem, options.isUnder ? ElementPlacement.PLACEAFTER : ElementPlacement.PLACEBEFORE);

  // Group original and offset items
  if (options.isGroup) {
    var comboGroup = origItem.layer.groupItems.add();
    comboGroup.name = origItem.name;
    comboGroup.move(origItem, ElementPlacement.PLACEBEFORE);
    origItem.move(comboGroup, ElementPlacement.PLACEATBEGINNING);
    offsetItem.move(comboGroup, options.isUnder ? ElementPlacement.PLACEATEND : ElementPlacement.PLACEATBEGINNING);
  } else if (options.isNewLayer) {
    // Move paths to a new layer
    var targetLayer = doc.layers[options.layerName];
    offsetItem.move(targetLayer, ElementPlacement.PLACEATBEGINNING);
  }

  // Remove unnecessaty group
  if (/group/i.test(offsetItem.typename) && offsetItem.pageItems.length === 1) {
    app.executeMenuCommand('ungroup');
  }

  offsetItem = app.selection[0];
  deselect();

  return offsetItem;
}

/**
 * Offset an object in Adobe Illustrator by duplicating it and applying an offset path effect
 * @param {Object} item - The item to be offset
 * @param {Object} options - Configuration options for processing
 * @returns {Object} The newly created offset object
 */
function offsetObject(item, options) {
  // Duplicate the item and place it right after the original
  var dup = item.duplicate();

  try {
    processGroup(dup);
  } catch (err) {}

  if (dup && /group/i.test(dup.typename) && !dup.pageItems.length) {
    try {
      dup.remove();
    } catch (err) {}
    return null;
  }

  dup.move(item, ElementPlacement.PLACEAFTER);
  dup.selected = true;

  processClippingMask(dup);

  // Outline Stroke
  app.executeMenuCommand('OffsetPath v22');
  dup = app.selection[0];

  /* Live Effects
    1. Drop Shadow
    2. Outline Object
    4. Outline Stroke
    3. Pathfinder > Merge
    4. Pathfinder > Divide
    5. Pathfinder > Add
    6. Offset Path
  */

  // Apply the specified style to the duplicated item
  if (options.offsetStyle !== undefined) {
    options.offsetStyle.applyTo(dup);
  }

  // Define and apply the offset path effect
  var xmlOffsetPath = '<LiveEffect name="Adobe Offset Path"><Dict data="R ofst #1 I jntp #2 R mlim #3 "/></LiveEffect>';
  xmlOffsetPath = xmlOffsetPath.replace(/#1/, options.offsetValue).replace(/#2/, options.joinType).replace(/#3/, options.miterValue);
  dup.applyEffect(xmlOffsetPath);

  updateScreen();

  // Expand the style to finalize the offset effect
  app.executeMenuCommand('expandStyle');

  // Return the newly created offset object
  return app.selection[0];
}

/**
 * Process a group item by unlocking it and handling its children
 * Removes the item if it is hidden, otherwise processes each child item recursively
 * @param {Object} item - The item to process
 */
function processGroup(item) {
  unlockAll(item);

  // Remove the item if it is hidden
  if (item.hidden) {
    unhideAll(item);
    try {
      item.remove();
    } catch (err) {}
    return;
  }

  // Return if the item is not a group
  if (!/group/i.test(item.typename)) return;

  // Remove empty groups
  if (/group/i.test(item.typename) && !item.pageItems.length) {
    try {
      item.remove();
    } catch (err) {}
    return;
  }

  for (var i = item.pageItems.length - 1; i >= 0; i--) {
    var child = item.pageItems[i];
    unlockAll(child);

    if (child.hidden) {
      unhideAll(child);
      try {
        child.remove();
        continue;
      } catch (err) {}
    }

    if (/group/i.test(child.typename)) {
      processGroup(child);
    }
  }
}

/**
 * Unlock an item and all its sub-items
 * @param {Object} item - The item to unlock
 */
function unlockAll(item) {
  item.locked = false;
  var i = 0;
  var len = 0;

  if (item.hasOwnProperty('pageItems') && item.pageItems.length) {
    for (i = 0, len = item.pageItems.length; i < len; i++) {
      var subItem = item.pageItems[i];
      subItem.locked = false;
      unlockAll(subItem);
    }
  } else if (item.hasOwnProperty('pathItems') && item.pathItems.length) {
    for (i = 0, len = item.pathItems.length; i < len; i++) {
      item.pathItems[i].locked = false;
    }
  }
}

/**
 * Show an item and all its sub-items
 * @param {Object} item - The item to show
 */
function unhideAll(item) {
  item.hidden = false;
  var i = 0;
  var len = 0;

  if (item.hasOwnProperty('pageItems') && item.pageItems.length) {
    for (i = 0, len = item.pageItems.length; i < len; i++) {
      var subItem = item.pageItems[i];
      subItem.hidden = false;
      unhideAll(subItem);
    }
  } else if (item.hasOwnProperty('pathItems') && item.pathItems.length) {
    for (i = 0, len = item.pathItems.length; i < len; i++) {
      item.pathItems[i].hidden = false;
    }
  }
}

/**
 * Process a clipping mask for a given item
 * A mask are getting ready for correct offset
 * @param {Object} item - The item to process
 */
function processClippingMask(item) {
  if (!/group/i.test(item.typename) && !item.clipped) return;

  var mask = getClippingMask(item);
  if (mask !== null && mask.hasOwnProperty('filled') && mask.filled) {
    mask.duplicate(item, ElementPlacement.PLACEATEND);
    mask.clipping = false;
  }

  for (var i = 0, len = item.pageItems.length; i < len; i++) {
    processClippingMask(item.pageItems[i]);
  }
}

/**
 * Get the clipping mask from a group
 * @param {Object} group - The group of items to search for a clipping mask
 * @returns {Object} The clipping path item if found, otherwise null
 */
function getClippingMask(group) {
  for (var i = 0, len = group.pageItems.length; i < len; i++) {
    var item = group.pageItems[i];
    if (/compound/i.test(item.typename) && item.pathItems.length) {
      item = item.pathItems[0];
    }
    if (item.hasOwnProperty('clipping') && item.clipping) {
      return item;
    }
  }
  return null;
}

/**
 * Clear the current selection in the Illustrator
 */
function deselect() {
  if (parseFloat(app.version) >= 16) {
    app.executeMenuCommand('deselectall');
  }
  app.selection = null;
}

/**
 * Force the screen to update by toggling artboard edges
 * @returns {void}
 */
function updateScreen() {
  if (parseFloat(app.version) >= 16) {
    app.executeMenuCommand('artboard');
    app.executeMenuCommand('artboard');
  } else {
    app.redraw();
  }
}

/**
 * Recursively collect path items from a given collection
 * @param {(Object|Array)} coll - The collection of items to search through
 * @returns {Array} An array of path items found in the collection
 */
function getPaths(coll) {
  var results = [];

  for (var i = 0; i < coll.length; i++) {
    var item = coll[i];
    if (item.pageItems && item.pageItems.length) {
      results = results.concat( getPaths(item.pageItems) );
    } else if (/compound/i.test(item.typename) && item.pathItems.length) {
      results = results.concat( getPaths(item.pathItems) );
    } else if (/pathitem/i.test(item.typename)) {
      results.push(item);
    }
  }

  return results;
}

/**
 * Apply colors and strokes to an array of paths
 * @param {Array} paths - The array of paths to style
 * @param {Object} color - The target color to apply
 * @param {Object} options - Configuration options for processing
 */
function stylePaths(paths, color, options) {
  for (var i = 0, len = paths.length; i < len; i++) {
    var path = paths[i];
    if (path.hasOwnProperty('fillColor')) {
      path.filled = true;
      path.fillColor = color;
    }
    path.blendingMode = BlendModes.NORMAL;
    path.opacity = 100;
    path.stroked = !!options.strokeValue;
    if (options.strokeValue) {
      path.strokeWidth = options.strokeValue;
      path.strokeColor = color;
      path.strokeMiterLimit = options.strokeMiter;
      path.strokeJoin = options.strokeJoin;
      path.strokeCap = options.strokeCap;
    }
  }
}

/**
 * Combining overlapping paths in a group
 * @param {GroupItem} group - The group item to process
 * @param {number} minArea - The minimum area threshold for paths
 * @returns {PageItem} The processed item
 */
function mergeGroup(group, minArea) {
  app.executeMenuCommand('Live Pathfinder Add');
  updateScreen();
  app.executeMenuCommand('expandStyle');

  var mergedItem = app.selection[0];

  if (/group/i.test(mergedItem.typename)) {
    // Remove unnecessaty group
    if (mergedItem.pageItems.length === 1) {
      app.executeMenuCommand('ungroup');
    } else {
      // Remove smallest paths
      var paths = getPaths(mergedItem.pageItems);
      for (var j = paths.length - 1; j >= 0; j--) {
        var path = paths[j];
        if (path.hasOwnProperty('area') && Math.abs(path.area) < minArea) {
          path.remove();
        }
      }
    }
  }

  return app.selection[0];
}

/**
 * Open a URL in the default web browser
 * @param {string} url - The URL to open in the web browser
 * @returns {void}
*/
function openURL(url) {
  var html = new File(Folder.temp.absoluteURI + '/aisLink.html');
  html.open('w');
  var htmlBody = '<html><head><META HTTP-EQUIV=Refresh CONTENT="0; URL=' + url + '"></head><body> <p></body></html>';
  html.write(htmlBody);
  html.close();
  html.execute();
}

/**
 * Serialize a JavaScript plain object into a JSON-like string
 * @param {Object} obj - The object to serialize
 * @returns {string} A JSON-like string representation of the object
 */
function stringify(obj) {
  var json = [];
  for (var key in obj) {
    if (obj.hasOwnProperty(key)) {
      var value = obj[key].toString();
      value = value
        .replace(/\t/g, "\t")
        .replace(/\r/g, "\r")
        .replace(/\n/g, "\n")
        .replace(/"/g, '\"');
      json.push('"' + key + '":"' + value + '"');
    }
  }
  return "{" + json.join(",") + "}";
}

// Run script
try {
  main();
} catch (err) {}