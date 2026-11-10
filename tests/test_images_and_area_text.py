"""Typed raster placement and editable area text without a native Adobe process."""

import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from illona_mcp.models import Element


HOST = Path(__file__).resolve().parents[1] / "illona_mcp" / "host"
HARNESS = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const request = JSON.parse(process.argv[1]), host = process.argv[2];
let serial = 0;
const doc = {name:'Mock', documentColorSpace:'RGB', artboards:[{name:'Board',artboardRect:[0,500,500,0]}], layers:[], pageItems:[], saved:false};
function removeFrom(list, value) { const i=list.indexOf(value); if(i>=0)list.splice(i,1); }
function layerOf(node) {let p=node; while(p && p.typename!=='Layer')p=p.parent; return p;}
function node(parent,type,bounds) {
  const n={uuid:'uuid-'+(++serial),typename:type,name:'',parent,locked:false,hidden:false,editable:true,opacity:100,_bounds:bounds||[0,0,0,0],_children:[]};
  // Illustrator inserts newly created artwork at the front of its container.
  parent._children.unshift(n);doc.pageItems.push(n);
  Object.defineProperties(n,{
    layer:{get(){return layerOf(this.parent);}},
    geometricBounds:{get(){return this._bounds;}},
    width:{get(){return this._bounds[2]-this._bounds[0];},set(w){this._bounds[2]=this._bounds[0]+w;}},
    height:{get(){return this._bounds[1]-this._bounds[3];},set(h){this._bounds[3]=this._bounds[1]-h;}},
    position:{get(){return this._bounds.slice(0,2);},set(p){const w=this.width,h=this.height;this._bounds=[p[0],p[1],p[0]+w,p[1]-h];}},
  });
  n.move=function(parent,placement){
    if(placement!=='beginning' && placement!=='end')throw Error('unsupported placement: '+placement);
    removeFrom(this.parent._children,this);this.parent=parent;this.move_placement=placement;
    if(placement==='beginning')parent._children.unshift(this);else parent._children.push(this);
  };
  n.remove=function(){for(const c of [...this._children])c.remove();removeFrom(this.parent._children,this);removeFrom(doc.pageItems,this);};
  n.zOrder=function(){removeFrom(this.parent._children,this);this.parent._children.unshift(this);};
  n.resize=function(x,y){this.width*=x/100;this.height*=y/100;};
  if(type==='GroupItem')n.pathItems=paths(n);
  return n;
}
function paths(parent){return {
  rectangle(top,left,width,height){return node(parent,'PathItem',[left,top,left+width,top-height]);},
  ellipse(top,left,width,height){return node(parent,'PathItem',[left,top,left+width,top-height]);},
};}
function text(parent,bounds,kind){
  const n=node(parent,'TextFrame',bounds);n.kind=kind;
  n.textRange={characterAttributes:{tracking:700,horizontalScale:55,verticalScale:140,baselineShift:30,strokeWeight:2,overprintFill:true},
    paragraphAttributes:{justification:'right',leftIndent:50,rightIndent:10,firstLineIndent:20,spaceBefore:15,spaceAfter:18,hyphenation:true}};
  if(kind==='area')n.textPath={filled:true,stroked:true};
  Object.defineProperty(n,'contents',{get(){return this._text||'';},set(s){this.layer_at_contents=this.layer.name;this._text=s;}});
  return n;
}
function newLayer(name,printable=true){
  const l={name,typename:'Layer',parent:doc,visible:true,locked:false,printable,_children:[]};
  l.pathItems=paths(l);l.groupItems={add(){return node(l,'GroupItem');}};
  l.textFrames={add(){return text(l,[0,0,0,0],'point');}};
  l.placedItems={add(){
    const p=node(l,'PlacedItem');
    Object.defineProperty(p,'file',{set(file){
      if(request.failDecode)throw Error('native image decoder rejected the file');
      this._file=file.fsName;
      const b=fs.readFileSync(file.fsName);this.width=b.readUInt32BE(16);this.height=b.readUInt32BE(20);
    }});
    p.embed=function(){
      if(request.failEmbed)throw Error('native embed failed');
      const raster=node(this.parent,'RasterItem',this._bounds.slice());raster._file=this._file;this.remove();
    };
    return p;
  }};
  l.remove=function(){for(const c of [...this._children])c.remove();removeFrom(doc.layers,this);};
  doc.layers.push(l);return l;
}
const guides=newLayer('Guides',false);
doc.layers.add=()=>newLayer('');
doc.textFrames={areaText(pathItem){const b=pathItem.geometricBounds.slice();pathItem.remove();return text(guides,b,'area');}};
doc.getPageItemFromUuid=id=>doc.pageItems.find(item=>item.uuid===id);
function File(filename){this.fsName=filename;}
Object.defineProperties(File.prototype,{exists:{get(){return fs.existsSync(this.fsName);}},length:{get(){return fs.statSync(this.fsName).size;}}});
File.prototype.open=function(){this._data=fs.readFileSync(this.fsName).toString('latin1');return true;};
File.prototype.read=function(n){return this._data.slice(0,n);};File.prototype.close=function(){};
const font={name:'ArialMT',family:'Arial',style:'Regular'};const fonts=[font];let fontLookups=0;
fonts.getByName=n=>{
  fontLookups++;
  if(n==='ArialMT' && !(request.failFontAfter!==undefined && fontLookups>request.failFontAfter))return font;
  throw Error('missing font');
};
const sandbox={File,$:{global:{}},app:{name:'Illustrator',version:'30.8',documents:[doc],textFonts:fonts,coordinateSystem:'document',redraw(){}},
  DocumentColorSpace:{RGB:'RGB',CMYK:'CMYK'},CoordinateSystem:{DOCUMENTCOORDINATESYSTEM:'document'},ElementPlacement:{PLACEATBEGINNING:'beginning',PLACEATEND:'end'},ZOrderMethod:{BRINGTOFRONT:'front'},Justification:{LEFT:'left'},
  RGBColor:function(){this.typename='RGBColor';},CMYKColor:function(){this.typename='CMYKColor';},NoColor:function(){this.typename='NoColor';},PointType:{CORNER:'corner',SMOOTH:'smooth'}};
vm.createContext(sandbox);
for(const name of ['core.jsx','drawing.jsx'])new vm.Script(fs.readFileSync(path.join(host,name),'utf8')).runInContext(sandbox);
const id=vm.runInContext('Illona.ops.status({}).documents[0].id',sandbox);
sandbox.input=JSON.stringify({document_id:id,units:'pt',layer_name:'Print',elements:request.elements});
const result=vm.runInContext("Illona.run('create_elements',JSON.parse(input))",sandbox);
let updateResult=null;
if(result.ok && request.updateFirstText){
  const target=doc.pageItems.find(n=>n.typename==='TextFrame');
  sandbox.updateInput=JSON.stringify({document_id:id,units:'pt',changes:[{id:target.uuid,...request.updateFirstText}]});
  updateResult=vm.runInContext("Illona.run('update_objects',JSON.parse(updateInput))",sandbox);
}
const objects=doc.pageItems.map(n=>({id:n.uuid,name:n.name,type:n.typename,parent:n.parent.typename,layer:n.layer.name,width:n.width,height:n.height,position:n.position,clipping:!!n.clipping,clipped:!!n.clipped,children:n._children.map(c=>c.uuid),text:n._text,kind:n.kind,layer_at_contents:n.layer_at_contents,move_placement:n.move_placement,character:n.textRange&&n.textRange.characterAttributes,paragraph:n.textRange&&n.textRange.paragraphAttributes,text_path:n.textPath}));
const layer_stacks=doc.layers.map(l=>({name:l.name,front_to_back:l._children.map(n=>n.uuid)}));
process.stdout.write(JSON.stringify({result,updateResult,objects,layers:doc.layers.map(l=>l.name),layer_stacks,created_node_count:serial,font_lookups:fontLookups}));
"""


def png_header(path, width=400, height=200):
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\0\0\0" + b"\0" * 4)
    return str(path)


def host(request):
    executable = shutil.which("node") or str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
    if not Path(executable).is_file():
        pytest.skip("Node is unavailable for host mock verification")
    result = subprocess.run([executable, "-e", HARNESS, json.dumps(request), str(HOST)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout)


def image(path, **overrides):
    return {"type": "image", "path": path, "x": 10, "y": 20, "width": 100, "height": 100, **overrides}


def test_model_accepts_images_and_area_text_but_rejects_incomplete_geometry():
    assert Element.model_validate(image("/assets/photo.png")).embed is True
    assert Element.model_validate({"type": "text", "text": "Area", "width": 100, "height": 40}).width == 100
    invalid = [
        {"type": "text", "text": "Area", "width": 100},
        {"type": "text", "text": "Area", "height": 40},
        image("relative/photo.png"), image("/assets/logo.svg"), image("/assets/photo.png", width=None),
        {"type": "image", "path": "/assets/photo.png", "width": 100, "height": 100},
        image("/assets/photo.png", fit="stretch"),
    ]
    for value in invalid:
        with pytest.raises(ValidationError):
            Element.model_validate(value)


def test_missing_or_invalid_asset_prevalidation_prevents_entire_batch_mutation(tmp_path):
    invalid = tmp_path / "corrupt.png"
    invalid.write_bytes(b"this is not a PNG")
    for path in (str(tmp_path / "missing.png"), str(invalid)):
        output = host({"elements": [{"type": "rect", "x": 0, "y": 0, "width": 10, "height": 10}, image(path)]})
        assert output["result"]["ok"] is False
        assert output["result"]["error"]["code"] in {"IMAGE_NOT_FOUND", "INVALID_IMAGE"}
        assert output["objects"] == [] and output["layers"] == ["Guides"]


def test_contain_preserves_aspect_centers_embedded_raster_and_returns_stable_group_id(tmp_path):
    output = host({"elements": [image(png_header(tmp_path / "wide.png"))]})
    assert output["result"]["ok"] is True
    group = next(item for item in output["objects"] if item["type"] == "GroupItem")
    raster = next(item for item in output["objects"] if item["type"] == "RasterItem")
    assert not any(item["type"] == "PlacedItem" for item in output["objects"])
    assert (raster["width"], raster["height"]) == pytest.approx((100, 50))
    assert raster["position"] == pytest.approx([10, 455])
    assert raster["id"] in group["children"]
    assert output["result"]["data"]["created"][0]["id"] == group["id"]
    assert group["layer"] == "Print" and group["clipped"] is False


def test_cover_keeps_link_when_requested_and_crops_with_topmost_vector_mask(tmp_path):
    output = host({"elements": [image(png_header(tmp_path / "wide.png"), fit="cover", embed=False)]})
    assert output["result"]["ok"] is True
    group = next(item for item in output["objects"] if item["type"] == "GroupItem")
    placed = next(item for item in output["objects"] if item["type"] == "PlacedItem")
    mask = next(item for item in output["objects"] if item["clipping"])
    assert (placed["width"], placed["height"]) == pytest.approx((200, 100))
    assert placed["position"] == pytest.approx([-40, 480])
    assert mask["position"] == pytest.approx([10, 480])
    assert (mask["width"], mask["height"]) == pytest.approx((100, 100))
    assert group["clipped"] and group["children"][0] == mask["id"]


def test_area_text_moves_to_print_layer_before_content_and_point_text_stays_compatible():
    output = host({"elements": [
        {"type": "text", "text": "Romanian area text", "x": 20, "y": 30, "width": 180, "height": 50, "font": "ArialMT"},
        {"type": "text", "text": "Point text", "x": 7, "y": 9},
    ]})
    assert output["result"]["ok"] is True
    area = next(item for item in output["objects"] if item.get("kind") == "area")
    point = next(item for item in output["objects"] if item.get("kind") == "point")
    assert area["layer"] == area["layer_at_contents"] == "Print"
    assert area["position"] == pytest.approx([20, 470])
    assert (area["width"], area["height"]) == pytest.approx((180, 50))
    assert point["position"] == pytest.approx([7, 491])
    assert not any(item["type"] == "PathItem" for item in output["objects"])


def test_area_text_created_after_same_layer_background_is_frontmost():
    output = host({"elements": [
        {"type": "rect", "name": "Page background", "x": 0, "y": 0,
         "width": 500, "height": 500, "fill": "#F6F0E5"},
        {"type": "text", "name": "Headline", "text": "Visible above the page",
         "x": 20, "y": 30, "width": 180, "height": 50, "font": "ArialMT"},
    ]})
    assert output["result"]["ok"] is True
    background = next(item for item in output["objects"] if item["name"] == "Page background")
    headline = next(item for item in output["objects"] if item["name"] == "Headline")
    assert headline["layer"] == headline["layer_at_contents"] == background["layer"] == "Print"
    assert headline["move_placement"] == "beginning"
    stack = next(layer for layer in output["layer_stacks"] if layer["name"] == "Print")
    assert stack["front_to_back"] == [headline["id"], background["id"]]


@pytest.mark.parametrize("font,settings,expected_created", [
    ("MissingFont", {}, 0),
    ("ArialMT", {"failFontAfter": 2}, 3),
])
def test_missing_font_leaves_no_partial_background_or_area_text(font, settings, expected_created):
    output = host({**settings, "elements": [
        {"type": "rect", "name": "Page background", "x": 0, "y": 0,
         "width": 500, "height": 500, "fill": "#F6F0E5"},
        {"type": "text", "name": "Headline", "text": "Needs a valid font",
         "x": 20, "y": 30, "width": 180, "height": 50, "font": font},
    ]})
    assert output["result"]["ok"] is False
    assert output["result"]["error"]["code"] == "FONT_NOT_FOUND"
    assert output["created_node_count"] == expected_created
    assert output["objects"] == [] and output["layers"] == ["Guides"]
    assert output["layer_stacks"] == [{"name": "Guides", "front_to_back": []}]
    if expected_created:
        # The font disappears after both validations. Failure therefore occurs
        # after the background and area frame exist, exercising actual cleanup.
        assert output["font_lookups"] == 3
        assert "text.font" in output["result"]["error"]["message"]


def test_native_decode_or_embed_failure_cleans_up_placed_art_and_earlier_elements(tmp_path):
    asset = png_header(tmp_path / "wide.png")
    for failure in ("failDecode", "failEmbed"):
        output = host({failure: True, "elements": [
            {"type": "rect", "x": 0, "y": 0, "width": 10, "height": 10}, image(asset),
        ]})
        assert output["result"]["ok"] is False
        assert output["objects"] == [] and output["layers"] == ["Guides"]


def test_new_text_resets_inherited_offsets_before_applying_explicit_style():
    output = host({"elements": [
        {"type": "text", "text": "Area heading", "x": 20, "y": 30, "width": 180, "height": 50, "tracking": 35, "size_pt": 18},
        {"type": "text", "text": "Point label", "x": 7, "y": 9},
    ]})
    assert output["result"]["ok"] is True
    frames = [item for item in output["objects"] if item["type"] == "TextFrame"]
    area, point = frames
    for frame in [area]:
        assert frame["paragraph"] == {"justification": "left", "leftIndent": 0, "rightIndent": 0, "firstLineIndent": 0, "spaceBefore": 0, "spaceAfter": 0, "hyphenation": False}
        attrs = frame["character"]
        assert attrs["horizontalScale"] == attrs["verticalScale"] == 100
        assert attrs["baselineShift"] == 0
        assert attrs["overprintFill"] is False
    assert area["character"]["tracking"] == 35 and area["character"]["size"] == 18
    assert area["text_path"] == {"filled": False, "stroked": False}
    # Point text follows its previously native-tested path without paragraph resets.
    assert point["character"]["tracking"] == 700


def test_update_objects_preserves_existing_tracking_while_changing_font_size():
    output = host({"elements": [{"type": "text", "text": "Existing style", "x": 7, "y": 9, "tracking": 42}], "updateFirstText": {"size_pt": 28}})
    assert output["result"]["ok"] and output["updateResult"]["ok"]
    frame = next(item for item in output["objects"] if item["type"] == "TextFrame")
    assert frame["character"]["tracking"] == 42
    assert frame["character"]["size"] == 28
