/* Native-DOM simulation of trace_images. No Adobe process or image decoder. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=require('node:path').resolve(__dirname,'..');

function setup() {
  let next=0;
  const events=[],doc={typename:'Document',name:'Trace fixture',pageItems:[],layers:[],saved:false};
  const other={typename:'Document',name:'Unrelated saved document',pageItems:[],layers:[],saved:true};
  const layer={typename:'Layer',name:'Artwork',visible:true,locked:false,parent:doc};doc.layers.push(layer);
  const all=[];
  function pageItem(type,name,bounds=[0,100,100,0],parent=layer) {
    const q={typename:type,name,uuid:'trace-'+ ++next,parent,layer,editable:true,locked:false,hidden:false,
      opacity:100,geometricBounds:bounds.slice(),pageItems:[],pathItems:[]};
    q.remove=()=>{
      events.push(['remove',q.uuid]);
      if(q.failRemoveBefore)throw Error('Source remove failed before mutation');
      for(const child of doc.pageItems.slice())if(child.parent===q)child.remove();
      const index=doc.pageItems.indexOf(q);if(index>=0)doc.pageItems.splice(index,1);
      if(q.failRemoveAfter)throw Error('Source remove failed after mutation');
    };
    doc.pageItems.push(q);all.push(q);return q;
  }
  function image(type,name,behavior={}) {
    const q=pageItem(type,name);q.file={exists:behavior.missingFile!==true};
    q.failRemoveBefore=behavior.removeBefore;q.failRemoveAfter=behavior.removeAfter;
    q.duplicate=(relative,placement)=>{
      assert.equal(relative,q);assert.equal(placement,'before');events.push(['duplicate',q.uuid]);
      const copy=pageItem(type,name+' copy');
      copy.trace=()=>{
        events.push(['trace',copy.uuid]);
        if(behavior.traceError)throw Error('Native trace failed');
        copy.remove();
        const plugin=pageItem('PluginItem',name+' plugin');
        const state={ready:false,preset:null,ignoreWhite:null};plugin.traceState=state;
        const options={livePaintOutput:true,loadFromPreset:name=>{
          events.push(['preset',name]);state.preset=name;return behavior.presetFailure?false:true;
        }};
        Object.defineProperty(options,'ignoreWhite',{
          get:()=>state.ignoreWhite,
          set:value=>{if(!behavior.ignoreSetter)state.ignoreWhite=value;}
        });
        plugin.tracing={tracingOptions:options,expandTracing:viewed=>{
          assert.equal(viewed,false);assert.equal(state.ready,true,'redraw must finish tracing first');
          assert.equal(options.livePaintOutput,false,'Expanded output must not remain Live Paint');
          events.push(['expand',plugin.uuid]);
          if(behavior.expandError)throw Error('Native expand failed');
          plugin.remove();
          if(behavior.nonGroup)return pageItem('PluginItem','Not expanded');
          const group=pageItem('GroupItem',name+' vectors',[10,90,90,10]);
          if(!behavior.empty) {
            const nested=pageItem('GroupItem','Nested vectors',undefined,group);
            const compound=pageItem('CompoundPathItem','Compound vectors',undefined,nested);
            const first=pageItem('PathItem','Traced shape1',undefined,compound);
            const second=pageItem('PathItem','Traced shape2',undefined,group);
            compound.pathItems=[first];nested.pageItems=[compound];
            // A collection can also expose a descendant already counted inside
            // a nested group. UUID de-duplication must keep counts accurate.
            group.pageItems=[nested,first,second];
          }
          if(behavior.rasterResult)group.pageItems.push(pageItem('RasterItem','Unexpected raster',undefined,group));
          return group;
        }};
        return plugin;
      };
      return copy;
    };
    return q;
  }
  const app={documents:[doc,other],activeDocument:other,userInteractionLevel:'display',tracingPresetsList:['16 Colors','Black and White Logo'],
    redraw:()=>{events.push(['redraw']);for(const q of all)if(q.traceState)q.traceState.ready=true;}};
  const context={app,$:{global:{}},CoordinateSystem:{DOCUMENTCOORDINATESYSTEM:'document'},
    UserInteractionLevel:{DONTDISPLAYALERTS:'quiet'},ElementPlacement:{PLACEBEFORE:'before'}};
  vm.createContext(context);
  for(const filename of ['core.jsx','creold_actions.jsx'])vm.runInContext(fs.readFileSync(root+'/illona_mcp/host/'+filename,'utf8'),context);
  const documentId=vm.runInContext('Illona.docId(app.documents[0])',context);
  function run(ids,options={}) {
    context.input=JSON.stringify({document_id:documentId,action:'trace_images',object_ids:ids,options});
    return vm.runInContext("Illona.run('creold_action',JSON.parse(input))",context);
  }
  return {doc,other,app,events,pageItem,image,run};
}

for(const type of ['PlacedItem','RasterItem']) {
  const t=setup(),image=t.image(type,'Official source');
  const result=t.run([image.uuid]);
  assert.equal(result.ok,true,JSON.stringify(result));assert.equal(result.data.success,true);
  assert.equal(result.data.created_count,1);assert.equal(result.data.replaced_count,1);
  assert.equal(result.data.created[0].type,'GroupItem');
  const traced=result.data.traces[0];assert.notEqual(traced.created_id,image.uuid);
  assert.equal(traced.vector_only,true);assert.equal(traced.counts.path_count,2);
  assert.equal(traced.counts.raster_count,0);assert.equal(traced.counts.placed_count,0);assert.equal(traced.counts.plugin_count,0);
  assert.equal(traced.bounds_preserved,false,'Ignoring white may crop the native result');
  assert.equal(traced.ignore_white,true);assert(!t.doc.pageItems.includes(image));
  assert.equal(t.app.activeDocument,t.other);assert.equal(t.app.userInteractionLevel,'display');
  const operations=t.events.map(e=>e[0]);assert(operations.indexOf('redraw')<operations.indexOf('expand'));
}

{
  const t=setup(),image=t.image('RasterItem','Black artwork');
  const result=t.run([image.uuid],{preset:'Black and White Logo',ignore_white:false});
  assert.equal(result.data.success,true);assert.equal(result.data.traces[0].ignore_white,false);
  assert.equal(t.events.find(e=>e[0]==='preset')[1],'Black and White Logo');
}

for(const invalid of ['preset','type','missingFile','limit','missingUuid']) {
  const t=setup(),image=t.image('PlacedItem','Source');let ids=[image.uuid],options={};
  if(invalid==='preset')options={preset:'Unavailable preset'};
  if(invalid==='type')ids.push(t.pageItem('GroupItem','Explicit group is not an image').uuid);
  if(invalid==='missingFile')ids.push(t.image('PlacedItem','Broken link',{missingFile:true}).uuid);
  if(invalid==='limit')ids=Array.from({length:11},(_,i)=>t.image('RasterItem','Too many'+i).uuid);
  if(invalid==='missingUuid')ids.push('unknown-native-uuid');
  const result=t.run(ids,options);assert.equal(result.ok,false,JSON.stringify(result));
  assert.equal(t.events.length,0,'Every target and preset must be validated before the first mutation');
  assert(t.doc.pageItems.includes(image));
}

for(const behavior of [{traceError:true},{presetFailure:true},{ignoreSetter:true},{expandError:true},{nonGroup:true},{empty:true},{rasterResult:true},{removeBefore:true}]) {
  const t=setup(),image=t.image('RasterItem','Keep source on failure',behavior);
  const result=t.run([image.uuid]);assert.equal(result.ok,true,JSON.stringify(result));
  assert.equal(result.data.success,false);assert.equal(result.data.partial,true);
  assert.equal(result.data.created_count,0);assert.equal(result.data.errors[0].source_preserved,true);
  assert(t.doc.pageItems.includes(image));
  assert.equal(t.doc.pageItems.length,1,'A failed trace must discard all temporary descendants');
  assert(!t.doc.pageItems.some(q=>q.typename==='PluginItem'),'A failed trace must discard its temporary plug-in');
  assert.equal(t.app.activeDocument,t.other);assert.equal(t.app.userInteractionLevel,'display');
}

{
  const t=setup(),image=t.image('RasterItem','Remove commits then throws',{removeAfter:true});
  const result=t.run([image.uuid]);assert.equal(result.data.success,false);assert.equal(result.data.partial,true);
  assert.equal(result.data.created_count,1,'Keep verified vectors if removing the source already committed');
  assert.equal(result.data.errors[0].source_preserved,false);assert(!t.doc.pageItems.includes(image));
  assert(t.doc.pageItems.some(q=>q.uuid===result.data.created[0].id));
}
{
  const t=setup(),first=t.image('RasterItem','Successful first image'),second=t.image('PlacedItem','Second native failure',{traceError:true});
  const result=t.run([first.uuid,second.uuid]);
  assert.equal(result.data.success,false);assert.equal(result.data.partial,true);
  assert.equal(result.data.created_count,1);assert.equal(result.data.replaced_count,1);
  assert(!t.doc.pageItems.includes(first));assert(t.doc.pageItems.includes(second));
  assert.equal(result.data.errors[0].object_id,second.uuid);
}
console.log('PASS: trace_images expands placed/embedded images into paths, verifies zero raster/plugin descendants, validates all inputs before mutation and retains sources on failure.');
