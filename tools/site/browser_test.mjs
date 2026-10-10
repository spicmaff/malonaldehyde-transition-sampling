/* Real-browser checks of the deployed static artifact; no scientific execution. */
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const deps=process.env.BROWSER_DEPS;
if(!deps)throw new Error('BROWSER_DEPS must point to the locked browser-only dependencies');
const require=createRequire(path.join(path.resolve(deps),'package.json'));
const puppeteer=require('puppeteer-core'),axe=require.resolve('axe-core/axe.min.js');
const base=process.env.SITE_URL||'http://127.0.0.1:8768/';
const out=path.resolve(process.env.QA_OUT||'site-browser-qa');fs.mkdirSync(out,{recursive:true});
const routes=['overview','molecule','sampling','landscape','seeds','train119','forces','story','longread','reproduce'];
const report={status:'RUNNING',base,views:[],functional:[],accessibility:[],errors:[],videos:[],performance:null};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
const p=await browser.newPage();
p.on('pageerror',e=>report.errors.push(e.message));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const locate=route=>p.evaluate(r=>location.hash='#'+r,route);
const ready=()=>p.waitForFunction(()=>document.body.dataset.ready==='true',{timeout:30000});
async function theme(name){await p.evaluate(name=>{if((document.documentElement.dataset.theme==='dark')!==(name==='dark'))document.getElementById('theme').click();},name);}
async function input(id,value){await p.$eval('#'+id,(e,v)=>{e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));},value);}
async function select(id,value){await p.select('#'+id,String(value));}
try{
  await p.setViewport({width:1440,height:1000});await p.goto(base+'?still#overview',{waitUntil:'networkidle0',timeout:45000});await ready();
  await p.waitForFunction(()=>window.exhibit.renderers()['hero-molecule']==='webgl'||window.exhibit.renderers()['hero-molecule']==='canvas-fallback');
  for(const width of [1920,1440,768,390,320]){
    await p.setViewport({width,height:width===1920?1080:width<=390?844:1000});
    for(const mode of ['light','dark']){await theme(mode);
      for(const r of routes){await locate(r);await p.waitForFunction(r=>window.exhibit.getState().route===r,{},r);await sleep(60);
        const v=await p.evaluate(()=>({route:window.exhibit.getState().route,width:innerWidth,theme:document.documentElement.dataset.theme||'light',overflow:document.documentElement.scrollWidth>innerWidth+1,active:document.querySelectorAll('[data-page].active').length,hasRussian:/[\u0400-\u04ff]/.test(document.querySelector('[data-page].active').innerText)}));
        assert.equal(v.overflow,false,`${width}/${mode}/${r} horizontal overflow`);assert.equal(v.active,1);assert.equal(v.hasRussian,false);report.views.push(v);
        if((width===1440&&['overview','molecule','train119','forces','story'].includes(r))||(width===390&&['overview','forces','train119'].includes(r))){await p.screenshot({path:path.join(out,`${mode}_${width}_${r}.png`),fullPage:r==='overview'});}
      }
    }
  }
  await p.setViewport({width:1440,height:1000});await theme('light');await locate('molecule');await sleep(100);
  await input('path-slider',2.5);assert.match(await p.$eval('#path-state',e=>e.textContent),/Interpolated/);
  await p.click('[data-image="8"]');assert.match(await p.$eval('#path-state',e=>e.textContent),/Saved image 9/);
  const endpoint=await p.evaluate(()=>({readout:Number(document.getElementById('path-roo').textContent),reference:window.exhibit.science().molecule[8].roo}));assert.ok(Math.abs(endpoint.readout-endpoint.reference)<.000051);
  await p.click('#path-reset');assert.equal(await p.$eval('#path-slider',e=>Number(e.value)),0);
  await p.click('#path-play');await sleep(250);assert.ok(await p.$eval('#path-slider',e=>Number(e.value)>0));await p.click('#path-play');assert.equal(await p.evaluate(()=>window.exhibit.getState().motion),null);
  await p.focus('#path-slider');await p.keyboard.press('ArrowRight');report.functional.push('saved frames, interpolation labels, reset, play/pause and keyboard slider');
  await locate('sampling');await p.click('#sampling-play');await sleep(200);assert.ok((await p.$eval('#sampling-count',e=>e.textContent)).startsWith('Revealed:'));await p.click('#sampling-reset');assert.equal(await p.$eval('#sampling-count',e=>e.textContent),'36 shared + 24 added per model');report.functional.push('actual membership reveal and complete endpoint');
  await locate('landscape');await p.click('[data-model="Basin60"]');assert.equal(await p.$$eval('#energy-chart [data-series="Basin60"]',x=>x.length),0);await p.click('[data-model="Basin60"]');await input('energy-image',8);assert.match(await p.$eval('#energy-readout',e=>e.textContent),/Image 9/);report.functional.push('model visibility and saved-energy selection');
  await locate('seeds');await select('seed-select','3');assert.match(await p.$eval('#seed-description',e=>e.textContent),/seed [0-9]+/);assert.equal(await p.$$eval('#seeds-barrier [data-seed-pair]',x=>x.length),5);report.functional.push('all paired seeds retained with exact string identity');
  await locate('train119');await select('diagnostic-frame','145');assert.match(await p.$eval('#diagnostic-readout',e=>e.textContent),/Coverage crossing/);await select('diagnostic-group','CHALLENGE4');assert.match(await p.$eval('#diagnostic-readout',e=>e.textContent),/Below stop/);await select('diagnostic-frame','148');assert.match(await p.$eval('#diagnostic-readout',e=>e.textContent),/148/);await p.click('.sub-study summary');await sleep(80);assert.ok(await p.$('#train119-residual svg'));report.functional.push('separate gamma and RMSE scales, segments, endpoint classification, residual panel');
  await locate('forces?frame=145&atom=2');await p.waitForFunction(()=>window.exhibit.getState().atom===2);assert.match(await p.$eval('#force-selection',e=>e.textContent),/C3/);await p.click('[data-atom="1"]');assert.match(await p.$eval('#force-selection',e=>e.textContent),/H2/);await select('force-frame','93');await select('force-scale','4');
  const f=await p.evaluate(()=>{const s=window.exhibit.getState(),d=window.exhibit.science().forces.find(f=>f.index===s.frame);return{read:Number(document.getElementById('selected-error').textContent),expected:Math.hypot(...d.error[s.atom]),frame:s.frame,scale:s.scale};});assert.ok(Math.abs(f.read-f.expected)<.0000051);assert.equal(f.frame,93);assert.equal(f.scale,4);report.functional.push('primary-data force magnitude, atom IDs, frame selection and shared scale');
  await locate('story');for(let i=0;i<6;i++){await p.click(`[data-chapter="${i}"]`);assert.match(await p.$eval('#story-count',e=>e.textContent),new RegExp(String(i+1).padStart(2,'0')));}await input('story-slider',.42);await p.click('#story-reset');assert.equal(await p.$eval('#story-slider',e=>Number(e.value)),0);report.functional.push('six directed scientific scenes and deterministic scrubbing');
  await p.goto(base+'ru.html#forces',{waitUntil:'networkidle0'});await ready();assert.equal(await p.evaluate(()=>window.exhibit.getState().route),'forces');assert.equal(new URL(p.url()).pathname.endsWith('ru.html'),false);report.functional.push('legacy Russian URL redirects while preserving section');
  await p.reload({waitUntil:'networkidle0'});await ready();assert.equal(await p.evaluate(()=>window.exhibit.getState().route),'forces');report.functional.push('deep-link reload');
  await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);await p.goto(base+'#overview',{waitUntil:'networkidle0'});await ready();await sleep(900);assert.equal(await p.evaluate(()=>window.exhibit.getState().motion),null);await input('hero-slider',6);assert.match(await p.$eval('#hero-frame',e=>e.textContent),/07/);report.functional.push('reduced motion suppresses autoplay without disabling manual exploration');
  await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'no-preference'}]);await locate('molecule');await p.click('#path-reset');await p.click('#path-play');await sleep(1800);await p.evaluate(()=>window.exhibit.stop());
  report.performance=await p.evaluate(()=>{const s=window.exhibit.stats(),sort=x=>[...x].sort((a,b)=>a-b),q=(a,p)=>a[Math.floor((a.length-1)*p)]??null;const ints=sort(s.intervals),work=sort(s.work);return{renderer:window.exhibit.renderers(),sampled_animation_frames:s.frames,median_frame_interval_ms:q(ints,.5),p95_frame_interval_ms:q(ints,.95),median_update_work_ms:q(work,.5),p95_update_work_ms:q(work,.95),user_agent:navigator.userAgent,device_pixel_ratio:devicePixelRatio,note:'Measured in this headless browser; not a guarantee of sustained hardware-GPU performance on every device.'};});
  await p.addScriptTag({path:axe});
  for(const mode of ['light','dark']){await theme(mode);for(const r of routes){await locate(r);await sleep(40);const result=await p.evaluate(async()=>{const a=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return a.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>n.target)}));});report.accessibility.push({route:r,theme:mode,violations:result});assert.deepEqual(result,[],`Accessibility: ${r}/${mode}`);}}
  await locate('story');const videos=await p.$$eval('video',vs=>vs.map(v=>v.querySelector('source')?.src||v.src));
  if(process.env.REQUIRE_FILMS==='1')assert.equal(videos.length,2,'Two new English films required');
  for(let i=0;i<videos.length;i++){await p.evaluate(async i=>{const v=document.querySelectorAll('video')[i];v.muted=true;v.load();await v.play();},i);await sleep(400);const meta=await p.evaluate(i=>{const v=document.querySelectorAll('video')[i];const m={duration:v.duration,width:v.videoWidth,height:v.videoHeight,currentTime:v.currentTime,readyState:v.readyState,error:v.error?.message||null};v.pause();return m;},i);assert.ok(meta.currentTime>0&&meta.readyState>=2&&!meta.error);report.videos.push(meta);}
  const fallback=await browser.newPage();await fallback.goto(base+'?fallback&still#molecule',{waitUntil:'networkidle0'});await fallback.waitForFunction(()=>document.body.dataset.ready==='true');assert.equal(await fallback.evaluate(()=>window.exhibit.renderers()['path-molecule']),'canvas-fallback');await fallback.close();report.functional.push('Canvas fallback without WebGL');
  const nojs=await browser.newPage();await nojs.setJavaScriptEnabled(false);await nojs.goto(base,{waitUntil:'networkidle0'});assert.ok(await nojs.$$eval('article.prose p',x=>x.length>35));assert.equal(await nojs.$eval('html',e=>e.lang),'en');await nojs.close();report.functional.push('full essay, tables and source links available without JavaScript');
  const fail=await browser.newPage();await fail.setRequestInterception(true);fail.on('request',r=>r.url().endsWith('/data/science.json')?r.abort():r.continue());await fail.goto(base,{waitUntil:'networkidle0'});await fail.waitForFunction(()=>document.body.dataset.ready==='error');assert.equal(await fail.$eval('#load-error',e=>e.hidden),false);assert.ok(await fail.$eval('article.prose',e=>e.textContent.length>5000));await fail.close();report.functional.push('visible data-load failure with readable scientific fallback');
  assert.deepEqual(report.errors,[]);report.status='PASS_CINEMATIC_BROWSER_QA';
}catch(e){report.status='FAIL';report.failure=String(e.stack||e);process.exitCode=1;}
finally{fs.writeFileSync(path.join(out,'BROWSER_QA.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({status:report.status,views:report.views.length,functional:report.functional.length,axe_checks:report.accessibility.length,videos:report.videos.length,errors:report.errors,failure:report.failure,performance:report.performance},null,2));}
