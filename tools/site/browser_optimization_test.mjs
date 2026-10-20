/* Real-browser acceptance of the additive, saved-data optimization chapter.
 * Complements both historical runners; performs no scientific model calls. */
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

const deps=process.env.BROWSER_DEPS;
if(!deps)throw new Error('BROWSER_DEPS must point to locked browser-only dependencies');
const require=createRequire(path.join(path.resolve(deps),'package.json'));
const puppeteer=require('puppeteer-core'),axe=require.resolve('axe-core/axe.min.js');
const base=process.env.SITE_URL||'http://127.0.0.1:8768/';
const out=path.resolve(process.env.QA_OUT||'optimization-browser-qa');
fs.mkdirSync(out,{recursive:true});
let commit=null;
try{commit=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();}catch{}
const report={status:'RUNNING',tested_commit:commit,base,views:[],functional:[],
 accessibility:[],downloads:[],failure_modes:[],errors:[],new_scientific_calls:0};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',
 headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
const p=await browser.newPage();
p.on('pageerror',e=>report.errors.push(e.message));
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const ready=page=>page.waitForFunction(()=>document.body.dataset.ready==='true'&&
 document.body.dataset.optimizationReady==='true'&&document.getElementById('optimization').classList.contains('active'),{timeout:30000});
const state=()=>p.evaluate(()=>window.optimizationExhibit.getState());
async function locate(hash){
 await p.evaluate(h=>location.hash=h,hash);
 await p.waitForFunction(()=>document.getElementById('optimization').classList.contains('active'));
 await wait(80);
}
async function theme(name){
 await p.evaluate(name=>{if((document.documentElement.dataset.theme==='dark')!==(name==='dark'))document.getElementById('theme').click();},name);
}
// The existing site scrolls smoothly. Check a stable hit target before native
// pointer input; do not let an in-flight scroll manufacture a wrong click.
async function scrollForClick(page,selector){
 await page.$eval(selector,el=>new Promise((resolve,reject)=>{
  let previous=null,stable=0;const began=performance.now();
  el.scrollIntoView({block:'center'});
  function inspect(){
   const r=el.getBoundingClientRect(),box=[r.x,r.y,r.width,r.height];
   stable=previous&&box.every((x,i)=>Math.abs(x-previous[i])<.1)?stable+1:0;previous=box;
   const x=r.left+r.width/2,y=r.top+r.height/2,hit=document.elementFromPoint(x,y);
   if(stable>=6&&r.width>0&&r.height>0&&x>0&&x<innerWidth&&y>0&&y<innerHeight&&(hit===el||el.contains(hit))){resolve();return;}
   if(performance.now()-began>5000){reject(new Error('Scroll target did not settle: '+el.id));return;}
   requestAnimationFrame(inspect);
  }requestAnimationFrame(inspect);
 }));
}
async function click(selector){await scrollForClick(p,selector);await p.click(selector);}
async function exactStaticRows(page,payload){
 const rows=await page.$$eval('#optimization [data-opt-state]',els=>els.map(el=>({
  id:el.dataset.optState,evidence:el.dataset.optEvidence,source:el.dataset.optSource,
  values:[...el.querySelectorAll('[data-opt-value]')].map(x=>Number(x.dataset.optValue)),
  text:el.textContent
 })));
 assert.deepEqual(rows.map(r=>r.id),payload.theory.main4500.states.map(r=>r.id));
 for(const row of rows){
  const source=payload.theory.main4500.states.find(s=>s.id===row.id);
  assert.equal(row.evidence,source.evidence_status,`${row.id} evidence class`);
  assert.equal(row.source,source.source_id,`${row.id} source identity`);
  if(source.native_J===null){assert.deepEqual(row.values,[]);assert.match(row.text,/not measured|unmeasured/i);}
  else assert.deepEqual(row.values,[source.native_J],`${row.id} exact native J`);
 }
 return rows;
}
async function axis(){return p.$eval('#opt-state-chart',el=>({min:Number(el.dataset.optLogMin),max:Number(el.dataset.optLogMax)}));}
async function exactPlottedValues(page,payload){
 const marks=await page.$$eval('#opt-state-chart [data-opt-mark]',els=>els.map(el=>({
  id:el.dataset.optMark,value:Number(el.dataset.optPlotValue),left:parseFloat(el.style.left),
  sourceLeft:Number(el.getAttribute('style').match(/left:\s*([\d.eE+-]+)%/)[1])
 })));
 const measured=payload.theory.main4500.states.filter(s=>s.native_J!==null);
 assert.deepEqual(marks.map(m=>m.id),measured.map(s=>s.id),'six measured marks; no invented S3 point');
 for(const mark of marks){
  const expected=measured.find(s=>s.id===mark.id).native_J;
  const expectedPosition=(Math.log10(expected)+6)/7*100;
  assert.equal(mark.value,expected);
  assert.ok(Math.abs(mark.sourceLeft-expectedPosition)<1e-8,`${mark.id}: exact source coordinate`);
  // CSSOM serializes percentages to fewer significant digits than the source
  // attribute. Keep the data/formula check exact and bound that serialization.
  assert.ok(Math.abs(mark.left-expectedPosition)<5e-5,`${mark.id}: browser coordinate within 0.00005 percentage points`);
 }
 const forces=await page.$$eval('[data-opt-force-value]',els=>els.map(el=>({
  model:el.dataset.optForceModel,region:el.dataset.optForceRegion,value:Number(el.dataset.optForceValue),
  width:Number(el.parentElement.querySelector('.opt-force-fill').getAttribute('style').match(/width:\s*([\d.eE+-]+)%/)[1])
 })));
 assert.equal(forces.length,6);
 const forceAxis=await page.$eval('.opt-force-chart',el=>({min:Number(el.dataset.optForceMin),max:Number(el.dataset.optForceMax)}));
 assert.equal(forceAxis.min,0);assert.ok(forceAxis.max>=Math.max(...forces.map(f=>f.value)));
 for(const force of forces){
  assert.equal(force.value,payload.observer.end_terminal.pbe14.regional_rows.find(r=>r.region===force.region)[force.model]);
  assert.ok(Math.abs(force.width-force.value/forceAxis.max*100)<1e-8,'force bar uses the declared common scale');
 }
}

try{
 await p.setViewport({width:1440,height:1000,deviceScaleFactor:1});
 await p.goto(base+'?still&utm_source=chatgpt.com#optimization',{waitUntil:'networkidle0',timeout:45000});
 await ready(p);
 report.browser=await browser.version();
 const payload=await p.evaluate(()=>window.optimizationExhibit.data());
 assert.equal(payload.schema,'proton-optimization-v1');
 assert.equal(payload.scope.T2_executed,false);
 assert.equal(payload.scope.PBE14_role,'development');
 const states=payload.theory.main4500.states.map(s=>s.id),native=payload.theory.main4500.native_order;
 assert.deepEqual(states,['S0','S1','S1c','S2','S2q','S3','S4']);
 assert.deepEqual(native,['S0','S1','S2','S3','S4']);
 assert.deepEqual((await state()).readerOrder,states);
 assert.deepEqual((await state()).nativeOrder,native);
 const axes=await axis();
 assert.ok(Number.isFinite(axes.min)&&Number.isFinite(axes.max)&&axes.min<axes.max);
 for(const s of payload.theory.main4500.states.filter(s=>s.native_J!==null)){
  assert.ok(s.native_J>=10**axes.min&&s.native_J<=10**axes.max,`${s.id} inside fixed logarithmic range`);
 }
 await exactStaticRows(p,payload);
 await exactPlottedValues(p,payload);
 const uniqueIDs=await p.evaluate(()=>{
  const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);
  return ids.filter((id,i)=>ids.indexOf(id)!==i);
 });
 assert.deepEqual(uniqueIDs,[],'unique IDs across old and new chapters');
 report.functional.push('Canonical native-J rows, seven distinct source/evidence statuses, S3 missing value, fixed log10 range including S1');

 for(const width of [1920,1440,768,390,320]){
  await p.setViewport({width,height:width===1920?1080:width<=390?844:1000,deviceScaleFactor:1});
  await wait(250);
  for(const mode of ['light','dark']){
   await theme(mode);await locate('#optimization');await wait(100);
   const view=await p.evaluate(()=>{
    const section=document.getElementById('optimization'),nav=document.querySelector('nav'),link=document.querySelector('[data-route="optimization"]');
    const n=nav.getBoundingClientRect(),a=link.getBoundingClientRect();
    return {width:innerWidth,theme:document.documentElement.dataset.theme||'light',
     overflow:document.documentElement.scrollWidth>innerWidth+1,
     active:document.querySelectorAll('[data-page].active').length,
     routeCount:document.querySelectorAll('[data-page]').length,
     activeNavVisible:a.left>=n.left-1&&a.right<=n.right+1,
     activeNavCurrent:link.getAttribute('aria-current'),
     cyrillic:/[\u0400-\u04ff]/.test(section.innerText),
     stateButtons:section.querySelectorAll('[data-opt-select]').length,
     forceUnitCorrect:section.querySelector('.opt-checkpoint-force .panel-heading .micro').innerText.includes('eV/Å'),
     wrappedCounts:[...section.querySelectorAll('.opt-parameter-block>strong,.opt-gate-code')].filter(el=>{
      const range=document.createRange();range.selectNodeContents(el);
      return [...range.getClientRects()].filter(r=>r.width>0).length!==1;
     }).map(el=>el.textContent),
     staticCharts:section.querySelectorAll('#opt-state-chart,.opt-force-chart,.opt-parameter-strip,.opt-transaction').length,
     title:(section.querySelector('h1')?.innerText||section.querySelector('h2')?.innerText||'').replace(/\s+/g,' '),
     logLabel:/log(?:arithmic|10)?/i.test(document.getElementById('opt-state-chart').textContent),
     exactLimit:section.innerText.includes('Engineered and checked on synthetic runs. Not yet demonstrated to be a better real-data optimizer.')};
   });
   assert.equal(view.overflow,false,`${width}/${mode} document overflow`);
   assert.equal(view.active,1);assert.equal(view.routeCount,12);
   assert.equal(view.activeNavVisible,true,`${width}/${mode} active navigation access`);
   assert.ok(view.activeNavCurrent==='page'||view.activeNavCurrent==='true');
   assert.equal(view.cyrillic,false);assert.equal(view.stateButtons,7);
   assert.equal(view.forceUnitCorrect,true,`${width}/${mode} case-sensitive eV/Å unit`);
   assert.deepEqual(view.wrappedCounts,[],`${width}/${mode} complete numbers and evidence codes`);
   assert.equal(view.staticCharts,4);assert.equal(view.logLabel,true);assert.equal(view.exactLimit,true);
   assert.match(view.title,/The fit is not the finish/);
   await exactStaticRows(p,payload);await exactPlottedValues(p,payload);assert.deepEqual(await axis(),axes);
   report.views.push(view);
   await p.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
   await p.screenshot({path:path.join(out,`${mode}_${width}_optimization.png`),fullPage:true});
   await p.addScriptTag({path:axe});
   const violations=await p.evaluate(async()=>{
    const r=await axe.run(document.getElementById('optimization'),{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});
    return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}));
   });
   report.accessibility.push({width,mode,scope:'#optimization',violations});
   assert.deepEqual(violations,[],`${width}/${mode} scoped WCAG 2.0/2.1 AA`);
  }
 }

 await p.setViewport({width:1440,height:1000,deviceScaleFactor:1});await theme('light');
 for(const id of states){
  await click(`[data-opt-select="${id}"]`);
  assert.equal((await state()).selectedState,id);
  assert.equal((await state()).playing,false);
  assert.equal(await p.$eval(`[data-opt-select="${id}"]`,e=>e.getAttribute('aria-pressed')),'true');
  await exactStaticRows(p,payload);await exactPlottedValues(p,payload);assert.deepEqual(await axis(),axes);
 }
 report.functional.push('All seven reader states selectable without changing any plotted measurement or axis');
 for(const id of ['S1','S1c','S2q','S3']){
  await click(`[data-opt-select="${id}"]`);
  await p.screenshot({path:path.join(out,`light_1440_state_${id}.png`),fullPage:false});
 }
 await click('#opt-reset');assert.equal((await state()).selectedState,'S0');
 await click('#opt-next');assert.equal((await state()).selectedState,'S1');
 await click('#opt-next');assert.equal((await state()).selectedState,'S1c');
 await click('#opt-prev');assert.equal((await state()).selectedState,'S1');
 await p.focus('[data-opt-select="S1"]');await p.keyboard.press('ArrowRight');
 assert.equal((await state()).selectedState,'S1c');
 assert.equal(await p.evaluate(()=>document.activeElement.dataset.optSelect),'S1c');
 await p.keyboard.press('End');assert.equal((await state()).selectedState,'S4');
 await p.keyboard.press('Home');assert.equal((await state()).selectedState,'S0');
 const focus=await p.evaluate(()=>{
  const el=document.activeElement,s=getComputedStyle(el);
  return {id:el.dataset.optSelect,outlineStyle:s.outlineStyle,outlineWidth:parseFloat(s.outlineWidth),shadow:s.boxShadow};
 });
 assert.equal(focus.id,'S0');assert.ok((focus.outlineStyle!=='none'&&focus.outlineWidth>=1)||focus.shadow!=='none');
 report.functional.push('Reader-order previous/next, native keyboard Arrow/Home/End, focused selection and visible focus styling');

 await click('#opt-play');assert.equal((await state()).playing,true);
 await p.click('#opt-play');assert.equal((await state()).playing,false);
 await click('#opt-reset');
 await p.evaluate(()=>{
  window.__optSeen=[window.optimizationExhibit.getState().selectedState];
  window.__optObserver=new MutationObserver(()=>{
   const id=window.optimizationExhibit.getState().selectedState;
   if(window.__optSeen.at(-1)!==id)window.__optSeen.push(id);
  });
  window.__optObserver.observe(document.getElementById('opt-selection'),{subtree:true,childList:true,characterData:true,attributes:true});
 });
 await click('#opt-play');
 await p.waitForFunction(()=>!window.optimizationExhibit.getState().playing,{timeout:30000,polling:100});
 const visited=await p.evaluate(()=>{window.__optObserver.disconnect();return window.__optSeen;});
 assert.deepEqual(visited,native,'finite playback must exclude counterfactual branches');
 assert.equal((await state()).selectedState,'S4');
 await click('#opt-reset');assert.equal((await state()).selectedState,'S0');
 report.functional.push('Play/pause/reset and complete finite native sequence S0/S1/S2/S3/S4; no interpolated measurements or counterfactual trajectory');

 await click('#opt-play');
 await p.evaluate(()=>location.hash='#seeds');
 await p.waitForFunction(()=>window.exhibit.getState().route==='seeds');
 assert.equal((await state()).playing,false);
 await locate('#optimization');await click('#opt-reset');await click('#opt-play');
 const other=await browser.newPage();await other.goto('about:blank');await other.bringToFront();
 await p.waitForFunction(()=>document.hidden,{timeout:10000,polling:100});
 assert.equal((await state()).playing,false);
 await other.close();await p.bringToFront();
 report.functional.push('Playback stops on old-route navigation and actual background-tab visibility change');
 await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
 await click('[data-opt-select="S2q"]');await click('#opt-play');
 assert.equal((await state()).playing,false);assert.equal((await state()).reducedMotion,true);
 assert.equal((await state()).selectedState,'S2q');
 await click('[data-opt-select="S1c"]');assert.equal((await state()).selectedState,'S1c');
 report.functional.push('Reduced motion suppresses playback while preserving exact manual counterfactual inspection');
 await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'no-preference'}]);

 const sourceAnchors=await p.$$eval('#optimization a[href^="#opt-source-"]',els=>[...new Set(els.map(e=>e.getAttribute('href')))]);
 assert.ok(sourceAnchors.length>0);
 for(const hash of ['#opt-parameters','#opt-episode','#opt-checkpoints','#opt-candidate','#opt-evidence','#opt-next-study',sourceAnchors[0],sourceAnchors.at(-1)]){
  await p.goto(base+'?still'+hash,{waitUntil:'networkidle0'});await ready(p);
  const target=hash.slice(1);
  await p.waitForFunction(id=>{
   const el=document.getElementById(id);if(!el)return false;
   const r=el.getBoundingClientRect();
   return document.activeElement===el&&r.top>=-1&&r.top<innerHeight&&r.height>0;
  },{timeout:10000},target);
 }
 const brokenLocalLinks=await p.evaluate(()=>[...document.querySelectorAll('#optimization a[href^="#"]')]
  .map(e=>e.getAttribute('href')).filter(h=>!document.getElementById(h.slice(1).split('?')[0])));
 assert.deepEqual(brokenLocalLinks,[]);
 report.functional.push('Direct module/source deep links focus and reveal their targets, including sources inside details; all chapter hash links resolve');

 for(const [hash,route] of [['overview','overview'],['seeds','seeds'],['offpath','offpath'],['train119','train119'],['applicability','train119'],['forces?frame=145&atom=2','forces']]){
  await p.goto(base+'?utm_source=chatgpt.com&still#'+hash,{waitUntil:'networkidle0'});
  await p.waitForFunction(r=>document.body.dataset.ready==='true'&&window.exhibit.getState().route===r,{},route);
  assert.equal(await p.$$eval('[data-page].active',els=>els.length),1);
 }
 const readAnchor=await p.$eval('#longread [id^="read-"]',e=>e.id);
 await p.goto(base+'?utm_source=chatgpt.com&still#'+readAnchor,{waitUntil:'networkidle0'});
 await p.waitForFunction(()=>window.exhibit.getState().route==='longread');
 report.functional.push('UTM query, overview/seeds/offpath/train119, applicability/read-* aliases and force-parameter routing');
 await p.goto(base+'?fallback&still#optimization',{waitUntil:'networkidle0'});await ready(p);
 await p.evaluate(()=>location.hash='#molecule');
 await p.waitForFunction(()=>window.exhibit.getState().route==='molecule');
 assert.equal(await p.evaluate(()=>window.exhibit.renderers()['path-molecule']),'canvas-fallback');
 await locate('#optimization');await click('[data-opt-select="S2"]');
 assert.equal((await state()).selectedState,'S2');
 report.functional.push('Shared Canvas fallback leaves the independent static HTML chapter operational');

 const files=['OPTIMIZATION_STORY.json','CLAIM_DATA_MAP.tsv','PROVENANCE.json','PUBLICATION_ALLOWLIST.json','README.md'];
 const downloaded={};
 for(const file of files){
  const result=await p.evaluate(async url=>{const r=await fetch(url);return {status:r.status,text:await r.text()};},base+'data/optimization/'+file);
  assert.equal(result.status,200,file+' actual download');downloaded[file]=result.text;
  report.downloads.push({file,status:result.status,bytes:Buffer.byteLength(result.text),sha256:createHash('sha256').update(result.text).digest('hex')});
 }
 assert.deepEqual(JSON.parse(downloaded['OPTIMIZATION_STORY.json']),payload);
 assert.equal(downloaded['CLAIM_DATA_MAP.tsv'].trim().split('\n').length,91);
 const manifest=JSON.parse(downloaded['PUBLICATION_ALLOWLIST.json']);
 // The offline verifier checks every bundle hash. This browser checks delivered
 // bytes against that same manifest without assuming a self-hash for it.
 const records=Array.isArray(manifest.files)?manifest.files:Object.values(manifest.files||{});
 for(const r of report.downloads){
  const entry=records.find(x=>(x.file||x.path||x.name)===r.file);
  if(r.file!=='PUBLICATION_ALLOWLIST.json'){assert.ok(entry,r.file+' listed in allowlist');assert.equal(r.sha256,entry.sha256);}
 }
 report.functional.push('Five actual public downloads, 90-claim TSV and exact payload/hash agreement');

 const nojs=await browser.newPage();await nojs.setJavaScriptEnabled(false);
 await nojs.goto(base+'#optimization',{waitUntil:'networkidle0'});await exactStaticRows(nojs,payload);
 await exactPlottedValues(nojs,payload);
 const staticView=await nojs.$eval('#optimization',el=>({text:el.innerText,charts:el.querySelectorAll('#opt-state-chart,.opt-force-chart,.opt-parameter-strip,.opt-transaction').length,
  display:getComputedStyle(el).display,visibility:getComputedStyle(el).visibility,height:el.getBoundingClientRect().height,
  enabled:[...el.querySelectorAll('button')].filter(x=>!x.disabled).length}));
 assert.equal(staticView.charts,4);assert.ok(staticView.text.includes(payload.t1.statuses.visible_limit));
 assert.notEqual(staticView.display,'none');assert.equal(staticView.visibility,'visible');assert.ok(staticView.height>1000);
 assert.equal(staticView.enabled,0,'no inert button pretending to work without JavaScript');await nojs.close();
 report.functional.push('No-JavaScript complete state values, charts, evidence limits and safe disabled controls');

 for(const failure of ['aborted','http-503','malformed-json','wrong-schema']){
  const fail=await browser.newPage(),errors=[];fail.on('pageerror',e=>errors.push(e.message));
  await fail.setRequestInterception(true);
  fail.on('request',r=>{
   if(!r.url().endsWith('/data/optimization.json'))return r.continue();
   if(failure==='aborted')return r.abort();
   if(failure==='http-503')return r.respond({status:503,contentType:'application/json',body:'{"error":"unavailable"}'});
   if(failure==='malformed-json')return r.respond({status:200,contentType:'application/json',body:'{'});
   return r.respond({status:200,contentType:'application/json',body:'{"schema":"wrong"}'});
  });
  await fail.goto(base+'?still'+sourceAnchors[0],{waitUntil:'networkidle0'});
  await fail.waitForFunction(()=>document.body.dataset.optimizationReady==='error');
  await exactStaticRows(fail,payload);
  const fallback=await fail.$eval('#optimization',el=>({text:el.innerText,
   display:getComputedStyle(el).display,visibility:getComputedStyle(el).visibility,height:el.getBoundingClientRect().height,
   enabled:[...el.querySelectorAll('button')].filter(x=>!x.disabled).length,status:document.getElementById('opt-load-status').textContent}));
  assert.equal(fallback.enabled,0);assert.match(fallback.status,/could not|unavailable|not available|failed/i);
  assert.notEqual(fallback.display,'none');assert.equal(fallback.visibility,'visible');assert.ok(fallback.height>1000);
  assert.ok(fallback.text.includes(payload.t1.statuses.visible_limit));assert.deepEqual(errors,[]);
  await fail.waitForFunction(id=>document.activeElement?.id===id,{},sourceAnchors[0].slice(1));
  report.failure_modes.push({mode:failure,static_values:'PASS',disabled_controls:true,source_anchor:'PASS',page_errors:errors});
  await fail.close();
 }
 report.functional.push('Aborted request, non-200 response, malformed JSON and wrong schema retain static evidence, disabled controls and source navigation');
 assert.deepEqual(report.errors,[]);
 report.status='PASS_OPTIMIZATION_BROWSER_QA';
}catch(error){report.status='FAIL';report.failure=String(error.stack||error);process.exitCode=1;}
finally{
 fs.writeFileSync(path.join(out,'OPTIMIZATION_BROWSER_QA.json'),JSON.stringify(report,null,2)+'\n');
 await browser.close();
 console.log(JSON.stringify({status:report.status,tested_commit:report.tested_commit,views:report.views.length,
  functional:report.functional.length,axe_checks:report.accessibility.length,downloads:report.downloads.length,
  failure_modes:report.failure_modes.length,errors:report.errors,failure:report.failure},null,2));
}
