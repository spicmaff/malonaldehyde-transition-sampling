/* Published-reading regressions. No new model or reference calculations. */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
const require=createRequire(path.resolve(process.env.BROWSER_DEPS||'tools/site','package.json'));
const puppeteer=require('puppeteer-core');
const out=path.resolve(process.env.QA_OUT||'popular-qa');fs.mkdirSync(out,{recursive:true});
const base=process.env.SITE_URL||'http://127.0.0.1:8768/';
const report={status:'RUNNING',commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),views:[],checks:[],errors:[]};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
const p=await browser.newPage();p.on('pageerror',e=>report.errors.push(e.message));
async function ready(){await p.waitForFunction(()=>document.body.dataset.ready==='true'&&document.body.dataset.optimizationReady==='true');}
async function route(r){await p.evaluate(r=>{location.hash=r;},r);await p.waitForFunction(r=>document.querySelector('[data-page].active')?.id===r,{},r);}
try{
 await p.goto(base+'?still#landscape',{waitUntil:'networkidle0'});await ready();
 await p.click('nav a[data-route="forces"]');await p.waitForFunction(()=>document.querySelector('#forces.active'));
 await p.select('#force-frame','93');await p.click('[data-atom="7"]');
 assert.match(await p.$eval('#force-selection',e=>e.textContent),/O8 · Replay 93/);
 assert.equal(new URL(p.url()).hash,'#forces?frame=93&atom=7');
 const before=await p.$eval('#selected-rmse',e=>e.textContent);
 await p.reload({waitUntil:'networkidle0'});await ready();
 assert.match(await p.$eval('#force-selection',e=>e.textContent),/O8 · Replay 93/);
 assert.equal(await p.$eval('#selected-rmse',e=>e.textContent),before);
 await p.goBack({waitUntil:'networkidle0'});await p.waitForFunction(()=>document.querySelector('#landscape.active'));
 await p.goForward({waitUntil:'networkidle0'});await ready();
 assert.match(await p.$eval('#force-selection',e=>e.textContent),/O8 · Replay 93/);
 report.checks.push('Force frame and atom survive sharing/reload and browser Back/Forward; local choices replace one chapter history entry');
 for(const width of [320,390,768,1440,1920])for(const theme of ['light','dark']){
  await p.setViewport({width,height:width<768?844:1000,deviceScaleFactor:1});
  if(await p.evaluate(()=>document.documentElement.dataset.theme||'light')!==theme)await p.click('#theme');
  for(const r of ['overview','molecule','sampling','landscape','seeds','offpath','train119','forces','optimization','story','longread','reproduce']){
   await route(r);
   const view=await p.evaluate(()=>({width:innerWidth,theme:document.documentElement.dataset.theme,route:document.querySelector('[data-page].active').id,overflow:document.documentElement.scrollWidth>innerWidth+1}));
   report.views.push(view);assert.equal(view.overflow,false,`${r} ${width} ${theme}`);
   if(r==='overview'&&width<=390){
    const stage=await p.$eval('#hero-molecule',e=>{const b=e.getBoundingClientRect();return {center:b.top+b.height/2,screen:innerHeight};});
    assert.ok(stage.center<stage.screen,'the molecule is visible on the first mobile screen');
   }
   if([390,1440].includes(width)&&['overview','landscape','optimization'].includes(r))await p.screenshot({path:path.join(out,`${r}-${theme}-${width}.png`)});
  }
 }
 await route('optimization');
 await p.$eval('#opt-native-details > summary',e=>e.scrollIntoView({block:'center'}));await p.click('#opt-native-details > summary');
 await p.waitForFunction(()=>document.querySelector('#opt-native-details').open);
 await p.click('[data-opt-select="S1"]');await p.waitForFunction(()=>document.querySelector('#opt-selection').dataset.optSelected==='S1');
 await p.click('#opt-play');assert.equal(await p.$eval('#opt-play',e=>e.getAttribute('aria-pressed')),'true');
 await route('overview');assert.equal(await p.$eval('#opt-play',e=>e.getAttribute('aria-pressed')),'false');
 report.checks.push('Optional native-state reader selects S1 and stops playback when leaving the chapter');
 await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);await route('overview');
 // CDP acknowledges emulation before the MediaQueryList change task has to run.
 // Observe the completed UI response rather than racing that asynchronous event.
 await p.waitForFunction(()=>matchMedia('(prefers-reduced-motion: reduce)').matches&&document.getElementById('hero-play').disabled,{timeout:5000});
 assert.equal(await p.$eval('#hero-play',e=>e.disabled),true);
 assert.equal(await p.evaluate(()=>window.exhibit.getState().motion),null);
 await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'no-preference'}]);
 await p.waitForFunction(()=>!matchMedia('(prefers-reduced-motion: reduce)').matches&&!document.getElementById('hero-play').disabled,{timeout:5000});
 await p.click('#hero-play');await p.waitForFunction(()=>window.exhibit.getState().motion==='hero');
 await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
 await p.waitForFunction(()=>document.getElementById('hero-play').disabled&&window.exhibit.getState().motion===null,{timeout:5000});
 report.checks.push('Reduced motion settles to disabled controls, restores manual playback when cleared, and stops an already running introduction when enabled');
 const staticPage=await browser.newPage();await staticPage.setJavaScriptEnabled(false);
 await staticPage.goto(base+'#forces',{waitUntil:'networkidle0'});
 const staticView=await staticPage.$eval('#forces',e=>({text:e.innerText,label:e.querySelector('#force-molecule svg').getAttribute('aria-label'),selected:e.querySelector('#force-frame').value,score:e.querySelector('#selected-rmse').textContent}));
 assert.match(staticView.label,/Replay 145/);assert.equal(staticView.selected,'145');assert.equal(staticView.score,'0.02781');assert.match(staticView.text,/Original laboratory components/);
 await staticPage.close();report.checks.push('No-JavaScript force fallback: correct saved geometry, atom, score, selected frame and component table');
 assert.deepEqual(report.errors,[]);report.status='PASS_POPULAR_BROWSER_QA';
}catch(e){report.status='FAIL';report.failure=String(e.stack||e);process.exitCode=1;}
finally{fs.writeFileSync(path.join(out,'POPULAR_BROWSER_QA.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report,null,2));}
