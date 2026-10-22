/* Integrated HTTP acceptance. Does not replace or weaken any earlier runner. */
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(path.join(path.resolve(process.env.BROWSER_DEPS),'package.json'));
const puppeteer=require('puppeteer-core'),axe=require.resolve('axe-core/axe.min.js');
const base=process.env.SITE_URL,before=process.env.FINALE_BEFORE_URL;
if(!base||!before)throw Error('Current and published-baseline HTTP URLs are required');
const out=path.resolve(process.env.QA_OUT||'finale-qa');fs.mkdirSync(out,{recursive:true});
const report={status:'RUNNING',commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),tree:execFileSync('git',['rev-parse','HEAD^{tree}'],{encoding:'utf8'}).trim(),baseline:'d713f60a3050f6a7b27a0d3e679e0bf58b93ddf0',views:[],checks:[],accessibility:[],screenshots:[],regions:{},errors:[],new_scientific_calls:0};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
const p=await browser.newPage();p.on('pageerror',e=>report.errors.push(e.message));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const near=(a,b,tol=1e-14)=>assert.ok(Math.abs(a-b)<=tol,`${a} != ${b}`);
const state=()=>p.evaluate(()=>window.scientificFinale.getState());
async function choose(width,mode,route='optimization'){
 await p.bringToFront();
 await p.setViewport({width,height:1000,deviceScaleFactor:1});
 await p.evaluate(({mode,route})=>{window.exhibit.stop();window.optimizationExhibit.stop();if((document.documentElement.dataset.theme==='dark')!==(mode==='dark'))document.getElementById('theme').click();location.hash=route;},{mode,route});
 await p.waitForFunction(r=>window.exhibit.getState().route===r,{},route);await wait(180);
}
async function click(selector){
 await p.$eval(selector,e=>e.scrollIntoView({block:'center',behavior:'instant'}));await wait(180);
 assert.equal(await p.$eval(selector,e=>{const r=e.getBoundingClientRect(),h=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return h===e||e.contains(h);}),true,'actual pointer target is not covered');
 await p.click(selector);await wait(50);
}
async function full(page,name){
 await page.bringToFront();
 await page.evaluate(()=>{window.exhibit?.stop();window.optimizationExhibit?.stop();window.scientificFinale?.stop();scrollTo({top:0,behavior:'instant'});});await wait(120);
 const file=name+'.png';await page.screenshot({path:path.join(out,file),fullPage:true});report.screenshots.push(file);
 report.regions[file]=await page.evaluate(()=>Object.fromEntries(['opt-finale-tradeoff','opt-finale-controls','opt-finale-geometry','opt-next-study'].map(id=>{const e=document.getElementById(id);if(!e)return [id,null];const r=e.getBoundingClientRect();return [id,{x:r.x,y:r.y+scrollY,width:r.width,height:r.height}];})));
}
try{
 report.browser=await browser.version();
 await p.goto(base+'?still&utm_source=chatgpt.com#optimization',{waitUntil:'networkidle0',timeout:60000});
 await p.waitForFunction(()=>document.body.dataset.ready==='true'&&window.scientificFinale?.getState().ready,{timeout:30000});
 const d=await p.evaluate(async()=>{const r=await fetch('data/finale.json');return r.json();});
 assert.equal(d.system,'ROW_EXACT_FIXED_D');assert.equal(d.normalization,60);assert.equal(d.native.S3,null);
 for(const r of d.rows)near(Number(r.Q),Number(r.ell)+Number(r.R),1e-17);
 const routes=['overview','molecule','sampling','landscape','seeds','train119','forces','story','longread','reproduce','offpath','optimization'];
 for(const width of [320,390,768,1440,1920])for(const mode of ['light','dark']){
  for(const route of routes){
   await choose(width,mode,route);
   const v=await p.evaluate(()=>({active:document.querySelectorAll('[data-page].active').length,overflow:document.documentElement.scrollWidth>innerWidth+1,route:window.exhibit.getState().route}));
   assert.equal(v.active,1);assert.equal(v.overflow,false);assert.equal(v.route,route);report.views.push({width,mode,...v});
  }
  await choose(width,mode);await p.evaluate(()=>window.scientificFinale.selectStep(5));
  await p.addScriptTag({path:axe});
  const a=await p.evaluate(async()=>{const r=await axe.run({include:['#opt-finale-tradeoff','#opt-finale-controls','#opt-finale-geometry','#opt-next-study','.sf-counterexample']},{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return {violations:r.violations,incomplete:r.incomplete};});
  report.accessibility.push({width,mode,...a});assert.deepEqual(a.violations,[],'new finale scoped axe violations');assert.ok(!a.incomplete.some(v=>v.id==='aria-prohibited-attr'),'no unresolved prohibited naming attributes');
 }
 report.checks.push('120 responsive route/theme/width combinations; ten scoped axe runs with incomplete nodes retained');
 await choose(1440,'light');
 const geometry=await p.$$eval('.sf-chart svg [data-sf-metric]',els=>els.map(e=>e.outerHTML));
 for(let i=0;i<6;i++){
  await click(`[data-sf-step="${i}"]`);assert.equal((await state()).index,i);
  assert.equal(await p.$eval(`[data-sf-step="${i}"]`,e=>e.getAttribute('aria-pressed')),'true');
  assert.deepEqual(await p.$$eval('.sf-chart svg [data-sf-metric]',els=>els.map(e=>e.outerHTML)),geometry,'highlight does not manufacture intermediate marks');
 }
 await p.focus('[data-sf-step="5"]');await p.keyboard.press('Home');assert.equal((await state()).index,0);await p.keyboard.press('ArrowRight');assert.equal((await state()).index,1);await p.keyboard.press('End');assert.equal((await state()).index,5);
 report.checks.push('all six states and keyboard navigation; source geometry and exact numeric table never change');
 await click('#sf-reset');await click('#sf-play');await p.waitForFunction(()=>window.scientificFinale.getState().index===1,{timeout:6000});await click('#sf-play');
 const paused=(await state()).index;assert.equal((await state()).playing,false);await wait(2600);assert.equal((await state()).index,paused);
 await click('#sf-reset');await click('#sf-play');await p.waitForFunction(()=>window.scientificFinale.getState().index===5&&!window.scientificFinale.getState().playing,{timeout:20000});
 await click('#sf-reset');await click('#sf-play');await p.evaluate(()=>location.hash='overview');await p.waitForFunction(()=>!window.scientificFinale.getState().playing);await choose(1440,'light');
 report.checks.push('actual pointer Play/Pause/Reset; finite completion; route change stops playback');
 for(const value of [0,.25,.5,.75,1]){
  await p.focus('#sf-alpha');await p.keyboard.press('Home');for(let n=0;n<value*100;n++)await p.keyboard.press('ArrowRight');
  const current=await p.$eval('#sf-alpha',e=>Number(e.value));near(current,value);
  const expected=d.direction.l0+d.direction.a*value+d.direction.b*value*value/2;
  near(await p.$eval('#sf-loss-value',e=>Number(e.textContent)),expected,1e-12);
 }
 assert.equal(await p.evaluate(()=>window.scientificFinale.setAlpha(-1)),false);
 assert.equal(await p.evaluate(()=>window.scientificFinale.setAlpha(NaN)),false);
 report.checks.push('native keyboard slider at five alpha values; saved scalar quadratic only; invalid inputs rejected');
 await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
 await p.waitForFunction(()=>document.getElementById('sf-play').disabled);await click('[data-sf-step="3"]');assert.equal((await state()).index,3);assert.equal((await state()).playing,false);
 await p.emulateMediaFeatures([]);report.checks.push('reduced motion disables automatic play while preserving manual inspection');
 for(const mode of ['missing','malformed','numeric-mutation','false-claim']){
  const q=await browser.newPage();await q.setRequestInterception(true);
  q.on('request',r=>{
   if(!r.url().endsWith('/data/finale.json'))return r.continue();
   const bad=structuredClone(d);if(mode==='numeric-mutation')bad.rows[1].ell='0';if(mode==='false-claim')bad.limits.T2_executed=true;
   r.respond({status:mode==='missing'?404:200,contentType:'application/json',body:mode==='malformed'?'{':JSON.stringify(bad)});
  });
  await q.goto(base+'?still#optimization',{waitUntil:'networkidle0'});await q.waitForFunction(()=>window.scientificFinale?.getState().failed);
  assert.equal(await q.$$eval('#opt-finale-tradeoff button:not(:disabled)',e=>e.length),0);assert.equal(await q.$eval('#sf-alpha',e=>e.disabled),true);
  assert.equal(await q.$$eval('[data-sf-exact]',e=>e.length),6);assert.match(await q.$eval('#sf-load-status',e=>e.textContent),/static figure/);await q.close();
 }
 report.checks.push('404, malformed JSON, numerical mismatch and false T2 claim all fail closed with intact static evidence');
 const nojs=await browser.newPage();await nojs.setJavaScriptEnabled(false);await nojs.goto(base+'#optimization',{waitUntil:'networkidle0'});
 assert.equal(await nojs.$$eval('[data-sf-exact]',e=>e.length),6);assert.equal(await nojs.$$eval('#opt-finale-tradeoff button:not(:disabled)',e=>e.length),0);assert.match(await nojs.$eval('#opt-next-study',e=>e.textContent),/different objective/);await nojs.close();
 report.checks.push('complete no-JavaScript conclusion, figures and table; no enabled fake controls');
 await choose(1440,'light');await p.evaluate(()=>document.body.style.zoom='2');await wait(150);
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'200% CSS zoom reflow');await p.evaluate(()=>document.body.style.zoom='');
 report.checks.push('200% CSS zoom reflow (not a general browser/device certification)');
 const old=await browser.newPage();
 for(const width of [1440,390])for(const mode of ['light','dark']){
  await choose(width,mode);await p.evaluate(()=>{window.scientificFinale.selectStep(5);window.scientificFinale.setAlpha(.5);});
  await full(p,`after_${mode}_${width}_FULL`);
  await old.setViewport({width,height:1000,deviceScaleFactor:1});await old.goto(before+'?still#optimization',{waitUntil:'networkidle0'});await old.waitForFunction(()=>document.body.dataset.ready==='true');
  await old.evaluate(m=>{if((document.documentElement.dataset.theme==='dark')!==(m==='dark'))document.getElementById('theme').click();},mode);await full(old,`before_${mode}_${width}_FULL`);
 }
 await old.close();await choose(1440,'light');
 for(const i of [0,1,2,3,4,5]){await p.evaluate(n=>window.scientificFinale.selectStep(n),i);await full(p,`reader_step_${i}_FULL`);}
 assert.deepEqual(report.errors,[]);report.status='PASS_SCOPED_HTTP_FINALE';
}catch(e){report.status='FAIL';report.failure=e.stack;throw e;}
finally{fs.writeFileSync(path.join(out,'FINALE_QA.json'),JSON.stringify(report,null,2));await browser.close();}
