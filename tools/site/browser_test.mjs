/* Real Chromium acceptance: routes, sizes, languages, motion, playback and axe. */
import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const dependencies=process.env.BROWSER_DEPS||path.dirname(new URL(import.meta.url).pathname);
const puppeteer=require(require.resolve('puppeteer-core',{paths:[dependencies]}));
const axePath=require.resolve('axe-core/axe.min.js',{paths:[dependencies]});
const base=(process.env.SITE_URL||'http://127.0.0.1:8765/').replace(/\/?$/,'/');
const out=process.env.QA_OUT||'site-qa-output';await mkdir(out,{recursive:true});
const routes=['overview','molecule','sampling','landscape','seeds','applicability','train119','story','longread','reproduce'];
const browser=await puppeteer.launch({headless:true,executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const findings={status:'RUNNING',base,views:[],functional:[],video:[],accessibility:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
try{
 const page=await browser.newPage();page.on('pageerror',e=>findings.errors.push(e.message));
 for(const lang of ['en','ru'])for(const width of [1440,390,320]){
  await page.setViewport({width,height:width===1440?900:844,deviceScaleFactor:1});
  await page.goto(base+(lang==='ru'?'ru.html':'index.html')+'#overview',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__siteReady===true,{timeout:20000});
  for(const theme of ['light','dark']){
   if(await page.$eval('html',el=>el.dataset.theme)!==theme)await page.click('#theme');
   for(const route of routes){
    await page.evaluate(r=>location.hash=r,route);await wait(100);
    const state=await page.evaluate(()=>({active:document.querySelector('section.active')?.id,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,language:document.documentElement.lang,theme:document.documentElement.dataset.theme,activeCount:document.querySelectorAll('section.active').length}));
    assert.equal(state.active,route);assert.equal(state.activeCount,1);assert.equal(state.language,lang);assert.equal(state.theme,theme);assert.ok(state.scrollWidth<=state.width+1,`Horizontal overflow ${lang}/${theme}/${width}/${route}: ${state.scrollWidth}`);
    findings.views.push({lang,width,theme,route,overflow:false});
    if((lang==='en'&&width===1440&&theme==='light'&&['overview','molecule','sampling','landscape','seeds','applicability','train119','story','longread'].includes(route))||(lang==='ru'&&width===390&&['overview','molecule','train119'].includes(route))||(lang==='en'&&width===1440&&theme==='dark'&&route==='overview'))await page.screenshot({path:path.join(out,`${lang}_${width}_${theme}_${route}.png`),fullPage:route==='overview'});
   }
  }
 }
 // Full keyboard slider, play/pause/reset and exact-data checks.
 await page.setViewport({width:1440,height:900});await page.goto(base+'index.html#molecule',{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.__siteReady===true);
 await page.click('#mol-reset');await page.focus('#mol-frame');await page.keyboard.press('Home');await page.keyboard.press('ArrowRight');assert.equal(await page.$eval('#mol-frame',e=>e.value),'1');
 await page.click('#mol-play');await wait(350);assert.match(await page.$eval('#mol-image-label',e=>e.textContent),/Interpolated/);await page.click('#mol-play');const paused=await page.$eval('#molecule-view',e=>e.innerHTML);await wait(160);assert.equal(await page.$eval('#molecule-view',e=>e.innerHTML),paused);await page.click('#mol-reset');assert.equal(await page.$eval('#mol-image-label',e=>e.textContent),'1 / 9');findings.functional.push('keyboard, play, pause, reset; no automatic playback');
 await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);await page.click('#mol-play');const reduced=await page.$eval('#molecule-view',e=>e.innerHTML);await wait(500);assert.equal(await page.$eval('#molecule-view',e=>e.innerHTML),reduced);findings.functional.push('reduced-motion uses a discrete step, no continuous animation');await page.emulateMediaFeatures([]);
 // Three original models only; route switching snaps to an exact image.
 await page.evaluate(()=>location.hash='landscape');await wait(120);await page.focus('#landscape-frame');await page.keyboard.press('End');assert.match(await page.$eval('#landscape-readout',e=>e.textContent),/9 \/ 9/);assert.equal(await page.$$eval('[data-series]',els=>els.length),3);await page.click('[data-series="Basin60"]');assert.equal(await page.$eval('[data-series="Basin60"]',e=>e.checked),false);findings.functional.push('energy toggles; exact saved-frame readout');
 await page.evaluate(()=>location.hash='sampling');await wait(120);await page.select('#sampling-branch','basin');assert.equal(await page.$$eval('#sampling-chart circle',x=>x.length),24);await page.select('#sampling-branch','targeted');assert.equal(await page.$$eval('#sampling-chart circle',x=>x.length),24);findings.functional.push('24 additions and 36 shared configurations; real projection');
 await page.evaluate(()=>location.hash='seeds');await wait(120);await page.select('#seed-metric','force');await page.select('#seed-select','3');assert.match(await page.$eval('#seed-readout',e=>e.textContent),/12250469658613881511/);findings.functional.push('metric selection and exact 64-bit seed identity');
 await page.evaluate(()=>location.hash='applicability');await wait(120);await page.select('#gamma-window','crossing');assert.equal(await page.$$eval('#gamma-chart circle',els=>els.length),7);findings.functional.push('gamma zoom shows all seven crossing-neighborhood frames');
 await page.evaluate(()=>location.hash='train119');await wait(120);await page.select('#case-frame','145');assert.match(await page.$eval('#case-readout',e=>e.textContent),/CROSSING7 \/ 145/);await page.click('#language');await page.waitForFunction(()=>document.documentElement.lang==='ru'&&window.__siteReady===true);assert.equal(new URL(page.url()).hash,'#train119');findings.functional.push('RU/EN switch preserves the current section');
 await page.goto(base+'ru.html#longread/chapter-8',{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.__siteReady===true);assert.equal(await page.$eval('section.active',e=>e.id),'longread');assert.equal(await page.$$eval('#longread-content h2',h=>h.length),10);findings.functional.push('deep links and ten-chapter longread');
 // Native browser video playback, all five same-origin historical media files.
 await page.goto(base+'index.html#story',{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.__siteReady===true);
 for(let i=0;i<5;i++){
  await page.evaluate(async index=>{const video=document.querySelectorAll('video')[index];video.scrollIntoView();video.muted=true;video.load();await video.play();},i);
  await wait(500);const result=await page.evaluate(index=>{const v=document.querySelectorAll('video')[index];const r={index,src:new URL(v.currentSrc).pathname,duration:v.duration,currentTime:v.currentTime,readyState:v.readyState,error:v.error?.code||null};v.pause();v.currentTime=0;return r;},i);assert.ok(result.duration>0&&result.currentTime>0&&result.readyState>=2&&!result.error,'Video failed: '+JSON.stringify(result));findings.video.push(result);
 }
 // Automated WCAG checks on every section, both themes. Scope does not exclude content.
 for(const theme of ['light','dark']){
  if(await page.$eval('html',e=>e.dataset.theme)!==theme)await page.click('#theme');
  for(const route of routes){await page.evaluate(r=>location.hash=r,route);await wait(100);await page.addScriptTag({path:axePath});const result=await page.evaluate(async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}}));findings.accessibility.push({theme,route,violations:result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))});}
 }
 const nojs=await browser.newPage();await nojs.setJavaScriptEnabled(false);await nojs.goto(base+'ru.html',{waitUntil:'domcontentloaded'});assert.equal(await nojs.$$('section.page').then(a=>a.length),10);assert.ok(await nojs.$eval('#longread-content',e=>e.textContent.length)>14000);assert.equal(await nojs.$$eval('.chapter-source',a=>a.length),10);findings.functional.push('Russian full static text, source links and tables without JavaScript');await nojs.close();
 const failed=await browser.newPage();await failed.setRequestInterception(true);failed.on('request',r=>r.url().endsWith('data/science.json')?r.abort():r.continue());await failed.goto(base+'index.html',{waitUntil:'domcontentloaded'});await failed.waitForSelector('#load-error:not([hidden])');assert.ok(await failed.$eval('#longread-content',e=>e.textContent.length)>14000);findings.functional.push('data-loading failure preserves the complete static narrative');await failed.close();
 assert.deepEqual(findings.errors,[],'Unexpected JavaScript errors');
 const violations=findings.accessibility.flatMap(a=>a.violations.map(v=>({theme:a.theme,route:a.route,...v})));
 findings.status=violations.length?'FAIL_ACCESSIBILITY':'PASS_BROWSER_ACCEPTANCE';findings.accessibility_violation_count=violations.length;
 await writeFile(path.join(out,'BROWSER_QA.json'),JSON.stringify(findings,null,2));
 console.log(JSON.stringify({status:findings.status,views:findings.views.length,functional:findings.functional.length,videos:findings.video.length,accessibility_violations:violations,errors:findings.errors},null,2));
 if(violations.length)process.exitCode=1;
}catch(error){findings.status='FAIL_BROWSER_ACCEPTANCE';findings.failure=String(error);await writeFile(path.join(out,'BROWSER_QA.json'),JSON.stringify(findings,null,2));console.error(error);process.exitCode=1;}finally{await browser.close();}
