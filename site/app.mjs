import {ATOMS,clamp,mix,smooth,norm,pathState,geometry,route,sceneState,finiteTree} from './core.mjs';
import {MoleculeView} from './molecule.mjs';
import {chart,samplingPlot,seedPlot,palette} from './charts.mjs';
const $=id=>document.getElementById(id), $$=s=>[...document.querySelectorAll(s)];
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
let D,active='overview',running=null,raf=0;
const progress={hero:0,molecule:0,sampling:1,landscape:0,seeds:1,train119:0,forces:1,story:0};
const durations={hero:18000,molecule:16000,sampling:10000,landscape:12000,seeds:14000,train119:10500,forces:9000,story:48000};
const state={path:4,angle:-12,energy:4,seed:0,metric:'barrier',group:'CROSSING7',frame:3,forceFrame:0,atom:1,forceAngle:-12,forceGain:1.2,forceLayer:'all',forceReveal:1};
const views={};let lastHero={position:4,camera:{yaw:-.24,tilt:.32}};
const fmt=(x,n=4)=>Number(x).toFixed(n),pressed=(id,v)=>$(id)?.setAttribute('aria-pressed',String(v));
function markStage(id){$('stage-'+id)?.classList.add('is-ready');}
function drawMolecule(id,xyz,opts={}){views[id].render(xyz,opts);markStage(id);const badge=$('stage-'+id)?.querySelector('.status-dot');if(badge)badge.textContent=opts.saved===false?'Display interpolation':opts.force?'Saved local geometry':'Saved PBE geometry';}
function pointSeries(key,profile){return {key,name:profile,dash:key==='basin'?'5 3':key==='targeted'?'2 3':null,points:D.molecule.map((m,i)=>({x:m.q,y:D.profiles[profile][i],index:i,label:'NEB image '+(i+1)}))};}
function hero(position=4,camera=lastHero.camera){
 lastHero={position,camera};const v=pathState(D,position);drawMolecule('hero',v.xyz,{camera,zoom:1.05,measure:true,saved:v.saved});
 $('hero-q').innerHTML=fmt(v.q)+' <small>Å</small>';$('hero-roo').innerHTML=fmt(v.roo)+' <small>Å</small>';$('hero-energy').innerHTML=fmt(v.energy,3)+' <small>meV</small>';
 chart($('hero-chart'),{series:[pointSeries('pbe','PBE')],height:132,label:'PBE energy along the nine saved structures',xlabel:'Proton coordinate qPT (Å)',ylabel:'PBE relative energy (meV)',xDomain:[-.52,.52],yDomain:[0,40],xTicks:[-.48,0,.48],activeX:v.q,activeIndex:v.saved?v.image-1:-1});
 $('hero-caption').textContent=v.saved?'Saved NEB image '+v.image+' of 9. Playback seconds are not reaction time.':'Display interpolation between saved images. No new DFT or dynamics.';
}
function path(){
 const v=pathState(D,state.path);drawMolecule('molecule',v.xyz,{camera:{yaw:state.angle*Math.PI/180,tilt:.24},ghost:$('path-ghost').checked?D.molecule[0].xyz:null,measure:true,saved:v.saved});
 $('path-position').value=state.path;$('path-state').textContent=v.saved?'Saved image '+v.image+' of 9 · exact geometry from the reference CFG.':'Interpolated display geometry · not a calculated sample or molecular trajectory.';
 $('path-readouts').innerHTML=[['O1–H2',v.left,'Å'],['O8–H2',v.right,'Å'],['O1–O8',v.roo,'Å'],['qPT',v.q,'Å']].map(([k,x,u])=>'<div><span>'+k+'</span><strong>'+fmt(x)+' <small>'+u+'</small></strong></div>').join('');
 chart($('path-chart'),{series:[pointSeries('pbe','PBE')],height:230,activeX:v.q,activeIndex:v.saved?v.image-1:-1,xDomain:[-.52,.52],yDomain:[0,40],xTicks:[-.48,0,.48],xlabel:'qPT (Å)',ylabel:'PBE relative energy (meV)',label:'PBE energy linked to the displayed molecular geometry'});
}
function sample(t=progress.sampling){samplingPlot($('sampling-chart'),D.sampling,t);$('count-common').textContent=Math.round(36*clamp(t*3));$('count-basin').textContent=Math.round(24*clamp(t*3-1));$('count-targeted').textContent=Math.round(24*clamp(t*3-2));}
function energy(){
 const series=[pointSeries('pbe','PBE')];if($('show-basin').checked)series.push(pointSeries('basin','Basin60'));if($('show-targeted').checked)series.push(pointSeries('targeted','Targeted60'));
 const i=Math.round(state.energy),q=D.molecule[i].q;
 chart($('energy-chart'),{series,height:310,region:[-.15,.15],activeX:q,activeIndex:i,xDomain:[-.52,.52],yDomain:[-1,42],xlabel:'Proton coordinate qPT (Å)',ylabel:'Relative energy (meV)',label:'Original PBE, Basin60 and Targeted60 saved energy profiles',interactive:true,onSelect:n=>{stop();state.energy=n;energy();}});
 const res=series.filter(s=>s.key!=='pbe').map(s=>({...s,points:s.points.map(p=>({...p,y:D.residuals[s.name][p.index]}))}));
 if(res.length)chart($('energy-residual'),{series:res,height:200,activeX:q,activeIndex:i,xDomain:[-.52,.52],yDomain:[-40,5],reference:{value:0,label:'Zero error'},xlabel:'qPT (Å)',ylabel:'Relative-profile residual (meV)',label:'Residual after each series is referenced to its own lower endpoint'});else $('energy-residual').innerHTML='<p class="fine">Select a model to inspect its residual.</p>';
 $('energy-image').value=i;drawMolecule('energy',D.molecule[i].xyz,{camera:{yaw:-.18,tilt:.25},zoom:.9});$('energy-image-label').textContent='Image '+(i+1)+' · '+fmt(q,3)+' Å';
}
function seeds(t=progress.seeds){
 seedPlot($('seeds-chart'),D.seeds,state.metric,state.seed,t);
 const rows=D.seeds.filter(r=>r.index===state.seed),unit=state.metric==='barrier'?'meV':'eV/Å';
 $('seed-record').innerHTML='<p class="eyebrow">Selected pair '+(state.seed+1)+'</p>'+rows.map(r=>'<p><strong class="'+r.model+'">'+(r.model==='basin'?'Basin60':'Targeted60')+'</strong> '+fmt(r[state.metric],state.metric==='barrier'?5:7)+' '+unit+'</p>').join('')+'<p class="seed-id">64-bit seed: '+rows[0].seed+'</p>';
 for(const el of $('seeds-chart').querySelectorAll('[data-seed]')){const fn=()=>{state.seed=Number(el.dataset.seed);$('seed-pair').value=state.seed;seeds();};el.onclick=fn;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();fn();}};}
}
function replay(){const zoom=$('gamma-zoom').checked,pts=D.replay.filter(r=>!zoom||(r.index>=140&&r.index<=150));chart($('replay-chart'),{series:[{key:'pbe',name:'Saved gamma',line:false,r:zoom?4:2.6,points:pts.map(r=>({x:r.index,y:r.gamma,index:r.index,label:'Replay '+r.index}))}],height:350,xDomain:zoom?[140,150]:[1,228],yDomain:zoom?[.997,1.002]:[0,1.08],xTicks:zoom?[140,142,144,146,148,150]:[1,50,100,150,200,228],xFormat:x=>String(Math.round(x)),yFormat:x=>zoom?x.toFixed(4):x.toFixed(2),reference:{value:D.stop,label:zoom?'Frozen stop 1.0000013':'Frozen stop'},xlabel:'Saved archive index (not time)',ylabel:'MaxVol gamma (dimensionless)',label:'Replay228 saved coverage scores with unchanged historical stop'});}
function localRows(){return D.local.filter(r=>r.role===state.group);}
function diagnostic(){
 const rows=localRows();state.frame=clamp(state.frame,0,rows.length-1);const row=rows[state.frame];$('diagnostic-frame').max=rows.length-1;$('diagnostic-frame').value=state.frame;
 const xd=[rows[0].replay_index,rows.at(-1).replay_index],xx=rows.map(r=>r.replay_index),gammaDomain=state.group==='CROSSING7'?[.999,1.0015]:[.78,1.01];
 chart($('diagnostic-gamma'),{series:[{key:'train119',name:'Saved gamma',points:rows.map((r,i)=>({x:r.replay_index,y:r.gamma_saved,index:i}))}],activeX:row.replay_index,activeIndex:state.frame,height:270,xDomain:xd,yDomain:gammaDomain,xTicks:xx,xFormat:x=>String(Math.round(x)),yFormat:x=>x.toFixed(state.group==='CROSSING7'?4:2),reference:{value:D.stop,label:'Frozen stop'},xlabel:'Saved archive index',ylabel:'Gamma (dimensionless)',label:'Saved Train119 coverage grades for '+state.group,interactive:true,onSelect:i=>{stop();state.frame=i;diagnostic();}});
 chart($('diagnostic-force'),{series:[{key:'targeted',name:'Force RMSE',points:rows.map((r,i)=>({x:r.replay_index,y:r.force_component_RMSE_eV_A,index:i}))}],activeX:row.replay_index,activeIndex:state.frame,height:270,xDomain:xd,yDomain:[0,.105],xTicks:xx,xFormat:x=>String(Math.round(x)),yFormat:x=>x.toFixed(3),reference:{value:D.a2,label:'A2 = 0.09 eV/Å'},xlabel:'Saved archive index',ylabel:'Force-component RMSE (eV/Å)',label:'Reference force error and fixed A2 threshold',interactive:true,onSelect:i=>{stop();state.frame=i;diagnostic();}});
 $('diagnostic-record').innerHTML=[['Archive frame',row.replay_index,'100 K development data'],['Saved gamma',fmt(row.gamma_saved,9),row.above_stop?'Above frozen stop':'Below frozen stop'],['Force RMSE',fmt(row.force_component_RMSE_eV_A,6),'eV/Å · below A2'],['Historical status','Not promoted','STATIC_APPLICABILITY_FAIL']].map(([a,b,c])=>'<div><span>'+a+'</span><strong>'+b+'</strong><small>'+c+'</small></div>').join('');
 const s=pointSeries('train119','Train119');chart($('train119-energy'),{series:[pointSeries('pbe','PBE'),s],height:245,xDomain:[-.52,.52],yDomain:[0,40],xlabel:'qPT (Å)',ylabel:'Relative energy (meV)',label:'Separate Train119 development profile'});
 chart($('train119-residual'),{series:[{...s,points:s.points.map(p=>({...p,y:D.residuals.Train119[p.index]}))}],height:245,xDomain:[-.52,.52],yDomain:[-.6,.6],reference:{value:0,label:'Zero residual'},xlabel:'qPT (Å)',ylabel:'Train119 − PBE residual (meV)',label:'Train119 profile residual, distinct from barrier error'});
}
function force(){
 const f=D.force_frames[state.forceFrame],i=state.atom;drawMolecule('forces',f.xyz,{camera:{yaw:state.forceAngle*Math.PI/180,tilt:.34},selected:i,force:f,forceGain:state.forceGain,layer:state.forceLayer,reveal:state.forceReveal,zoom:.86});
 const err=f.difference[i];let table='<table><caption>Atom '+ATOMS[i]+' · source-frame components (eV/Å)</caption><thead><tr><th>Vector</th><th>x</th><th>y</th><th>z</th></tr></thead><tbody>';
 for(const [name,vec] of [['PBE',f.pbe[i]],['MTP',f.mtp[i]],['ΔF',err]])table+='<tr><td>'+name+'</td>'+vec.map(v=>'<td>'+fmt(v,5)+'</td>').join('')+'</tr>';
 table+='</tbody></table>';
 $('force-record').innerHTML='<p class="vector-summary">'+fmt(norm(err),5)+' <small>eV/Å</small></p><p class="fine">3-D error magnitude for '+ATOMS[i]+'. Configuration RMSE: '+fmt(f.rmse,6)+' eV/Å.</p>'+table;
 $('force-source').href=f.source;$('forces-canvas').dataset.frame=String(f.index);$('forces-canvas').dataset.selectedAtom=ATOMS[i];
}
const acts=[
 ['01 / THE QUESTION','Where should a potential learn?','A hydrogen atom changes sides while the oxygen bridge contracts. Which geometries should a limited DFT budget describe?','molecule'],
 ['02 / THE DATA','Thirty-six shared.<br>Twenty-four different.','The original comparison holds the data count and architecture fixed. Only the placement of the additions changes.','sampling'],
 ['03 / THE FIRST RESULT','A convincing static fit.','In the original locked pair, the barrier error falls from 35.25 to 4.10 meV. That is an artifact-specific result.','landscape'],
 ['04 / THE REPETITION','The ordering is not guaranteed.','Across five paired seeds, targeted wins both metrics in three pairs. All outcomes remain visible.','seeds'],
 ['05 / THE WARNING','Two criteria. Two verdicts.','Five saved coverage grades cross their stop, while the selected local PBE force errors remain below A2.','train119'],
 ['06 / THE CONCLUSION','A better fit is not<br>the final test.','Repeatability, coverage, independent evaluation and the physical reference ask different questions. The historical failure remains.','reproduce']];
function journey(t=0){const act=Math.min(5,Math.floor(t*6)),u=clamp(t*6-act),a=acts[act];$('journey-step').textContent=a[0];$('journey-title').innerHTML=a[1];$('journey-copy').textContent=a[2];$('journey-link').href='#'+a[3];for(const b of $$('[data-act]'))b.setAttribute('aria-current',Number(b.dataset.act)===act?'step':'false');
 const box=$('journey-chart'),mol=$('journey-molecule');mol.style.display=act===0||act===5?'block':'none';box.style.display=act===0||act===5?'none':'block';
 if(act===0||act===5){const p=act===0?8*smooth(u):4;drawMolecule('journey',pathState(D,p).xyz,{camera:{yaw:-.32+.4*u,tilt:.35},measure:true,zoom:1.02,saved:Number.isInteger(p)});}
 if(act===1)samplingPlot(box,D.sampling,clamp(u*1.22));
 if(act===2)chart(box,{series:[pointSeries('pbe','PBE'),pointSeries('basin','Basin60'),pointSeries('targeted','Targeted60')],height:350,xDomain:[-.52,.52],yDomain:[-1,42],activeIndex:Math.min(8,Math.floor(u*9)),xlabel:'qPT (Å)',ylabel:'Relative energy (meV)',label:'Original three-series comparison',reveal:clamp(u*1.4)});
 if(act===3)seedPlot(box,D.seeds,'barrier',Math.min(4,Math.floor(u*5)),clamp(u*1.15));
 if(act===4){box.innerHTML='<div id="journey-gamma"></div><div id="journey-rmse"></div>';const rows=D.local.filter(r=>r.role==='CROSSING7'),i=Math.min(6,Math.floor(u*7));for(const [id,key,domain,ref,ylabel] of [['journey-gamma','gamma_saved',[.999,1.0015],D.stop,'Saved gamma'],['journey-rmse','force_component_RMSE_eV_A',[0,.105],D.a2,'Force RMSE (eV/Å)']])chart($(id),{series:[{key:id==='journey-gamma'?'train119':'targeted',name:ylabel,points:rows.map((r,j)=>({x:r.replay_index,y:r[key],index:j}))}],height:180,activeIndex:i,activeX:rows[i].replay_index,xDomain:[142,148],xTicks:[142,145,148],xFormat:x=>String(x),yFormat:x=>id==='journey-gamma'?x.toFixed(4):x.toFixed(3),yDomain:domain,reference:{value:ref,label:id==='journey-gamma'?'Frozen stop':'A2'},xlabel:'Archive index',ylabel,label: ylabel+' for the same selected frames'});}
}
function seek(name,t){t=clamp(t);progress[name]=t;if($('progress-'+name))$('progress-'+name).value=Math.round(t*1000);
 switch(name){case 'hero':{const s=sceneState('hero',t);hero(s.position,{yaw:s.yaw,tilt:s.tilt});break;}case 'molecule':{const s=sceneState('path',t);state.path=s.position;path();break;}case 'sampling':sample(t);break;case 'landscape':state.energy=Math.min(8,Math.floor(t*9));energy();break;case 'seeds':seeds(t);break;case 'train119':state.frame=Math.min(localRows().length-1,Math.floor(t*localRows().length));diagnostic();break;case 'forces':state.forceReveal=t;force();break;case 'story':journey(t);break;}
}
function stop(){if(running){pressed('play-'+running.name,false);const el=$('play-'+running.name);if(el)el.innerHTML=el.dataset.original;}cancelAnimationFrame(raf);raf=0;running=null;}
function play(name){if(running?.name===name){stop();return;}stop();if(reduced.matches){seek(name,1);return;}let t=progress[name];if(t>=1)t=0;running={name,start:performance.now()-t*durations[name]};const b=$('play-'+name);b.innerHTML='Ⅱ Pause';pressed('play-'+name,true);const tick=now=>{if(!running)return;if(document.hidden){stop();return;}const t=clamp((now-running.start)/durations[name]);seek(name,t);if(t>=1){stop();return;}raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);}
function reset(name){stop();seek(name,0);}
function redraw(){switch(active){case'overview':hero(lastHero.position,lastHero.camera);break;case'molecule':path();break;case'sampling':sample();break;case'landscape':energy();break;case'seeds':seeds();break;case'applicability':replay();break;case'train119':diagnostic();break;case'forces':force();break;case'story':journey(progress.story);break;}}
function navigate(){stop();active=route(location.hash);for(const p of $$('.page')){p.classList.toggle('active',p.id===active);if(p.id===active)p.removeAttribute('aria-hidden');else p.setAttribute('aria-hidden','true');}for(const a of $$('nav [data-route]')){if(a.dataset.route===active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');}document.body.dataset.page=active;redraw();window.scrollTo({top:0,behavior:'instant'});}
function theme(){const dark=document.documentElement.dataset.theme!=='dark';document.documentElement.dataset.theme=dark?'dark':'light';try{localStorage.setItem('proton-theme',dark?'dark':'light');}catch{}$('theme-toggle').textContent=dark?'Light theme':'Dark theme';redraw();}
async function init(){
 try{const theme=localStorage.getItem('proton-theme');if(theme==='dark')document.documentElement.dataset.theme='dark';}catch{}
 $('theme-toggle').textContent=document.documentElement.dataset.theme==='dark'?'Light theme':'Dark theme';
 const response=await fetch('data/science.json');if(!response.ok)throw Error('The scientific dataset did not load.');D=await response.json();if(!finiteTree(D)||D.molecule.length!==9||D.force_frames.length!==11)throw Error('Unexpected scientific data schema.');
 for(const id of ['hero','molecule','energy','forces','journey'])views[id]=new MoleculeView($(id+'-canvas'));
 for(const name of Object.keys(durations)){const b=$('play-'+name);if(b){b.dataset.original=b.innerHTML;b.onclick=()=>play(name);}$('reset-'+name)?.addEventListener('click',()=>reset(name));$('progress-'+name)?.addEventListener('input',e=>{stop();seek(name,Number(e.target.value)/1000);});}
 $('path-position').oninput=e=>{stop();state.path=Number(e.target.value);path();};$('path-angle').oninput=e=>{state.angle=Number(e.target.value);path();};$('path-ghost').onchange=path;
 $('path-prev').onclick=()=>{stop();state.path=clamp(Math.ceil(state.path)-1,0,8);path();};$('path-next').onclick=()=>{stop();state.path=clamp(Math.floor(state.path)+1,0,8);path();};
 $('energy-image').oninput=e=>{stop();state.energy=Number(e.target.value);energy();};$('show-basin').onchange=energy;$('show-targeted').onchange=energy;
 $('seed-metric').onchange=e=>{state.metric=e.target.value;seeds();};$('seed-pair').onchange=e=>{state.seed=Number(e.target.value);seeds();};$('gamma-zoom').onchange=replay;
 $('diagnostic-group').onchange=e=>{stop();state.group=e.target.value;state.frame=0;diagnostic();};$('diagnostic-frame').oninput=e=>{stop();state.frame=Number(e.target.value);diagnostic();};
 $('force-frame').onchange=e=>{stop();state.forceFrame=Number(e.target.value);state.forceReveal=1;force();};$('force-atom').onchange=e=>{state.atom=Number(e.target.value);force();};$('force-angle').oninput=e=>{state.forceAngle=Number(e.target.value);force();};$('force-gain').oninput=e=>{state.forceGain=Number(e.target.value);force();};$('force-layer').onchange=e=>{state.forceLayer=e.target.value;force();};
 $('forces-canvas').onclick=e=>{const r=e.currentTarget.getBoundingClientRect(),i=views.forces.pick(e.clientX-r.left,e.clientY-r.top);if(i!==null){state.atom=i;$('force-atom').value=i;force();}};
 for(const b of $$('[data-act]'))b.onclick=()=>{stop();seek('story',Number(b.dataset.act)/6+.015);};
 $('theme-toggle').onclick=theme;window.addEventListener('hashchange',navigate);document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});reduced.addEventListener('change',()=>{stop();redraw();});
 let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(redraw,90);});
 for(const [k,v] of Object.entries(progress))if($('progress-'+k))$('progress-'+k).value=Math.round(v*1000);
 document.body.classList.add('enhanced');if(new URLSearchParams(location.search).has('capture'))document.body.classList.add('capture');navigate();
 window.__proton={ready:true,data:D,state,seek:(name,t)=>{stop();seek(name,t);},stop,playing:()=>running?.name||null,geometry,redraw,version:'english-cinematic-v2'};
 // New English previews are optional, and are never fetched just to start the scene.
 fetch('cinema/manifest.json').then(r=>r.ok?r.json():null).then(a=>{if(!a||!Array.isArray(a.films)||!a.films.length)return;$('cinema-downloads').innerHTML='<div class="section-intro"><p class="eyebrow">English cinematic previews</p><h2>Watch, then take control.</h2><p>Deterministically rendered from the same saved data. Screen time is not reaction time.</p></div><div class="cinema-grid">'+a.films.map(v=>'<figure><video controls preload="none" playsinline poster="cinema/'+v.poster+'" aria-label="'+v.title+'"><source src="cinema/'+v.file+'" type="video/mp4"></video><figcaption>'+v.title+' · '+v.seconds+' s · '+v.fps+' fps<br><a href="cinema/'+v.file+'" download>Download MP4 ↓</a></figcaption></figure>').join('')+'</div>';}).catch(()=>{});
}
init().catch(e=>{$('load-error').hidden=false;$('load-error').textContent='Interactive data are unavailable: '+e.message+' The English article, saved tables and source links remain readable below.';document.body.classList.remove('enhanced');console.error(e);});
