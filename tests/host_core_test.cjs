/* Independent host smoke tests: no Adobe process, files, or user documents. */
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
let serial = 0;
const doc = {name: 'Mock', documentColorSpace: 'RGB', artboards: [{name: 'A4', artboardRect: [100, 700, 695, 0]}], layers: [], pageItems: [], saved: false, fullName: {fsName: '/synthetic-unsaved.ai', exists: false}};
function layer(name) {
  const value = {name, locked: false, visible: true, typename: 'Layer', parent: doc};
  value.pathItems = {
    rectangle: (top, left, w, h) => makeItem(value, 'PathItem', [left, top, left + w, top - h]),
    ellipse: (top, left, w, h) => makeItem(value, 'PathItem', [left, top, left + w, top - h]),
    add: () => makeItem(value, 'PathItem', [0, 0, 0, 0]),
  };
  value.textFrames = {add: () => makeItem(value, 'TextFrame', [0, 0, 0, 0])};
  return value;
}
function makeItem(layer, type, bounds) {
  const item = {uuid: 'id-' + (++serial), name: '', typename: type, geometricBounds: bounds, parent: layer, layer, editable: true, locked: false, hidden: false, opacity: 100, position: [bounds[0], bounds[1]], textRange: {characterAttributes: {}, paragraphAttributes: {}}, pathPoints: []};
  item.pathPoints.add = () => {const point = {}; item.pathPoints.push(point); return point;};
  item.remove = () => {doc.pageItems.splice(doc.pageItems.indexOf(item), 1);};
  doc.pageItems.push(item);
  return item;
}
doc.layers.add = () => {const value = layer(''); doc.layers.push(value); value.remove = () => doc.layers.splice(doc.layers.indexOf(value), 1); return value;};
doc.getPageItemFromUuid = id => doc.pageItems.find(x => x.uuid === id) || null;
const docs = [doc];
docs.addDocument = (preset, settings) => {const value = {...doc, name: settings.title, artboards: [{artboardRect: [0, settings.height, settings.width, 0]}], pageItems: [], layers: []}; docs.push(value); return value;};
const font = {name: 'ArialMT', family: 'Arial', style: 'Regular'};
const fonts = [font];
fonts.getByName = name => {if (name === font.name) return font; throw Error('missing');};
const sandbox = {
  app: {name: 'Illustrator', version: '30.8.2', documents: docs, textFonts: fonts, coordinateSystem: 'artboard', startupPresetsList: ['Basic RGB'], redraw() {}},
  $: {global: {}}, DocumentPreset: function () {}, DocumentColorSpace: {RGB: 'RGB', CMYK: 'CMYK'},
  RulerUnits: {Millimeters: 'mm', Points: 'pt'}, CoordinateSystem: {DOCUMENTCOORDINATESYSTEM: 'document'},
  RGBColor: function () {this.typename = 'RGBColor';}, CMYKColor: function () {this.typename = 'CMYKColor';},
  NoColor: function () {}, PointType: {SMOOTH: 'smooth', CORNER: 'corner'}, Justification: {LEFT: 'left'}, Date, Error, Math, isFinite, parseInt,
};
vm.createContext(sandbox);
for (const file of ['core.jsx', 'drawing.jsx']) {
  const source = fs.readFileSync(path.join(__dirname, '..', 'illona_mcp', 'host', file), 'utf8');
  new vm.Script(source, {filename: file}).runInContext(sandbox);
}
function run(operation, params) {
  sandbox.operation = operation;
  sandbox.input = JSON.stringify(params);
  return vm.runInContext('Illona.run(operation, JSON.parse(input))', sandbox);
}
const id = run('status', {}).data.documents[0].id;
assert.equal(run('status', {}).data.documents[0].path, null);
const second = run('create_document', {width: 210, height: 297, units: 'mm', name: 'Second document'});
assert.equal(second.ok, true, JSON.stringify(second));
assert.notEqual(second.data.id, id);
assert.equal(second.data.path, null);
/* Re-evaluating modules must retain IDs across subsequent host requests. */
for (const file of ['core.jsx', 'drawing.jsx']) {
  new vm.Script(fs.readFileSync(path.join(__dirname, '..', 'illona_mcp', 'host', file), 'utf8')).runInContext(sandbox);
}
let status = run('status', {}).data;
assert.equal(status.documents[0].id, id);
assert.equal(status.documents[1].id, second.data.id);
assert.equal(run('inspect_document', {document_id: second.data.id}).ok, true);
doc.fullName.exists = true;
assert.equal(run('status', {}).data.documents[0].path, '/synthetic-unsaved.ai');
doc.fullName.exists = false;
let result = run('create_elements', {document_id: id, elements: [{type: 'rect', x: 0, y: 0, width: 10, height: 10}, {type: 'ellipse', x: 0, y: 0, width: -1, height: 10}]});
assert.equal(result.ok, false);
assert.equal(doc.pageItems.length, 0);
assert.equal(doc.layers.length, 0);
result = run('create_elements', {document_id: id, units: 'mm', elements: [
  {type: 'rect', x: 10, y: 20, width: 30, height: 40, fill: '#ff0000'},
  {type: 'text', text: 'Bună, România! 😊', x: 0, y: 0, font: 'ArialMT'},
  {type: 'path', points: [{x: 0, y: 0, right: [5, 0]}, {x: 10, y: 10, left: {x: 10, y: 5}, smooth: true}], closed: true, stroke: '#000000'},
]});
assert.equal(result.ok, true, JSON.stringify(result));
assert.equal(result.data.count, 3);
assert(Math.abs(doc.pageItems[0].geometricBounds[0] - (100 + 10 * 72 / 25.4)) < 1e-8);
assert.equal(doc.pageItems[1].contents, 'Bună, România! 😊');
assert.equal(doc.pageItems[2].pathPoints[1].pointType, 'smooth');
assert.equal(doc.pageItems[2].closed, true);
const text = doc.pageItems[1];
result = run('update_objects', {document_id: id, changes: [{id: text.uuid, name: 'must not apply'}, {id: 'missing', text: 'x'}]});
assert.equal(result.ok, false);
assert.equal(text.name, '');
result = run('create_elements', {document_id: id, elements: [{type: 'text', text: 'x', font: 'Missing', x: 0, y: 0}]});
assert.equal(result.error.code, 'FONT_NOT_FOUND');
assert.equal(doc.pageItems.length, 3);
assert.equal(run('inspect_document', {document_id: 'unknown'}).error.code, 'DOCUMENT_NOT_FOUND');
assert.equal(sandbox.app.coordinateSystem, 'artboard');
result = run('update_objects', {document_id: id, changes: [{id: text.uuid, text: 'Titlu nou', size_pt: 24}]});
assert.equal(result.ok, true);
assert.equal(text.textRange.characterAttributes.size, 24);
assert.equal(result.data.warnings.length, 1);
/* Illustrator 30.8 UUID lookup can return a generic GroupItem proxy for a
 * real PlacedItem. Resolve the explicit document's native collection instead. */
const linked = makeItem(doc.layers[0], 'PlacedItem', [1, 2, 3, 0]);
const misleading = {...linked, typename: 'GroupItem'};
doc.getPageItemFromUuid = () => misleading;
assert.strictEqual(sandbox.Illona.findItem(doc, linked.uuid), linked);
docs[1].getPageItemFromUuid = () => misleading;
assert.throws(() => sandbox.Illona.findItem(docs[1], linked.uuid), /no longer exists/);
console.log('Host mock checks passed: coordinates, Bézier handles, Unicode, full prevalidation, missing fonts/objects, text style warning, coordinate restoration, native image subtype and document confinement.');
