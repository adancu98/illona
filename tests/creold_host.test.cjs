/* Offline checks of the 13 Creold paint/geometry actions. Tracing has its own fixture. No Adobe process. */
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const root=require('node:path').resolve(__dirname,'..');
const doc={typename:'Document',name:'Mock',pageItems:[],layers:[],artboards:[{artboardRect:[0,300,210,0]}],saved:false,fullName:{exists:false},documentColorSpace:'RGB'};
let serial=0;
const layer={typename:'Layer',name:'Main',visible:true,locked:false,parent:doc};doc.layers.push(layer);
function item(type,name){const q={uuid:name,name,typename:type,parent:layer,layer,editable:true,locked:false,hidden:false,opacity:50,filled:true,stroked:true,strokeWidth:2,geometricBounds:[.2,20.3,10.2,10.3],visibleBounds:[.2,20.3,10.2,10.3],pathPoints:[{anchor:[0,0],leftDirection:[-1,0],rightDirection:[1,0]},{anchor:[10,10],leftDirection:[9,10],rightDirection:[11,10]}]};q.translate=(x,y)=>{q.geometricBounds=q.geometricBounds.map((v,i)=>v+(i%2?y:x));if(q.anchor)q.anchor=[q.anchor[0]+x,q.anchor[1]+y];};q.zOrder=()=>{};q.remove=()=>doc.pageItems.splice(doc.pageItems.indexOf(q),1);doc.pageItems.push(q);return q;}
function rgb(r,g,b){return {typename:'RGBColor',red:r,green:g,blue:b};}
function grad(stops){const a=[];a.add=()=>add({color:rgb(0,0,0),opacity:100,midPoint:50,rampPoint:50});function add(s){const v={color:s.color,opacity:s.opacity,midPoint:s.midPoint};let p=s.rampPoint;Object.defineProperty(v,'rampPoint',{get:()=>p,set:x=>{p=x;a.sort((x,y)=>x.rampPoint-y.rampPoint);}});v.remove=()=>a.splice(a.indexOf(v),1);a.push(v);a.sort((x,y)=>x.rampPoint-y.rampPoint);return v;}stops.forEach(add);const q={name:'Original',type:'LINEAR',gradientStops:a};q.remove=()=>doc.gradients.splice(doc.gradients.indexOf(q),1);return q;}
doc.gradients=[];doc.gradients.add=()=>{const g=grad([{color:rgb(0,0,0),opacity:100,midPoint:50,rampPoint:0},{color:rgb(255,255,255),opacity:100,midPoint:50,rampPoint:100}]);doc.gradients.push(g);return g;};
const original=grad([{color:rgb(10,0,0),opacity:30,midPoint:50,rampPoint:10},{color:rgb(20,0,0),opacity:70,midPoint:50,rampPoint:40},{color:rgb(30,0,0),opacity:100,midPoint:50,rampPoint:90}]);doc.gradients.push(original);
const a=item('PathItem','a'),b=item('PathItem','b'),g=item('PathItem','g'),u=item('PathItem','unselected');a.fillColor=rgb(10,20,30);b.fillColor=rgb(110,120,130);b.strokeWidth=4;g.fillColor={typename:'GradientColor',gradient:original,angle:37,origin:[2,3],length:100};u.fillColor={typename:'GradientColor',gradient:original};
const t1=item('TextFrame','t1'),t2=item('TextFrame','t2');t1.kind=t2.kind='POINT';t1.anchor=[10,100];t2.anchor=[20,60];
layer.pathItems={rectangle:(top,left,w,h)=>{const q=item('PathItem','new-'+ ++serial);q.geometricBounds=[left,top,left+w,top-h];return q;}};doc.layers.add=()=>{throw Error('Unexpected extra layer');};
const context={app:{documents:[doc],name:'Illustrator',version:'30.8.2',coordinateSystem:'board'},$:{global:{}},DocumentColorSpace:{RGB:'RGB',CMYK:'CMYK'},CoordinateSystem:{DOCUMENTCOORDINATESYSTEM:'doc'},TextType:{POINTTEXT:'POINT'},ZOrderMethod:{SENDTOBACK:'back'},RGBColor:function(){this.typename='RGBColor';},CMYKColor:function(){this.typename='CMYKColor';},GrayColor:function(){this.typename='GrayColor';}};
vm.createContext(context);for(const f of ['core.jsx','creold_actions.jsx'])vm.runInContext(fs.readFileSync(root+'/illona_mcp/host/'+f,'utf8'),context);
const docId=vm.runInContext('Illona.docId(app.documents[0])',context);
function run(action,ids,options={}){context.input=JSON.stringify({document_id:docId,action,object_ids:ids,options});const r=vm.runInContext("Illona.run('creold_action',JSON.parse(input))",context);assert.equal(r.ok,true,JSON.stringify(r));assert.equal(r.data.success,true,JSON.stringify(r));return r.data;}
function near(a,b){assert(Math.abs(a-b)<1e-7,`${a} != ${b}`);}
run('reverse_gradient_colors',['g']);assert.notEqual(g.fillColor.gradient,original);assert.equal(u.fillColor.gradient,original);assert.deepEqual(original.gradientStops.map(s=>s.color.red),[10,20,30]);assert.deepEqual(g.fillColor.gradient.gradientStops.map(s=>s.color.red),[30,20,10]);assert.deepEqual(g.fillColor.gradient.gradientStops.map(s=>s.opacity),[100,70,30]);assert.equal(g.fillColor.angle,37);
run('distribute_gradient_stops',['g']);assert.deepEqual(g.fillColor.gradient.gradientStops.map(s=>s.rampPoint),[10,50,90]);
run('cycle_gradient_colors',['g'],{steps:1});assert.deepEqual(g.fillColor.gradient.gradientStops.map(s=>s.color.red),[10,30,20]);
run('remove_gradient_stops',['g']);assert.equal(g.fillColor.gradient.gradientStops.length,2);
run('stroke_color_from_fill',['a'],{width_pt:2});assert.equal(a.strokeColor.red,10);
run('average_stroke_width',['a','b']);assert.equal(a.strokeWidth,3);assert.equal(b.strokeWidth,3);
run('align_text_baselines',['t1','t2'],{baseline_y_pt:120,spacing_pt:20});assert.equal(t1.anchor[1],120);assert.equal(t2.anchor[1],100);
run('round_coordinates',['a']);near((a.geometricBounds[0]+a.geometricBounds[2])/2,5);near((a.geometricBounds[1]+a.geometricBounds[3])/2,15);
run('set_point_coordinates',['a'],{point_indices:[1],x_pt:50});assert.deepEqual(Array.from(a.pathPoints[1].anchor),[50,10]);assert.deepEqual(Array.from(a.pathPoints[1].leftDirection),[49,10]);
run('transform_points',['a'],{point_indices:[1],scale_x_pct:200,angle_deg:90,origin_x_pt:0,origin_y_pt:0});near(a.pathPoints[1].anchor[0],-10);near(a.pathPoints[1].anchor[1],100);near(a.pathPoints[1].leftDirection[1],98);
const r=run('draw_artboard_rectangles',[],{artboard_indices:[0],bleed_pt:3,layer_name:'Main'});assert.equal(r.created_count,1);assert.deepEqual(Array.from(r.created[0].bounds? [r.created[0].bounds.left,r.created[0].bounds.top,r.created[0].bounds.right,r.created[0].bounds.bottom]:[]),[-3,303,213,-3]);
run('change_opacity',['a'],{value:42});assert.equal(a.opacity,42);
run('change_opacity',['a'],{mode:'multiply',value:0.5});assert.equal(a.opacity,21);
run('change_opacity',['a'],{mode:'delta',value:19});assert.equal(a.opacity,40);
run('average_colors',['a','b']);assert.equal(a.fillColor.red,60);assert.equal(b.fillColor.blue,80);
run('average_colors',['unselected'],{average_method:'rms'});near(u.fillColor.red,Math.sqrt((100+400+900)/3));
context.input=JSON.stringify({document_id:docId,action:'change_opacity',object_ids:['a','MISSING'],options:{value:10}});const bad=vm.runInContext("Illona.run('creold_action',JSON.parse(input))",context);assert.equal(bad.ok,false);assert.equal(a.opacity,40);
context.input=JSON.stringify({document_id:docId,action:'set_point_coordinates',object_ids:['a','b'],options:{point_indices:[99],x_pt:8}});const old=JSON.stringify(a.pathPoints);assert.equal(vm.runInContext("Illona.run('creold_action',JSON.parse(input))",context).ok,false);assert.equal(JSON.stringify(a.pathPoints),old);
console.log('PASS: 13 paint/geometry actions, gradient isolation/order/opacity, handle preservation, point rotation, baseline spacing, artboard bleed, average widths/colors, and full missing-ID/index prevalidation.');
