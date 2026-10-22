/* Independent acceptance of actual HTTP builds. No scientific executables. */
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const require=createRequire(path.resolve(process.env.BROWSER_DEPS,'package.json'));
const puppeteer=require('puppeteer-core'),axe=require.resolve('axe-core/axe.min.js');
const root=process.env.SITE_URL,out=path.resolve(process.env.QA_OUT);
fs.mkdirSync(out,{recursive:true});
const report={schema:'independent-browser-review-v1',commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),tree:execFileSync('git',['rev-parse','HEAD^{tree}'],{encoding:'utf8'}).trim(),baseline:'76e0e22967f408480b5a713d8f94f6c9e9981105',pr:'3e6eeb9803078fa7a8e7b984389ce0b55d34d816',checks:[],views:[],comparisons:[],errors:[],requests:[],diagnosis:{}};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
report.browser=await browser.version();
const p=await browser.newPage();
p.on('pageerror',e=>report.errors.push(String(e)));
p.on('requestfailed',r=>report.requests.push({url:r.url(),failure:r.failure()}));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const save=()=>fs.writeFileSync(path.join(out,'INDEPENDENT_BROWSER_QA.json'),JSON.stringify(report,null,2)+'\n');
async function check(name,fn){try{const detail=await fn();report.checks.push({name,status:'PASS',detail});}catch(e){report.checks.push({name,status:'FAIL',error:String(e.stack||e)});}save();console.log(JSON.stringify(report.checks.at(-1)));}
async function open(page,edition,route='overview'){
  await page.goto(root+edition+'/?still#'+route,{waitUntil:'networkidle0'});
  await page.waitForFunction(()=>document.body.dataset.ready==='true'&&document.body.dataset.optimizationReady==='true'&&document.body.dataset.offpathReady==='true');
}
async function choose(page,width,theme,route){
  await page.bringToFront();await page.setViewport({width,height:1000,deviceScaleFactor:1});
  await page.evaluate(({theme,route})=>{window.exhibit.stop();window.optimizationExhibit.stop();if((document.documentElement.dataset.theme==='dark')!==(theme==='dark'))document.getElementById('theme').click();location.hash=route;},{theme,route});
  await page.waitForFunction(r=>document.getElementById(r)?.classList.contains('active'),{},route);
  await delay(200);await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
}
async function click(page,selector){await page.$eval(selector,e=>e.scrollIntoView({block:'center',behavior:'instant'}));await delay(100);await page.click(selector);}
async function shot(page,name){await page.screenshot({path:path.join(out,name+'.png'),fullPage:false});return name+'.png';}
async function snapshot(page){return page.evaluate(()=>({state:window.optimizationExhibit.getState(),hidden:document.hidden,focus:document.hasFocus(),route:location.hash,selected:document.getElementById('opt-selection').dataset.optSelected,rail:[...document.querySelectorAll('[data-cin-step]')].map(e=>({id:e.dataset.cinStep,pressed:e.getAttribute('aria-pressed')})),play:{disabled:document.getElementById('opt-play').disabled,label:document.getElementById('opt-play').textContent},scrollY}));}
try{
  // Reproduce the exact legacy precondition and retain diagnostic observations,
  // including whether the button hit is intercepted or playback is stopped.
  for(const edition of ['pr','current'])await check('Optimization S1 playback / '+edition,async()=>{
    await open(p,edition,'optimization');await choose(p,1440,'light','optimization');
    const order=await p.evaluate(()=>window.optimizationExhibit.data().theory.main4500.native_order);
    for(const id of order){await p.focus(`[data-cin-step="${id}"]`);await p.keyboard.press('Enter');await p.waitForFunction(id=>window.optimizationExhibit.getState().selectedState===id,{},id);}
    await p.evaluate(()=>window.optimizationExhibit.selectState('S1c'));await delay(20);
    await p.evaluate(()=>window.optimizationExhibit.reset());
    const before=await snapshot(p);await click(p,'#opt-play');
    const immediately=await snapshot(p);await delay(1550);const after=await snapshot(p);
    const screenshot=await shot(p,'playback-'+edition);
    report.diagnosis[edition]={before,immediately,after,screenshot};save();
    assert.equal(after.state.selectedState,'S1','the controller must advance from S0 to S1');
    assert.equal(after.rail.find(s=>s.id==='S1').pressed,'true','rail follows the same controller');
    await click(p,'#opt-play');assert.equal((await snapshot(p)).state.playing,false);
    return report.diagnosis[edition];
  });
  await check('120 route / width / theme layouts with accessibility',async()=>{
    await open(p,'current');await p.addScriptTag({path:axe});
    for(const width of [320,390,768,1440,1920])for(const theme of ['light','dark']){
      for(const route of ['overview','molecule','sampling','landscape','seeds','offpath','train119','forces','optimization','story','longread','reproduce']){
        await choose(p,width,theme,route);
        const view=await p.evaluate(async()=>{const a=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return {overflow:document.documentElement.scrollWidth>innerWidth+1,active:document.querySelectorAll('[data-page].active').length,violations:a.violations.map(v=>({id:v.id,impact:v.impact,targets:v.nodes.map(n=>n.target)})),incomplete:a.incomplete.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))};});
        report.views.push({width,theme,route,...view});save();
      }
      console.log(JSON.stringify({views:report.views.length,width,theme}));
    }
    assert.equal(report.views.length,120);assert.deepEqual(report.views.filter(v=>v.overflow||v.active!==1||v.violations.length),[]);
    return {views:120,incomplete:report.views.reduce((n,v)=>n+v.incomplete.length,0)};
  });
  await check('Controlled baseline / PR / repaired comparisons',async()=>{
    for(const edition of ['baseline','pr','current']){
      await open(p,edition);
      for(const width of [390,1440])for(const theme of ['light','dark'])for(const route of ['overview','sampling','optimization']){
        await choose(p,width,theme,route);
        if(route==='overview')await p.evaluate(()=>window.exhibit.seek('hero',4));
        if(route==='sampling'&&edition!=='baseline')await p.$eval('#ed-sampling-image',e=>{e.value=4;e.dispatchEvent(new Event('input',{bubbles:true}));});
        const state=await p.evaluate(()=>({theme:document.documentElement.dataset.theme||'light',scrollY,width:innerWidth,height:innerHeight,hero:window.exhibit.getState().hero,sampling:window.exhibit.getState().sampling}));
        report.comparisons.push({edition,route,width,theme,state,file:await shot(p,`${edition}-${route}-${theme}-${width}`)});save();
      }
    }
    return {screenshots:report.comparisons.length,viewport:'390 or 1440 × 1000; device scale 1; top; image 5; stopped'};
  });
  await check('Reduced motion: manual image controls and play request',async()=>{
    await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);await open(p,'current','molecule');
    await choose(p,390,'dark','molecule');await click(p,'#path-play');await delay(200);
    const state=await p.evaluate(()=>window.exhibit.getState());await p.evaluate(()=>window.exhibit.stop());
    await p.focus('#path-slider');await p.keyboard.press('End');assert.equal(await p.$eval('#path-slider',e=>Number(e.value)),8);
    await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'no-preference'}]);
    assert.equal(state.motion,null,'reduced motion uses manual saved-image selection');return state;
  });
  await check('History, deep links and independent animation stops',async()=>{
    await open(p,'current');await choose(p,390,'light','overview');
    await p.select('#ed-contents','offpath');await p.waitForFunction(()=>document.querySelector('#offpath.active'));
    await click(p,'#off-reveal');assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().playing),true);
    await p.select('#ed-contents','optimization');await p.waitForFunction(()=>document.querySelector('#optimization.active'));
    assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().playing),false);
    await p.goBack();await p.waitForFunction(()=>document.querySelector('#offpath.active'));await p.goForward();await p.waitForFunction(()=>document.querySelector('#optimization.active'));
    await p.evaluate(()=>location.hash='opt-candidate');await p.waitForFunction(()=>document.getElementById('opt-candidate').contains(document.activeElement)||document.activeElement.id==='opt-candidate');
    await p.reload({waitUntil:'networkidle0'});await p.waitForFunction(()=>document.body.dataset.optimizationReady==='true');
    assert.equal(await p.evaluate(()=>document.querySelector('[data-page].active').id),'optimization');
    return 'Back / Forward, #opt-candidate reload, prior chapter stopped';
  });
  await check('No JS, missing / corrupt / partial data and Canvas fallback',async()=>{
    const details=[];
    for(const scenario of ['nojs','missing-science','corrupt-science','partial-science','missing-opt','corrupt-opt','missing-off','fallback']){
      const q=await browser.newPage();
      try{
        if(scenario==='nojs')await q.setJavaScriptEnabled(false);
        if(scenario.includes('science')||scenario.includes('-opt')||scenario.includes('-off')){
          await q.setRequestInterception(true);
          q.on('request',r=>{const file=scenario.includes('science')?'science':scenario.includes('-opt')?'optimization':'offpath';if(!r.url().endsWith('/data/'+file+'.json'))return r.continue();if(scenario.startsWith('missing'))return r.abort();return r.respond({status:200,contentType:'application/json',body:scenario.startsWith('partial')?'{"schema":"proton-potential-cinematic-v2","molecule":[]}':'{invalid JSON'});});
        }
        await q.goto(root+'current/'+(scenario==='fallback'?'?fallback':'?still')+'#optimization',{waitUntil:'networkidle0'});
        if(scenario==='nojs')assert.ok(await q.$eval('article.prose',e=>e.textContent.length>5000));
        else if(scenario.includes('science'))await q.waitForFunction(()=>document.body.dataset.ready==='error');
        else if(scenario.includes('-opt')){await q.waitForFunction(()=>document.body.dataset.optimizationReady==='error');assert.equal(await q.$$eval('#optimization button:not(:disabled)',e=>e.length),0);}
        else if(scenario.includes('-off'))await q.waitForFunction(()=>document.body.dataset.offpathReady==='error');
        else{await q.evaluate(()=>location.hash='molecule');await q.waitForFunction(()=>window.exhibit?.renderers()['path-molecule']==='canvas-fallback');}
        details.push({scenario,status:'PASS'});
      }finally{await q.close();}
    }
    return details;
  });
  await check('No unexpected runtime or network errors in normal loads',async()=>{assert.deepEqual(report.errors,[]);assert.deepEqual(report.requests,[]);return 'normal routes only; injected failure requests use separate pages';});
}finally{
  report.status=report.checks.some(c=>c.status==='FAIL')?'FAIL':'PASS';save();await browser.close();
  console.log(JSON.stringify({status:report.status,commit:report.commit,checks:report.checks.map(({name,status})=>({name,status}))}));
  if(report.status==='FAIL')process.exitCode=1;
}
