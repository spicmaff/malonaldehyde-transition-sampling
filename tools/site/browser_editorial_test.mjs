/* Acceptance in the existing GitHub browser runner; no physical programs run. */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const require=createRequire(path.resolve(process.env.BROWSER_DEPS||'tools/site','package.json'));
const puppeteer=require('puppeteer-core');
const out=process.env.QA_OUT||'qa-local/editorial';fs.mkdirSync(out,{recursive:true});
const base=process.env.SITE_URL||'http://127.0.0.1:8768/';
const compareOnly=process.env.EDITORIAL_COMPARE_ONLY==='1';
const report={status:'RUNNING',checks:[],screenshots:[],errors:[]};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--disable-dev-shm-usage']});
const p=await browser.newPage();p.on('pageerror',e=>report.errors.push(String(e)));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function go(route){await p.goto(base+'?still#'+route,{waitUntil:'networkidle0'});await p.waitForFunction(()=>document.body.dataset.ready==='true');await delay(180);}
async function image(name){await p.screenshot({path:path.join(out,name),fullPage:false});report.screenshots.push(name);}
try{
  if(!compareOnly){
  await p.setViewport({width:1440,height:1000});await go('sampling');
  assert.deepEqual(await p.$$eval('#sampling-basin [data-pbe-image],#sampling-targeted [data-pbe-image]',n=>[n.length,n.slice(0,9).map(x=>+x.dataset.pbeImage)]),[18,[1,2,3,4,5,6,7,8,9]]);
  assert.equal(await p.$$eval('[data-candidate]',n=>n.length),120);
  await p.focus('#ed-sampling-image');await p.keyboard.press('Home');
  assert.match(await p.$eval('#ed-sampling-readout',n=>n.textContent),/Image 1 \/ 9/);
  await p.keyboard.press('End');assert.match(await p.$eval('#ed-sampling-readout',n=>n.textContent),/Image 9 \/ 9/);
  await p.focus('#ed-sampling-molecule');await p.keyboard.press('ArrowRight');
  assert.ok(await p.$eval('#ed-sampling-molecule',n=>n.dataset.orientation));
  report.checks.push('120 saved training points, 18 PBE overlay points, linked keyboard selection and rotation');
  await go('landscape');await p.focus('#energy-image');await p.keyboard.press('Home');
  assert.match(await p.$eval('#ed-energy-readout',n=>n.textContent),/Image 1 \/ 9/);
  const axis=await p.$$eval('#energy-chart .chart-axis',n=>n.map(x=>x.textContent));
  await p.click('[data-model="Basin60"]');assert.deepEqual(await p.$$eval('#energy-chart .chart-axis',n=>n.map(x=>x.textContent)),axis);
  report.checks.push('energy geometry linkage; comparison axis unchanged when a branch is hidden');
  await p.setViewport({width:390,height:1000});await go('overview');
  await p.waitForFunction(()=>document.body.dataset.offpathReady==='true'&&document.body.dataset.optimizationReady==='true');
  await p.select('#ed-contents','offpath');
  await p.waitForFunction(()=>document.querySelector('#offpath.active')&&window.offpathExhibit?.getState().renderer);
  assert.equal(await p.$eval('#ed-contents',n=>document.activeElement===n),true);
  await p.click('#off-reveal');assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().playing),true);
  await p.select('#ed-contents','optimization');
  await p.waitForFunction(()=>document.querySelector('#optimization.active'));
  assert.equal(await p.evaluate(()=>window.offpathExhibit.getState().playing),false);
  await p.goBack();await p.waitForFunction(()=>document.querySelector('#offpath.active'));
  report.checks.push('compact chapter navigation initializes independent modules, stops prior playback, retains focus and supports browser Back');

  const axe=fs.readFileSync(require.resolve('axe-core/axe.min.js'),'utf8');
  for(const theme of ['light','dark'])for(const width of [1440,390,320]){
    await p.setViewport({width,height:1000});
    for(const route of ['overview','sampling','landscape','offpath','optimization','longread','reproduce']){
      await go(route);await p.evaluate(t=>{document.documentElement.dataset.theme=t;localStorage.setItem('proton-theme',t);},theme);
      const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);assert.equal(overflow,false,`${route} ${theme} ${width}`);
      if(width!==320&&['overview','sampling','optimization'].includes(route))await image(`after-${route}-${theme}-${width}.png`);
      await p.addScriptTag({content:axe});
      const issues=await p.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}));});
      assert.deepEqual(issues,[],`${route} ${theme} ${width} accessibility`);
    }
  }
  report.checks.push('42 width/theme/chapter views: no page overflow, zero WCAG A/AA violations');
  }
  if(process.env.EDITORIAL_BEFORE_URL){
    await p.setViewport({width:1440,height:1000});
    for(const route of ['overview','sampling','optimization']){
      await p.goto(process.env.EDITORIAL_BEFORE_URL+'?still#'+route,{waitUntil:'networkidle0'});await delay(200);
      await p.evaluate(()=>{document.documentElement.dataset.theme='light';localStorage.setItem('proton-theme','light');window.scrollTo(0,0);});
      await image(`before-${route}-light-1440.png`);
    }
  }
  assert.deepEqual(report.errors,[]);report.status=compareOnly?'PASS_EDITORIAL_COMPARISON_QA':'PASS_EDITORIAL_BROWSER_QA';
}catch(e){report.status='FAIL';report.failure=String(e.stack||e);process.exitCode=1;}
finally{fs.writeFileSync(path.join(out,compareOnly?'EDITORIAL_COMPARISON_QA.json':'EDITORIAL_BROWSER_QA.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report,null,2));}
