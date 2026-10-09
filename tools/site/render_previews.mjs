/* Deterministic presentation-only video export. Uses the live site's exact seek API.
 * Run with BROWSER_DEPS, SITE_URL, CINEMA_OUT. Requires system Chrome and ffmpeg.
 * Never runs QE, MLIP, selectors, or dynamics. Does not overwrite prior clips.
 */
import fs from 'node:fs';import path from 'node:path';import {spawn} from 'node:child_process';import {once} from 'node:events';import {createRequire} from 'node:module';import {createHash} from 'node:crypto';
const deps=process.env.BROWSER_DEPS;if(!deps)throw Error('BROWSER_DEPS required');
const req=createRequire(path.join(deps,'package.json')),puppeteer=req('puppeteer-core');
const root=(process.env.SITE_URL||'http://127.0.0.1:8783/').replace(/\/?$/,'/');
const out=process.env.CINEMA_OUT;if(!out)throw Error('CINEMA_OUT required');fs.mkdirSync(out,{recursive:true});
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const spec=[{id:'hero',route:'overview',seconds:18,title:'The moving scaffold',file:'01_moving_scaffold.mp4',poster:'01_moving_scaffold.jpg'},
{id:'train119',route:'train119',seconds:10.5,title:'Coverage is not force error',file:'02_two_verdicts.mp4',poster:'02_two_verdicts.jpg'},
{id:'forces',route:'forces',seconds:9,title:'Inside the force error',file:'03_inside_force_error.mp4',poster:'03_inside_force_error.jpg'}];
const b=await puppeteer.launch({headless:true,executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const manifest={schema:'english-cinematic-previews-v2',scientific_snapshot:'f44d28cc0b13defb747f625376b083055b577629',scope:'Screen time is not reaction time. All moving intermediate geometries and energies are display interpolation; force arrows show stored PBE/MTP vectors.',new_physical_calls:0,films:[]};
const requested=process.env.ONLY_SCENES?.split(',');
const selected=requested?spec.filter(v=>requested.includes(v.id)):spec;
if(!selected.length)throw Error('No requested scenes');
if(requested&&fs.existsSync(path.join(out,'manifest.json'))){
 const prior=JSON.parse(fs.readFileSync(path.join(out,'manifest.json'),'utf8'));
 manifest.films=(prior.films||[]).filter(v=>!requested.includes(v.id));
}
try{
 for(const v of selected){
  const dest=path.join(out,v.file);if(fs.existsSync(dest))throw Error('Refuse overwriting '+dest);
  const page=await b.newPage();await page.setViewport({width:1920,height:1080,deviceScaleFactor:1});
  await page.goto(root+'?capture=1#'+v.route,{waitUntil:'networkidle0',timeout:45000});await page.waitForFunction(()=>window.__proton?.ready);
  await page.evaluate(()=>{document.documentElement.dataset.theme='light';window.__proton.redraw();});
  const common=`html,body{width:1920px!important;height:1080px!important;overflow:hidden!important}main{padding:40px 56px!important}.capture .page-heading,.chapter-footer,.transport,.evidence,.data-table,footer,.site-header,.story-chapters{display:none!important}.capture .scene-description{font-size:15px}.capture .hero-readouts span{font-size:12px}.capture .hero-readouts strong{font-size:31px}.capture .scene-top,.capture .scene-bottom{font-size:11px}.capture .hero-context{font-size:22px}.capture .hero-science .molecular-stage.large{height:550px}.capture .hero-copy{padding:55px 20px}.capture .hero-layout{gap:55px;grid-template-columns:.95fr 1.1fr}.capture .hero-copy h1{font-size:104px}.capture .actions{display:none!important}.capture .hero-chart{margin-top:30px}.capture .byline{font-size:13px}`;
  await page.addStyleTag({content:common});
  if(v.id==='train119'){
   await page.addStyleTag({content:`#train119>.essay-pair,#train119>.wide-card,#train119>.frame-controls{display:none!important}#train119{padding:0}.capture-title{margin:10px 0 45px}.capture-title h1{font-size:65px;line-height:1.05}.capture-title p{font-size:21px;margin-top:20px}.two-plots .wide-card{padding:36px}.record-strip{margin:35px 0}.record-strip strong{font-size:31px}.record-strip span,.record-strip small{font-size:15px}.two-plots{gap:32px}.capture-footer{font-size:17px;border-left:3px solid #a44d27;padding:14px 20px;margin-top:35px;max-width:none}`});
   await page.evaluate(()=>{const s=document.querySelector('#train119');const div=document.createElement('div');div.className='capture-title';div.innerHTML='<p class="eyebrow">PROTON / POTENTIAL · LOCAL PBE DIAGNOSTIC</p><h1>Coverage is not force error.</h1><p>Seven saved development frames. Two different criteria. The historical failure is not erased.</p>';s.prepend(div);const foot=document.createElement('p');foot.className='capture-footer';foot.textContent='Crossing7 · saved 100 K neighborhood · five coverage crossings · no independent deployment validation';s.append(foot);});
  }
  if(v.id==='forces'){
   await page.addStyleTag({content:`#forces .molecular-stage{height:660px}.capture-title{margin:0 0 30px}.capture-title h1{font-size:62px}.capture-title p{font-size:19px}.capture .experiment-grid{grid-template-columns:1.4fr 1fr;gap:45px}.capture .analysis .control-grid,.capture .analysis>label,.capture .control-grid{display:none}.capture .analysis .fine{font-size:15px}.force-record .vector-summary{font-size:60px}.force-record th,.force-record td{font-size:17px;padding:15px 9px}.force-legend{font-size:17px}.analysis .note{font-size:16px}.capture .analysis{padding-top:50px}`});
   await page.evaluate(()=>{const s=document.querySelector('#forces'),div=document.createElement('div');div.className='capture-title';div.innerHTML='<p class="eyebrow">PROTON / POTENTIAL · SAVED VECTORS, NOT MOTION</p><h1>Inside the force error.</h1><p>Transferred hydrogen H2 · source-frame components · PBE → MTP → difference</p>';s.prepend(div);const el=document.querySelector('#force-frame');el.value='7';el.dispatchEvent(new Event('change',{bubbles:true}));});
  }
  await page.evaluate(()=>window.__proton.redraw());
  const frames=Math.round(v.seconds*60),fps=60;let errorText='';
  const ff=spawn('ffmpeg',['-y','-loglevel','error','-f','image2pipe','-vcodec','mjpeg','-framerate',String(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart','-frames:v',String(frames),dest],{stdio:['pipe','ignore','pipe']});
  ff.stderr.on('data',d=>errorText+=d.toString());let pipeError;ff.stdin.on('error',e=>pipeError=e);
  const completion=new Promise((res,rej)=>{ff.on('error',rej);ff.on('close',code=>code===0?res():rej(Error('ffmpeg failed '+code+' '+errorText)));});
  const start=Date.now();
  for(let i=0;i<frames;i++){
   if(pipeError)throw pipeError;
   await page.evaluate(({id,t})=>window.__proton.seek(id,t),{id:v.id,t:i/(frames-1)});
   const jpeg=await page.screenshot({type:'jpeg',quality:92,optimizeForSpeed:true});
   if(!ff.stdin.write(jpeg))await once(ff.stdin,'drain');
   if(i===Math.floor(frames*.52))fs.writeFileSync(path.join(out,v.poster),jpeg);
   if(i%180===0)console.log(v.id,i+'/'+frames,'frames',Math.round((Date.now()-start)/1000)+'s');
  }
  ff.stdin.end();await completion;await page.close();
  manifest.films.push({...v,fps,frames,width:1920,height:1080,sha256:hash(dest),poster_sha256:hash(path.join(out,v.poster)),english_on_frame_text:true,render_seconds:Math.round((Date.now()-start)/1000)});
  fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  console.log('EXPORTED',v.file,frames,'frames',fs.statSync(dest).size,'bytes');
 }
}finally{await b.close();}
console.log(JSON.stringify({status:'PASS_DETERMINISTIC_ENGLISH_PREVIEWS',films:manifest.films.length,new_physical_calls:0},null,2));
