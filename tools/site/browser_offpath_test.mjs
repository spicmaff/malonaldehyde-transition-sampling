/* Complete browser acceptance for the additional chapter, not a replacement for old QA. */
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const deps=process.env.BROWSER_DEPS;if(!deps)throw new Error('BROWSER_DEPS required');
const require=createRequire(path.join(path.resolve(deps),'package.json'));
const puppeteer=require('puppeteer-core'),axe=require.resolve('axe-core/axe.min.js');
const base=process.env.SITE_URL||'http://127.0.0.1:8768/';
const out=path.resolve(process.env.QA_OUT||'offpath-browser-qa');fs.mkdirSync(out,{recursive:true});
const report={status:'RUNNING',views:[],functional:[],accessibility:[],errors:[],new_scientific_calls:0};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
const p=await browser.newPage();p.on('pageerror',e=>report.errors.push(e.message));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function ready(){await p.waitForFunction(()=>document.body.dataset.ready==='true'&&document.body.dataset.offpathReady==='true',{timeout:30000});await p.waitForFunction(()=>document.getElementById('offpath').classList.contains('active'));await wait(300);}
async function choose(id,value){await p.select('#'+id,String(value));await wait(80);}
try{
 await p.setViewport({width:1440,height:1000});await p.goto(base+'?still#offpath',{waitUntil:'networkidle0'});await ready();
 for(const width of [1920,1440,768,390,320]){
  await p.setViewport({width,height:width<=390?844:1000});await wait(260);
  for(const mode of ['light','dark']){
   await p.evaluate(mode=>{if((document.documentElement.dataset.theme==='dark')!==(mode==='dark'))document.getElementById('theme').click();},mode);await wait(100);
   const view=await p.evaluate(()=>({width:innerWidth,theme:document.documentElement.dataset.theme||'light',overflow:document.documentElement.scrollWidth>innerWidth+1,active:document.querySelectorAll('[data-page].active').length,
      primaryMarks:document.querySelectorAll('#off-primary-chart [data-off-seed]').length,originalHeadline:document.querySelector('#overview').textContent.includes('3 of 5'),
      cyrillic:/[\u0400-\u04ff]/.test(document.querySelector('#offpath').innerText),renderer:window.offpathExhibit.getState().renderer,
      labelSize:parseFloat(getComputedStyle(document.querySelector('#off-primary-chart .off-svg-axis')).fontSize)}));
   assert.equal(view.overflow,false,`${width}/${mode} page overflow`);assert.equal(view.active,1);assert.equal(view.primaryMarks,5);assert.equal(view.cyrillic,false);assert.equal(view.originalHeadline,true);assert.ok(view.labelSize>=11);
   report.views.push(view);await p.evaluate(()=>scrollTo(0,0));await p.screenshot({path:path.join(out,`${mode}_${width}_offpath.png`),fullPage:true});
   await p.addScriptTag({path:axe});const violations=await p.evaluate(async()=>{const r=await axe.run(document.getElementById('offpath'),{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}));});
   report.accessibility.push({width,mode,violations});assert.deepEqual(violations,[],`${width}/${mode} accessibility`);
  }
 }
 await p.setViewport({width:1440,height:1000});await wait(250);
 for(const region of ['TRANSITION_CENTER','BASIN_LEFT'])for(const cap of [2000,8000])for(const seed of ['all','0','1','2','3','4']){
  await choose('off-region',region);await choose('off-cap',cap);await choose('off-seed',seed);
  const check=await p.evaluate(({region,cap,seed})=>{const rows=window.offpathExhibit.data().benchmark.block_rows;let max=0;for(const el of document.querySelectorAll('#off-direction-chart .off-block-row')){
   for(const pair of el.querySelectorAll('.off-block-pair')){const rr=rows.filter(r=>r.region===region&&r.budget===cap&&r.mode===el.dataset.mode&&r.branch===pair.dataset.branch&&(seed==='all'||r.seed_index===Number(seed)));const expected=rr.reduce((s,r)=>s+r.force_RMSE_eV_A,0)/rr.length;
    max=Math.max(max,Math.abs(Number(pair.querySelector('[data-value]').dataset.value)-expected));}}
   return {max,blocks:document.querySelectorAll('.off-block-row').length,positiveSeedStillPresent:!!document.querySelector('[data-off-seed="3"]')};},{region,cap,seed});assert.equal(check.max,0);assert.equal(check.blocks,4);assert.equal(check.positiveSeedStillPresent,true);
 }
 report.functional.push('24 region-cap-seed filter combinations agree with source rows; all primary seeds persist');
 const geometries=await p.evaluate(()=>window.offpathExhibit.data().benchmark.geometries.map(g=>g.id));
 for(const id of geometries){await choose('off-geometry',id);const d=await p.evaluate(id=>{const g=window.offpathExhibit.data().benchmark.geometries.find(g=>g.id===id);return {q:Math.abs(Number(document.getElementById('off-q').textContent)-g.q),roo:Math.abs(Number(document.getElementById('off-roo').textContent)-g.roo),id:document.getElementById('off-geometry-id').textContent};},id);assert.ok(d.q<=.0000501&&d.roo<=.0000501);assert.ok(d.id.startsWith(id));}
 report.functional.push('All fourteen exact stored geometries and qPT/O-O readouts');
 await choose('off-geometry','T01p');await choose('off-region','TRANSITION_CENTER');await choose('off-cap','8000');await choose('off-seed','all');
 await p.$eval('#off-primary-chart',e=>e.scrollIntoView({block:'center'}));await p.click('#off-reveal');await wait(350);assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().playing),true);await p.click('#off-reveal');assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().playing),false);await p.click('#off-reveal-reset');assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().progress),1);
 await p.focus('#off-progress');await p.keyboard.press('ArrowLeft');assert.ok(await p.evaluate(()=>window.offpathExhibit.getState().progress<1));await p.click('#off-reveal-reset');
 report.functional.push('Finite fixed-axis reveal, pause, show-all, keyboard scrubbing');
 await p.evaluate(()=>location.hash='#molecule');await p.waitForFunction(()=>window.exhibit.getState().route==='molecule');assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().playing),false);
 await p.evaluate(()=>location.hash='#offpath');await ready();await p.reload({waitUntil:'networkidle0'});await ready();report.functional.push('Old route and offpath deep-link reload');
 await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);await p.$eval('#off-reveal',e=>e.scrollIntoView({block:'center'}));await p.click('#off-reveal');assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().playing),false);assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().progress),1);report.functional.push('Reduced-motion keeps all final marks and manual controls');
 await p.goto(base+'?fallback&still#offpath',{waitUntil:'networkidle0'});await ready();assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().renderer),'canvas-fallback');report.functional.push('Shared Canvas renderer fallback');
 const download=await p.evaluate(async url=>{const r=await fetch(url);return {status:r.status,text:await r.text()};},base+'data/offpath/PER_GEOMETRY_280.tsv');assert.equal(download.status,200);assert.equal(download.text.trim().split('\n').length,281);report.functional.push('Actual downloadable 280-row table');
 const nojs=await browser.newPage();await nojs.setJavaScriptEnabled(false);await nojs.goto(base+'#offpath',{waitUntil:'networkidle0'});const staticView=await nojs.$eval('#offpath',e=>({text:e.innerText,svg:e.querySelectorAll('svg').length,rows:e.querySelectorAll('tbody tr').length}));assert.ok(staticView.text.includes('−0.146135'));assert.ok(staticView.svg>=4);assert.ok(staticView.rows>=280);await nojs.close();report.functional.push('No-JavaScript full static charts, tables and numerical primary');
 const fail=await browser.newPage();await fail.setRequestInterception(true);fail.on('request',r=>r.url().endsWith('/data/offpath.json')?r.abort():r.continue());await fail.goto(base+'?still#offpath',{waitUntil:'networkidle0'});await fail.waitForFunction(()=>document.body.dataset.offpathReady==='error');assert.ok((await fail.$eval('#offpath',e=>e.innerText)).includes('−0.146135'));await fail.close();report.functional.push('Offpath data-request failure preserves static evidence');
 assert.deepEqual(report.errors,[]);report.status='PASS_OFFPATH_BROWSER_QA';
}catch(e){report.status='FAIL';report.failure=e.stack;process.exitCode=1;}
finally{fs.writeFileSync(path.join(out,'OFFPATH_BROWSER_QA.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report,null,2));}
