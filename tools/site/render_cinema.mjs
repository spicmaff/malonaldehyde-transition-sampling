/* Deterministic presentation capture, not physical simulation.
 * Run a built exhibit over HTTP, set BROWSER_DEPS and CINEMA_OUT to new paths.
 * Requires Chrome and ffmpeg/libx264. Uses project-owned scenes and system fonts.
 */
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn,execFileSync} from 'node:child_process';
import {once} from 'node:events';
const require=createRequire(path.join(path.resolve(process.env.BROWSER_DEPS||'.'),'package.json'));
const pp=require('puppeteer-core');
const base=process.env.SITE_URL||'http://127.0.0.1:8768/';
const out=path.resolve(process.env.CINEMA_OUT||'cinema-output');
if(fs.existsSync(out)&&fs.readdirSync(out).length)throw new Error('CINEMA_OUT must be new or empty; refuse replacing a previous render');
fs.mkdirSync(out,{recursive:true});
const fps=60,width=1920,height=1080;
const browser=await pp.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
const records=[];
try{
  await page.setViewport({width,height,deviceScaleFactor:1});await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
  await page.goto(base+'?still#story',{waitUntil:'networkidle0',timeout:45000});await page.waitForFunction(()=>document.body.dataset.ready==='true');
  await page.waitForFunction(()=>window.exhibit.renderers()['story-molecule']==='webgl',{timeout:30000});
  await page.evaluate(()=>{window.exhibit.stop();document.body.classList.add('export-mode');window.dispatchEvent(new Event('resize'));});
  await new Promise(r=>setTimeout(r,250));
  const science=await page.evaluate(()=>window.exhibit.science());
  for(const spec of [{name:'molecular-path',duration:12,title:'The proton and the moving scaffold',map:t=>Math.min(.166666-1e-7,t/6),scope:'Nine saved PBE images with display interpolation; no physical reaction clock.'},{name:'research-story',duration:30,title:'Several tests of trust',map:t=>t,scope:'Six data-driven research scenes. No new physical calculations or independent deployment claim.'}]){
    const filename=spec.name+'.mp4',target=path.join(out,filename),frames=fps*spec.duration;
    const ff=spawn('ffmpeg',['-hide_banner','-loglevel','error','-f','image2pipe','-framerate',String(fps),'-vcodec','mjpeg','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart','-threads','4',target],{stdio:['pipe','ignore','pipe']});
    let fferr='';ff.stderr.on('data',x=>fferr+=x);const close=once(ff,'close');
    for(let i=0;i<frames;i++){
      await page.evaluate(t=>window.exhibit.seek('story',t),spec.map(i/(frames-1)));
      const buffer=await page.screenshot({type:'jpeg',quality:91,captureBeyondViewport:false});
      if(!ff.stdin.write(buffer))await once(ff.stdin,'drain');
      if(i%180===0)console.log(JSON.stringify({film:filename,rendered_frames:i,total_frames:frames}));
    }
    ff.stdin.end();const [code]=await close;if(code!==0)throw new Error('ffmpeg failed: '+fferr);
    const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate,nb_read_frames,duration','-of','json',target],{encoding:'utf8'})).streams[0];
    if(probe.width!==width||probe.height!==height||probe.r_frame_rate!=='60/1'||Number(probe.nb_read_frames)!==frames)throw new Error('Encoded media contract failed');
    execFileSync('ffmpeg',['-v','error','-i',target,'-f','null','-'],{stdio:['ignore','ignore','pipe']});
    await page.evaluate(t=>window.exhibit.seek('story',t),spec.name==='molecular-path'?.075:.04);
    const poster=spec.name+'.jpg';await page.screenshot({path:path.join(out,poster),type:'jpeg',quality:94,captureBeyondViewport:false});
    const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(path.join(out,f))).digest('hex');
    records.push({title:spec.title,file:'cinema/'+filename,poster:'cinema/'+poster,scope:spec.scope,width,height,fps,frames,duration_seconds:spec.duration,sha256:hash(filename),poster_sha256:hash(poster),source_science_commit:science.science_commit,source_evidence_commit:science.source_commit,renderer:'tools/site/render_cinema.mjs + site/app.mjs + site/molecule.mjs',physical_time:false});
    console.log(JSON.stringify({film:filename,status:'ENCODED_DECODED_VERIFIED',frames,fps,bytes:fs.statSync(target).size}));
  }
  for(const record of records){
    const stem=path.basename(record.file,'.mp4');
    let captions;
    if(stem==='molecular-path') captions='WEBVTT\n\n00:00.000 --> 00:12.000\nThe proton and the heavy-atom scaffold move along nine saved PBE images.\nIntermediate frames are display interpolation, not physical reaction time.\n';
    else {const labels=[['One proton. A moving scaffold.','Nine saved PBE images, not a time-resolved reaction.'],['Spend the labels differently.','36 shared configurations, then 24 additions per training branch.'],['A striking original result.','The frozen original model pair is not a seed-robust causal estimate.'],['Then repeat the training.','Targeted wins both primary metrics in three of five paired seeds.'],['A warning is not a force error.','Five coverage crossings coexist with small local PBE force errors.'],['Keep the boundary of the claim.','No independent deployment validation. The historical failure remains.']];
      captions='WEBVTT\n\n'+labels.map(([a,b],i)=>`00:${String(i*5).padStart(2,'0')}.000 --> 00:${String((i+1)*5).padStart(2,'0')}.000\n${a}\n${b}`).join('\n\n')+'\n';}
    const name=stem+'.vtt';fs.writeFileSync(path.join(out,name),captions);record.captions='cinema/'+name;record.captions_sha256=crypto.createHash('sha256').update(captions).digest('hex');
  }
  if(errors.length)throw new Error(errors.join('\n'));
  fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({schema:'proton-cinema-v2',new_physical_calls:0,films:records},null,2)+'\n');
}finally{await browser.close();}
