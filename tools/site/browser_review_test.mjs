/* Final review supplement: never substitutes for the three existing runners.
 * Records incomplete axe findings, before/after views and stable-pointer trials.
 * No native scientific software is loaded or invoked. */
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const deps=process.env.BROWSER_DEPS;
if(!deps)throw new Error('BROWSER_DEPS is required');
const require=createRequire(path.join(path.resolve(deps),'package.json'));
const puppeteer=require('puppeteer-core'),axe=require.resolve('axe-core/axe.min.js');
const base=process.env.SITE_URL||'http://127.0.0.1:8768/';
const before=process.env.REVIEW_BEFORE_URL;
const baseline=process.env.REVIEW_BASELINE_URL;
if(!before||!baseline)throw new Error('Both pinned comparison builds are required');
const out=path.resolve(process.env.QA_OUT||'presentation-review-qa');
fs.mkdirSync(out,{recursive:true});
const report={status:'RUNNING',commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),
 tree:execFileSync('git',['rev-parse','HEAD^{tree}'],{encoding:'utf8'}).trim(),
 previous_ref:'d37e7ceb209f0eb68fa4e36a0bec5af20e58fc35',
 baseline_ref:'f5f4784d7cc186ae9cfcacbd97117b5dabbffb30',
 views:[],before:[],screenshots:[],pause_trials:[],live:[],errors:[],new_scientific_calls:0};
const routes=['overview','molecule','sampling','landscape','seeds','train119','forces','story','longread','reproduce','offpath','optimization'];
const widths=[320,390,768,1440,1920],modes=['light','dark'];
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,protocolTimeout:60000,
 args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
report.browser=await browser.version();
async function open(url){
 const p=await browser.newPage();p.on('pageerror',e=>report.errors.push(e.message));
 await p.setViewport({width:1440,height:1000,deviceScaleFactor:1});
 await p.goto(url+'?still&utm_source=chatgpt.com#overview',{waitUntil:'networkidle0'});
 await p.waitForFunction(()=>document.body.dataset.ready==='true');
 await p.addScriptTag({path:axe});return p;
}
async function choose(p,route,mode,width){
 await p.bringToFront();
 await p.setViewport({width,height:width===1920?1080:width<768?844:1000,deviceScaleFactor:1});
 await p.evaluate(({route,mode})=>{
  window.exhibit.stop();window.optimizationExhibit?.stop();
  if((document.documentElement.dataset.theme==='dark')!==(mode==='dark'))document.getElementById('theme').click();
  location.hash=route;
 },{route,mode});
 await p.waitForFunction(r=>document.getElementById(r).classList.contains('active'),{},route);
 await p.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await wait(100);
}
async function audit(p){
 return p.evaluate(async()=>{
  const a=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});
  const inspect=n=>{
   let e;try{e=document.querySelector(n.target[0]);}catch{}
   if(!e)return {target:n.target,html:n.html,unresolved:true};
   const c=getComputedStyle(e),rect=e.getBoundingClientRect();
   let opacity=1;const backgrounds=[];
   for(let p=e;p;p=p.parentElement){
    const s=getComputedStyle(p);opacity*=Number(s.opacity);
    if(s.backgroundColor!=='rgba(0, 0, 0, 0)'||s.backgroundImage!=='none')
     backgrounds.push({tag:p.tagName,id:p.id,class:p.className?.baseVal??p.className,color:s.backgroundColor,image:s.backgroundImage});
   }
   return {target:n.target,html:n.html,text:e.textContent.trim().slice(0,240),
    tag:e.tagName,role:e.getAttribute('role'),color:c.color,fill:c.fill,fillOpacity:c.fillOpacity,
    fontSize:c.fontSize,fontWeight:c.fontWeight,opacity,backgrounds,
    rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},
    checks:[...n.any,...n.all,...n.none].map(x=>({id:x.id,message:x.message,data:x.data}))};
  };
  const compact=v=>({id:v.id,impact:v.impact,description:v.description,helpUrl:v.helpUrl,nodes:v.nodes.map(inspect)});
  return {axeVersion:axe.version,violations:a.violations.map(compact),incomplete:a.incomplete.map(compact),
   overflow:document.documentElement.scrollWidth>innerWidth+1,
   activePages:document.querySelectorAll('[data-page].active').length,
   routeCount:document.querySelectorAll('[data-page]').length};
 });
}
async function shot(p,name,fullPage=false){
 await p.bringToFront();
 const file=path.join(out,name+'.png');await p.screenshot({path:file,fullPage});
 report.screenshots.push({file:name+'.png',fullPage,bytes:fs.statSync(file).size,
  sha256:createHash('sha256').update(fs.readFileSync(file)).digest('hex')});
}
async function stableClick(p,selector){
 await p.$eval(selector,e=>e.scrollIntoView({block:'center',behavior:'instant'}));
 await p.waitForFunction(s=>{const e=document.querySelector(s),r=e.getBoundingClientRect(),h=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return h===e||e.contains(h);},{timeout:5000},selector);
 await wait(80);await p.click(selector);
}
try{
 const p=await open(base),old=await open(before),historical=await open(baseline);
 for(const width of widths)for(const mode of modes)for(const route of routes){
  await choose(old,route,mode,width);const prior=await audit(old);
  report.before.push({route,width,mode,...prior});
  await choose(p,route,mode,width);const current=await audit(p);
  report.views.push({route,width,mode,...current});
  if(report.views.length%12===0){fs.writeFileSync(path.join(out,'PRESENTATION_REVIEW_PROGRESS.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({completedViews:report.views.length,width,mode}));}
  assert.equal(current.overflow,false,`${route}/${mode}/${width}: overflow`);
  assert.equal(current.activePages,1);assert.equal(current.routeCount,12);
  assert.deepEqual(current.violations,[],`${route}/${mode}/${width}: axe violations`);
  assert.ok(!current.incomplete.some(v=>v.id==='aria-prohibited-attr'),`${route}: unresolved prohibited ARIA`);
  if([1440,390].includes(width)){
   await shot(p,`after_${mode}_${width}_${route}`);
   if(['overview','optimization'].includes(route))await shot(old,`before_${mode}_${width}_${route}`);
   if(['overview','molecule','story','offpath'].includes(route)){
    await choose(historical,route,mode,width);await shot(historical,`main_${mode}_${width}_${route}`);
   }
   if(route==='optimization')await shot(p,`full_${mode}_${width}_${route}`,true);
  }
 }
 await choose(p,'overview','light',1440);
 await stableClick(p,'.review-optimization-entry');
 await p.waitForFunction(()=>document.getElementById('optimization').classList.contains('active'));
 assert.equal(await p.$eval('#opt-recovery-availability',e=>e.getAttribute('role')),'note');
 report.overview_entry='PASS';
 await choose(p,'molecule','light',1440);
 for(let i=0;i<12;i++){
  await stableClick(p,'#path-reset');await stableClick(p,'#path-play');await wait(250);
  const running=await p.evaluate(()=>window.exhibit.getState().motion);
  assert.notEqual(running,null);
  await stableClick(p,'#path-play');const paused=await p.evaluate(()=>window.exhibit.getState().motion);
  const position=await p.$eval('#path-slider',e=>e.value);await wait(160);
  assert.equal(paused,null);assert.equal(await p.$eval('#path-slider',e=>e.value),position);
  report.pause_trials.push({trial:i+1,running,paused,position});
 }
 const nojs=await browser.newPage();await nojs.setJavaScriptEnabled(false);
 await nojs.goto(base+'#optimization',{waitUntil:'networkidle0'});
 assert.ok(await nojs.$eval('#opt-recovery-availability',e=>e.innerText.includes('currently unavailable')));
 assert.equal(await nojs.$eval('#opt-state-chart',e=>e.getAttribute('role')),'group');
 await nojs.close();report.static_disclosure='PASS';
 // Production is read only. PR13 has already published Optimization in d713f60.
 // Keep the live-route probe aligned with that twelve-chapter release, not its old draft status.
 // Failure is recorded, never disguised as a local test.
 const live=await browser.newPage();
 for(const route of ['overview','offpath']){
  const response=await live.goto('https://spicmaff.github.io/malonaldehyde-transition-sampling/?utm_source=chatgpt.com&still#'+route,{waitUntil:'networkidle0',timeout:45000});
  await live.waitForFunction(()=>document.body.dataset.ready==='true');
  const d=await live.evaluate(()=>({route:window.exhibit.getState().route,routeCount:document.querySelectorAll('[data-page]').length,optimizationPublished:!!document.getElementById('optimization')}));
  report.live.push({status:response?.status()??null,navigation:response?'document':'same-document',...d});if(response)assert.equal(response.status(),200);assert.equal(d.route,route);assert.equal(d.optimizationPublished,true);assert.equal(d.routeCount,12);
 }
 await live.close();await p.close();await old.close();await historical.close();
 assert.equal(report.views.length,120);assert.equal(report.before.length,120);assert.deepEqual(report.errors,[]);
 report.status='PASS_PRESENTATION_REVIEW_AUTOMATION_MANUAL_CONTRAST_PENDING';
}catch(e){report.status='FAIL';report.failure=String(e.stack||e);process.exitCode=1;}
finally{
 report.beforeIncomplete=report.before.reduce((n,v)=>n+v.incomplete.length,0);
 report.afterIncomplete=report.views.reduce((n,v)=>n+v.incomplete.length,0);
 fs.writeFileSync(path.join(out,'PRESENTATION_REVIEW.json'),JSON.stringify(report,null,2));
 await browser.close();console.log(JSON.stringify({status:report.status,views:report.views.length,before:report.before.length,
  beforeIncomplete:report.beforeIncomplete,afterIncomplete:report.afterIncomplete,pause:report.pause_trials.length,failure:report.failure}));
}
