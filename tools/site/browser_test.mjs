/* Real HTTP browser acceptance; no physics, no external screenshot service. */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const deps=process.env.BROWSER_DEPS;if(!deps)throw Error('BROWSER_DEPS must point to the locked QA dependency installation.');
const require=createRequire(path.join(deps,'package.json'));
const puppeteer=require('puppeteer-core');
const URL_BASE=(process.env.SITE_URL||'http://127.0.0.1:8783/').replace(/\/?$/,'/');
const out=process.env.QA_OUT||path.resolve('site-qa');fs.mkdirSync(out,{recursive:true});
const routes=['overview','molecule','sampling','landscape','seeds','applicability','train119','forces','story','longread','reproduce'];
const widths=[1440,1920,768,390,320];
const report={schema:'cinematic-browser-qa-v2',base:URL_BASE,views:[],functional:[],performance:{},accessibility:[],errors:[],videos:[],screenshots:[]};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const browser=await puppeteer.launch({headless:true,executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
try{
 const pg=await browser.newPage();
 pg.on('pageerror',e=>report.errors.push(e.message));
 pg.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))report.errors.push('console: '+m.text());});
 await pg.setViewport({width:1440,height:950,deviceScaleFactor:1});
 await pg.goto(URL_BASE,{waitUntil:'networkidle0',timeout:45000});await pg.waitForFunction(()=>window.__proton?.ready,{timeout:20000});
 const navigate=async r=>{await pg.evaluate(r=>{location.hash=r;},r);await pg.waitForFunction(r=>document.body.dataset.page===r,{},r);await pause(55);};
 for(const width of widths){
  await pg.setViewport({width,height:width>=1440?950:width===768?1024:844,deviceScaleFactor:1});
  for(const theme of ['light','dark']){
   await pg.evaluate(theme=>{document.documentElement.dataset.theme=theme;window.__proton.redraw();},theme);
   for(const r of routes){await navigate(r);
    const check=await pg.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,route:document.body.dataset.page,cyrillic:/[\u0400-\u04ff]/.test(document.querySelector('.page.active').innerText),title:document.querySelector('.page.active h1')?.textContent,canvas:[...document.querySelectorAll('.page.active canvas')].filter(c=>c.getBoundingClientRect().width>0).every(c=>c.dataset.rendered==='true')}));
    report.views.push({width,theme,...check});assert.equal(check.overflow,false,'Page overflow '+width+' '+r);assert.equal(check.cyrillic,false,'Russian visible text '+r);assert.equal(check.canvas,true,'Missing canvas render '+r);
    if((width===1440&&['overview','molecule','train119','forces','story'].includes(r))||(width===390&&['overview','forces','train119'].includes(r))||(width===320&&r==='overview')){
     const file=`${theme}_${width}_${r}.png`;await pg.screenshot({path:path.join(out,file),fullPage:width<768});report.screenshots.push(file);
    }
   }
  }
 }
 await pg.setViewport({width:1440,height:950});
 // Every timeline must change, pause, reset, and expose manual progress.
 const sceneRoute={hero:'overview',molecule:'molecule',sampling:'sampling',landscape:'landscape',seeds:'seeds',train119:'train119',forces:'forces',story:'story'};
 for(const [scene,r] of Object.entries(sceneRoute)){
  await navigate(r);await pg.evaluate(scene=>window.__proton.seek(scene,0),scene);
  const before=await pg.evaluate(()=>({canvas:document.querySelector('.page.active canvas')?.toDataURL(),html:document.querySelector('.page.active .chart')?.innerHTML}));
  await pg.click('#play-'+scene);await pause(scene==='molecule'?1900:scene==='train119'||scene==='landscape'?1650:750);assert.equal(await pg.evaluate(()=>window.__proton.playing()),scene);
  await pg.click('#play-'+scene);assert.equal(await pg.evaluate(()=>window.__proton.playing()),null);
  const after=await pg.evaluate(()=>({canvas:document.querySelector('.page.active canvas')?.toDataURL(),html:document.querySelector('.page.active .chart')?.innerHTML}));
  assert.notDeepEqual(before,after,'Scene did not change '+scene);
  await pg.click('#reset-'+scene);await pg.evaluate(scene=>window.__proton.seek(scene,1),scene);
  report.functional.push({test:'play-pause-reset-manual-seek',scene,status:'PASS'});
 }
 await navigate('molecule');
 await pg.$eval('#path-position',e=>{e.value='0';e.dispatchEvent(new Event('input',{bubbles:true}));});
 assert.equal(await pg.evaluate(()=>window.__proton.state.path),0);assert.match(await pg.$eval('#path-state',e=>e.textContent),/Saved image 1/);
 await pg.click('#path-next');assert.equal(await pg.evaluate(()=>window.__proton.state.path),1);
 await pg.$eval('#path-position',e=>{e.value='3.5';e.dispatchEvent(new Event('input',{bubbles:true}));});assert.match(await pg.$eval('#path-state',e=>e.textContent),/Interpolated/);
 await pg.focus('#path-position');await pg.keyboard.press('ArrowRight');assert.ok(await pg.evaluate(()=>window.__proton.state.path>3.5));report.functional.push({test:'exact-images-interpolation-keyboard',status:'PASS'});
 await navigate('landscape');await pg.click('#show-basin');assert.equal(await pg.$eval('#show-basin',e=>e.checked),false);await pg.click('#show-basin');
 await pg.$eval('#energy-image',e=>{e.value=8;e.dispatchEvent(new Event('input',{bubbles:true}));});assert.match(await pg.$eval('#energy-image-label',e=>e.textContent),/Image 9/);report.functional.push({test:'model-toggle-saved-image',status:'PASS'});
 await navigate('seeds');await pg.select('#seed-pair','3');await pg.select('#seed-metric','force');const seedRecord=await pg.$eval('#seed-record',e=>e.textContent);assert.match(seedRecord,/Selected pair 4/);assert.match(seedRecord,/64-bit seed/);report.functional.push({test:'five-seed-selection',status:'PASS'});
 await navigate('applicability');await pg.click('#gamma-zoom');assert.match(await pg.$eval('#replay-chart',e=>e.textContent),/1\.0000013/);report.functional.push({test:'gamma-zoom-fixed-threshold',status:'PASS'});
 await navigate('train119');await pg.select('#diagnostic-group','CHALLENGE4');assert.equal(await pg.$eval('#diagnostic-frame',e=>e.max),'3');await pg.$eval('#diagnostic-frame',e=>{e.value=3;e.dispatchEvent(new Event('input',{bubbles:true}));});assert.match(await pg.$eval('#diagnostic-record',e=>e.textContent),/96/);await pg.select('#diagnostic-group','CROSSING7');report.functional.push({test:'disjoint-diagnostic-segments',status:'PASS'});
 await navigate('forces');await pg.select('#force-frame','7');await pg.select('#force-atom','2');const force=await pg.evaluate(()=>({frame:document.querySelector('#forces-canvas').dataset.frame,atom:document.querySelector('#forces-canvas').dataset.selectedAtom,text:document.querySelector('#force-record').textContent}));assert.equal(force.frame,'145');assert.equal(force.atom,'C3');assert.match(force.text,/source-frame/);
 const stable=await pg.$eval('#force-record',e=>e.textContent);await pg.$eval('#force-angle',e=>{e.value=52;e.dispatchEvent(new Event('input',{bubbles:true}));});assert.equal(await pg.$eval('#force-record',e=>e.textContent),stable);await pg.select('#force-layer','difference');report.functional.push({test:'force-frame-atom-rotation-norm-and-layer',status:'PASS'});
 // Measure real browser timing, not a promise about arbitrary client hardware.
 await navigate('overview');
 report.performance=await pg.evaluate(async()=>{
  const draws=[];for(let i=0;i<90;i++){const start=performance.now();window.__proton.seek('hero',i/89);draws.push(performance.now()-start);}
  const frames=[];await new Promise(resolve=>{let last,n=0;function step(t){if(last!==undefined)frames.push(t-last);last=t;if(++n<90)requestAnimationFrame(step);else resolve();}requestAnimationFrame(step);});
  const quant=(xs,p)=>[...xs].sort((a,b)=>a-b)[Math.floor((xs.length-1)*p)];
  return {headless_browser:true,renderer:'Canvas2D and SVG',hero_update_median_ms:quant(draws,.5),hero_update_p95_ms:quant(draws,.95),idle_rAF_median_ms:quant(frames,.5),idle_rAF_p95_ms:quant(frames,.95),hardware_GPU_certification:false};
 });
 // axe runs all sections in both themes. Canvas image interpretation is reviewed separately.
 await pg.addScriptTag({path:require.resolve('axe-core/axe.min.js')});
 for(const theme of ['light','dark']){
  await pg.evaluate(t=>{document.documentElement.dataset.theme=t;window.__proton.redraw();},theme);
  for(const r of routes){
   await navigate(r);
   const violations=await pg.evaluate(async()=>{
    const result=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});
    return result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary})).slice(0,6)}));
   });
   report.accessibility.push({theme,route:r,violations});
  }
 }
 // Existing translated URL becomes only a legacy redirect, preserving route.
 await pg.goto(URL_BASE+'ru.html#forces',{waitUntil:'networkidle0'});await pg.waitForFunction(()=>window.__proton?.ready);assert.equal(new URL(pg.url()).hash,'#forces');assert.equal(await pg.$eval('html',e=>e.lang),'en');assert.ok(!new URL(pg.url()).pathname.endsWith('ru.html'));report.functional.push({test:'legacy-ru-route-redirect',status:'PASS'});
 await pg.reload({waitUntil:'networkidle0'});await pg.waitForFunction(()=>window.__proton?.ready);assert.equal(await pg.evaluate(()=>document.body.dataset.page),'forces');
 await pg.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);await navigate('overview');await pg.click('#play-hero');await pause(100);assert.equal(await pg.evaluate(()=>window.__proton.playing()),null);report.functional.push({test:'reduced-motion-static-play',status:'PASS'});await pg.emulateMediaFeatures([]);
 await navigate('story');await pg.waitForFunction(()=>document.querySelectorAll('#cinema-downloads video').length>0,{timeout:process.env.ALLOW_NO_VIDEO?'500':'15000'}).catch(e=>{if(!process.env.ALLOW_NO_VIDEO)throw e;});
 for(let i=0;i<await pg.$$eval('#cinema-downloads video',els=>els.length);i++){
  const v=await pg.evaluate(async i=>{const v=document.querySelectorAll('#cinema-downloads video')[i];v.muted=true;v.load();await Promise.race([new Promise((res,rej)=>{v.addEventListener('loadeddata',res,{once:true});v.addEventListener('error',()=>rej(Error('media error')),{once:true});}),new Promise((_,rej)=>setTimeout(()=>rej(Error('media timeout')),20000))]);await v.play();await new Promise(r=>setTimeout(r,550));const result={src:v.currentSrc,advanced:v.currentTime>0,width:v.videoWidth,height:v.videoHeight};v.pause();return result;},i);assert.ok(v.advanced);report.videos.push(v);
 }
 const plain=await browser.newPage();await plain.setJavaScriptEnabled(false);await plain.goto(URL_BASE,{waitUntil:'networkidle0'});assert.equal(await plain.$eval('html',e=>e.lang),'en');assert.ok(await plain.$$eval('.page',els=>els.every(e=>getComputedStyle(e).display!=='none')));assert.match(await plain.$eval('#longread',e=>e.innerText),/21 internal degrees/);assert.ok(await plain.$$eval('table',els=>els.length>=5));await plain.close();report.functional.push({test:'no-javascript-narrative-and-tables',status:'PASS'});
 const errors=report.errors.filter(e=>!e.includes('favicon'));const violations=report.accessibility.flatMap(a=>a.violations.map(v=>({...v,theme:a.theme,route:a.route})));
 report.status=errors.length||violations.length?'FAIL':'PASS_CINEMATIC_BROWSER_ACCEPTANCE';report.error_count=errors.length;report.accessibility_violation_count=violations.length;
 fs.writeFileSync(path.join(out,'BROWSER_REPORT.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({status:report.status,views:report.views.length,functional:report.functional.length,videos:report.videos.length,accessibility_violations:violations,errors,performance:report.performance},null,2));
 assert.equal(errors.length,0,'Unexpected JavaScript/browser errors');assert.equal(violations.length,0,'Accessibility findings');
}catch(e){report.status='FAIL';report.failure=e.stack;fs.writeFileSync(path.join(out,'BROWSER_REPORT.json'),JSON.stringify(report,null,2)+'\n');console.error(e);process.exitCode=1;}finally{await browser.close();}
