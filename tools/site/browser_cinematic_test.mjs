/* Source-driven scene acceptance; complements all existing HTTP-browser suites. */
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(path.join(path.resolve(process.env.BROWSER_DEPS),'package.json'));
const puppeteer=require('puppeteer-core'),axe=require.resolve('axe-core/axe.min.js');
const url=process.env.SITE_URL,before=process.env.CIN_BEFORE_URL;
if(!url||!before)throw new Error('Current and pinned previous HTTP builds are required');
const out=path.resolve(process.env.QA_OUT||'cinematic-scenes-qa');fs.mkdirSync(out,{recursive:true});
const report={status:'RUNNING',commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),tree:execFileSync('git',['rev-parse','HEAD^{tree}'],{encoding:'utf8'}).trim(),before_ref:'9cb1e603df1ad2df481988a31480122010931a5c',views:[],navigation_views:[],checks:[],screenshots:[],errors:[]};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});report.browser=await browser.version();
// SVG appends omitted paint operations in their normal order. Chrome may
// serialize `stroke fill` as `stroke`; compare semantics, not CSSOM spelling.
function expandedPaintOrder(value) {
 const normal=['fill','stroke','markers'];
 const specified=value==='normal'?[]:value.trim().split(/\s+/);
 assert.ok(specified.every(v=>normal.includes(v))&&new Set(specified).size===specified.length,'valid paint order');
 return [...specified,...normal.filter(v=>!specified.includes(v))];
}
assert.deepEqual(expandedPaintOrder('stroke'),['stroke','fill','markers']);
assert.deepEqual(expandedPaintOrder('stroke fill'),['stroke','fill','markers']);
assert.deepEqual(expandedPaintOrder('normal'),['fill','stroke','markers']);
assert.notDeepEqual(expandedPaintOrder('fill stroke'),['stroke','fill','markers']);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const p=await browser.newPage(),old=await browser.newPage();
p.on('pageerror',e=>report.errors.push(e.message));old.on('pageerror',e=>report.errors.push(e.message));
async function open(page,base){await page.goto(base+'?still#optimization',{waitUntil:'networkidle0'});await page.waitForFunction(()=>document.body.dataset.optimizationReady==='true');}
async function choose(page,width,mode,route='optimization'){
 await page.bringToFront();
 await page.setViewport({width,height:width<768?844:1000,deviceScaleFactor:1});
 await page.evaluate(({mode,route})=>{window.exhibit.stop();window.optimizationExhibit.stop();if((document.documentElement.dataset.theme==='dark')!==(mode==='dark'))document.getElementById('theme').click();location.hash=route;},{mode,route});
 await page.waitForFunction(r=>document.getElementById(r).classList.contains('active'),{},route);await wait(220);await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
}
async function shot(page,name,fullPage=false){await page.bringToFront();await page.screenshot({path:path.join(out,name+'.png'),fullPage});report.screenshots.push(name+'.png');}
async function click(selector){await p.$eval(selector,e=>e.scrollIntoView({block:'center',behavior:'instant'}));await wait(100);await p.click(selector);}
try{
 await open(p,url);await open(old,before);await p.addScriptTag({path:axe});
 const payload=await p.evaluate(()=>window.optimizationExhibit.data());
 for(const width of [320,390,768,1440,1920])for(const mode of ['light','dark']){
  await choose(p,width,mode);
  const result=await p.evaluate(async()=>{
   const cells=[...document.querySelectorAll('[data-cin-cell]')],sizes=cells.map(e=>e.getBoundingClientRect().width);
   const a=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});
   return {count:cells.length,counts:Object.fromEntries(['radial','invariant','offset'].map(k=>[k,cells.filter(e=>e.dataset.cinCell===k).length])),widthSpread:Math.max(...sizes)-Math.min(...sizes),overflow:document.documentElement.scrollWidth>innerWidth+1,violations:a.violations,incomplete:a.incomplete,snapshots:[...document.querySelectorAll('[data-cin-snapshot]')].map(e=>{const mark=e.getBoundingClientRect(),track=e.parentElement.getBoundingClientRect(),style=getComputedStyle(e.parentElement),borderLeft=parseFloat(style.borderLeftWidth),borderRight=parseFloat(style.borderRightWidth);return {id:e.dataset.cinSnapshot,value:Number(e.dataset.cinJ),sourceLeft:Number(e.getAttribute('style').match(/left:([\d.]+)%/)[1]),cssomLeft:parseFloat(e.style.left),renderedCenter:mark.x+mark.width/2,trackStart:track.x+borderLeft,trackWidth:track.width-borderLeft-borderRight};})};
  });
  report.views.push({width,mode,...result});assert.equal(result.count,248);assert.deepEqual(result.counts,{radial:216,invariant:29,offset:3});assert.ok(result.widthSpread<.15,'one equal-size square per coefficient');assert.equal(result.overflow,false);assert.deepEqual(result.violations,[]);
  for(const point of result.snapshots){assert.equal(point.value,payload.theory.main4500.states.find(s=>s.id===point.id).native_J);const expected=(Math.log10(point.value)+5)*50;assert.ok(Math.abs(point.sourceLeft-expected)<1e-9,'exact source percentage');assert.ok(Math.abs(point.renderedCenter-(point.trackStart+point.trackWidth*expected/100))<.75,'rendered marker within subpixel tolerance');}
  if([390,1440].includes(width)){
   await shot(p,`after_${mode}_${width}_optimization`,true);await choose(old,width,mode);await shot(old,`before_${mode}_${width}_optimization`,true);
   for(const id of ['opt-coefficient-atlas','opt-episode','opt-candidate']){
    await p.$eval('#'+id,e=>e.scrollIntoView({block:'start',behavior:'instant'}));await shot(p,`${id}_${mode}_${width}`);
   }
   await choose(p,width,mode,'overview');await choose(old,width,mode,'overview');await shot(p,`after_${mode}_${width}_overview`,true);await shot(old,`before_${mode}_${width}_overview`,true);
  }
  fs.writeFileSync(path.join(out,'CINEMATIC_PROGRESS.json'),JSON.stringify(report,null,2));
 }
 for(const width of [320,390,768,1440,1920])for(const mode of ['light','dark'])for(const route of ['overview','molecule','sampling','landscape','seeds','train119','forces','story','longread','reproduce','offpath','optimization']){
  await choose(p,width,mode,route);
  // Fragment navigation has native focus semantics. Test our reveal helper in
  // isolation AFTER that navigation, not against an unrelated prior focus.
  const focusAfterRoute=await p.evaluate(()=>({tag:document.activeElement.tagName,id:document.activeElement.id}));
  await p.focus('.site-header .brand');
  assert.equal(await p.evaluate(()=>document.activeElement===document.querySelector('.site-header .brand')),true,'focus precondition');
  await p.evaluate(()=>{const n=document.querySelector('.nav-shell nav');n.scrollLeft=n.scrollLeft>0?0:n.scrollWidth;window.dispatchEvent(new Event('resize'));});
  await wait(220);
  const nav=await p.evaluate(()=>{const select=document.getElementById('ed-contents');const compact=select?.getClientRects().length>0;const n=compact?select:document.querySelector('.nav-shell nav'),a=compact?select:n.querySelector('[aria-current="page"]'),nr=n.getBoundingClientRect(),ar=a.getBoundingClientRect();return {kind:compact?'select':'links',visible:nr.width>0&&nr.height>0,route:compact?select.value:a.dataset.route,left:ar.left,right:ar.right,containerLeft:nr.left,containerRight:nr.right,scrollY:window.scrollY,headerFocusRetained:document.activeElement===document.querySelector('.site-header .brand')};});
  report.navigation_views.push({width,mode,requested:route,focusAfterRoute,...nav});assert.equal(nav.route,route);assert.equal(nav.visible,true,'current chapter control visible');assert.ok(nav.left>=nav.containerLeft-1&&nav.right<=nav.containerRight+1,'current route visible in horizontal menu');assert.equal(nav.scrollY,0);assert.equal(nav.headerFocusRetained,true);
 }
 report.checks.push('120 active-route navigation combinations visible without vertical scroll or focus theft');
 // Walk the actual Tab order as well as testing the active-route observer.
 for(const width of [320,390,768,1440,1920])for(const mode of ['light','dark']){
  await choose(p,width,mode);await p.focus('.site-header .brand');const seen=new Set();
  const compact=await p.$eval('#ed-contents',e=>e.getClientRects().length>0);
  if(compact){
   // The compact design replaces the horizontal links with a native select.
   // Exercise all twelve choices with real keys, keeping the control focused.
   await p.focus('#ed-contents');await p.keyboard.press('Home');
   for(let i=0;i<12;i++){
    if(i)await p.keyboard.press('ArrowDown');
    await p.waitForFunction(i=>document.querySelector('[data-page].active')?.id===document.getElementById('ed-contents').options[i].value,{},i);
    const focused=await p.$eval('#ed-contents',e=>({route:e.value,focused:document.activeElement===e,focusVisible:e.matches(':focus-visible'),outline:getComputedStyle(e).outlineStyle,scrollY}));
    assert.ok(focused.focused&&focused.focusVisible&&focused.outline!=='none','native chapter selector keeps visible keyboard focus');assert.equal(focused.scrollY,0);seen.add(focused.route);
    (report.keyboard_navigation??=[]).push({width,mode,kind:'select',...focused});
   }
   assert.equal(seen.size,12,'all twelve chapter choices work with real keys');continue;
  }
  for(let i=0;i<35&&seen.size<12;i++){
   await p.keyboard.press('Tab');await wait(40);
   const focused=await p.evaluate(()=>{const e=document.activeElement;if(!e.matches('.nav-shell nav a'))return null;const a=e.getBoundingClientRect(),n=e.closest('nav').getBoundingClientRect(),s=getComputedStyle(e);return {route:e.dataset.route,left:a.left,right:a.right,navLeft:n.left,navRight:n.right,focusVisible:e.matches(':focus-visible'),outline:s.outlineStyle,scrollY};});
   if(!focused)continue;seen.add(focused.route);
   (report.keyboard_navigation??=[]).push({width,mode,...focused});
   assert.ok(focused.left>=focused.navLeft-1&&focused.right<=focused.navRight+1,'entire keyboard-focused label visible');
   assert.ok(focused.focusVisible&&focused.outline!=='none','keyboard focus indicator');assert.equal(focused.scrollY,0);
  }
  assert.equal(seen.size,12,'all twelve chapter links in real Tab order');
 }
 report.checks.push('120 actual keyboard route choices: desktop Tab links and compact native selector, visible focus, no document scrolling');
 report.threshold_views=[];
 for(const width of [320,390,768,1440,1920])for(const mode of ['light','dark']){
  await choose(p,width,mode,'train119');
  await p.waitForFunction(()=>{const svg=document.querySelector('#gamma-chart svg'),label=svg?.querySelector('text.chart-label');return label?.textContent==='Frozen stop'&&svg.lastElementChild===label;});
  const annotation=await p.$eval('#gamma-chart text.chart-label',e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return {paintOrder:s.paintOrder,strokeWidth:parseFloat(s.strokeWidth),stroke:s.stroke,text:e.textContent,width:r.width,height:r.height};});
  assert.deepEqual(expandedPaintOrder(annotation.paintOrder),['stroke','fill','markers']);assert.ok(annotation.strokeWidth>=4);assert.equal(annotation.text,'Frozen stop');assert.ok(annotation.width>0&&annotation.height>0);
  const panelColor=await p.$eval('#gamma-chart',e=>{const probe=document.createElement('span');probe.style.color='var(--panel)';e.appendChild(probe);const color=getComputedStyle(probe).color;probe.remove();return color;});
  assert.equal(annotation.stroke,panelColor,'annotation halo uses the opaque chart panel color');
  report.threshold_views.push({width,mode,...annotation});
  await p.$eval('#gamma-chart',e=>e.scrollIntoView({block:'center',behavior:'instant'}));
  await wait(80);
  const chartShot=`threshold_${mode}_${width}.png`;
  await (await p.$('#gamma-chart')).screenshot({path:path.join(out,chartShot)});
  report.screenshots.push(chartShot);
 }
 report.checks.push('threshold label draws after data marks with an opaque halo at all ten theme-width combinations');

 await choose(p,1440,'light');
 for(const id of ['opt-parameters','opt-episode','opt-checkpoints','opt-candidate','opt-evidence','opt-next-study']){
  await p.$eval('#'+id,e=>e.scrollIntoView({block:'start',behavior:'instant'}));
  await p.waitForFunction(s=>document.querySelector('.cin-chapter-map').dataset.readingSection===s,{},id);
  assert.equal(await p.$eval('.cin-chapter-map a[aria-current="location"]',e=>e.hash),'#'+id);
  const beforeFocus=await p.evaluate(()=>{document.querySelector('.site-header .brand').focus({preventScroll:true});return window.scrollY;});
  await p.evaluate(()=>window.dispatchEvent(new Event('scroll')));await wait(50);
  assert.equal(await p.evaluate(()=>document.activeElement===document.querySelector('.site-header .brand')),true);
  assert.equal(await p.evaluate(()=>window.scrollY),beforeFocus);
 }
 await choose(p,390,'light');assert.equal(await p.$eval('.cin-chapter-map',e=>getComputedStyle(e).position),'static');
 report.checks.push('six reading locations; compass never changes focus or scroll and is not sticky on mobile');
 await choose(p,1440,'light');
 for(const [key,count] of [['radial',216],['invariant',29],['offset',3],['all',248]]){
  await click(`[data-cin-group-select="${key}"]`);assert.equal(await p.$eval('#cin-atlas-count',e=>Number(e.textContent)),count);assert.equal(await p.$eval(`[data-cin-group-select="${key}"]`,e=>e.getAttribute('aria-pressed')),'true');
 }
 await p.focus('[data-cin-group-select="all"]');await p.keyboard.press('ArrowRight');assert.equal(await p.$eval('#opt-coefficient-atlas',e=>e.dataset.selection),'radial');await p.keyboard.press('ArrowLeft');assert.equal(await p.$eval('#opt-coefficient-atlas',e=>e.dataset.selection),'all');await p.keyboard.press('End');assert.equal(await p.$eval('#opt-coefficient-atlas',e=>e.dataset.selection),'offset');await p.keyboard.press('Home');assert.equal(await p.$eval('#opt-coefficient-atlas',e=>e.dataset.selection),'all');report.checks.push('all four coefficient families, native pointer and Left/Right/Home/End');
 for(const id of payload.theory.main4500.native_order){
  await p.focus(`[data-cin-step="${id}"]`);await p.keyboard.press('Enter');await p.waitForFunction(s=>window.optimizationExhibit.getState().selectedState===s,{},id);await wait(20);assert.equal(await p.$eval(`[data-cin-step="${id}"]`,e=>e.getAttribute('aria-pressed')),'true');
 }
 await p.evaluate(()=>window.optimizationExhibit.selectState('S1c'));await wait(20);assert.equal(await p.$$eval('[data-cin-step][aria-pressed="true"]',e=>e.length),0);report.checks.push('native rail delegates to original controller; diagnostic copy never becomes a native node');
 await p.evaluate(()=>window.optimizationExhibit.reset());await click('#opt-play');await p.waitForFunction(()=>document.querySelector('[data-cin-step="S1"]').getAttribute('aria-pressed')==='true');await click('#opt-play');assert.equal(await p.evaluate(()=>window.optimizationExhibit.getState().playing),false);report.checks.push('existing playback and pause synchronize rail without a second clock');
 await p.focus('.skip-link');await p.keyboard.press('Enter');assert.equal(await p.evaluate(()=>location.hash),'#optimization');assert.equal(await p.evaluate(()=>document.activeElement.id),'optimization');report.checks.push('skip link retains current route and focuses chapter');
 await choose(p,390,'dark','molecule');await click('#path-play');await wait(150);assert.equal(await p.$eval('#path-play',e=>e.getAttribute('aria-label')),await p.$eval('#path-play',e=>e.textContent.trim()));await click('#path-play');await wait(30);assert.equal(await p.$eval('#path-play',e=>e.getAttribute('aria-label')),await p.$eval('#path-play',e=>e.textContent.trim()));report.checks.push('legacy play/pause accessible name follows visible state');
 await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);await choose(p,390,'dark');assert.equal(await p.$eval('.opt-hero-copy',e=>getComputedStyle(e).animationName),'none');await click('#opt-play');assert.equal(await p.evaluate(()=>window.optimizationExhibit.getState().playing),false);report.checks.push('reduced motion disables heading entrance and automatic sequence');
 const nojs=await browser.newPage();await nojs.setJavaScriptEnabled(false);await nojs.goto(url+'#optimization',{waitUntil:'networkidle0'});assert.equal(await nojs.$$eval('[data-cin-cell]',e=>e.length),248);assert.equal(await nojs.$$eval('#optimization button:not(:disabled)',e=>e.length),0);await nojs.close();report.checks.push('no-JS figures, definitions, unmeasured state and disabled controls');
 const failed=await browser.newPage();await failed.setRequestInterception(true);failed.on('request',r=>r.url().endsWith('/data/optimization.json')?r.abort():r.continue());await failed.goto(url+'?still#optimization',{waitUntil:'networkidle0'});await failed.waitForFunction(()=>document.body.dataset.optimizationReady==='error');assert.equal(await failed.$$eval('#optimization button:not(:disabled)',e=>e.length),0);await failed.close();report.checks.push('missing JSON leaves every new and existing state control disabled');
 assert.deepEqual(report.errors,[]);report.status='PASS';
}catch(error){report.status='FAIL';report.failure=error.stack;throw error;}
finally{fs.writeFileSync(path.join(out,'CINEMATIC_QA.json'),JSON.stringify(report,null,2));await browser.close();}
