/* English research exhibit. All animations are finite presentations of saved data. */
import {ATOMS,ROUTES,clamp,pathState,pairedSeeds,route,journeyState,norm,finite} from './core.mjs';
import {MolecularStage} from './molecule.mjs';
import {linePlot,samplingPlot,seedPlot,diagnosticPlots,colors} from './charts.mjs';
const $=id=>document.getElementById(id);
const reduce=matchMedia('(prefers-reduced-motion: reduce)');
const state={route:route(location.hash),hero:4,path:4,sampling:1,energy:1,energyImage:4,models:{Basin60:true,Targeted60:true},seeds:1,seed:'all',frame:145,group:'CROSSING7',atom:1,scale:2,vectors:{pbe:true,mtp:true,error:true},story:0};
const stages=new Map(),charts={};let data=null,motion=null,raf=0,lastStoryChapter=-1,userAction=false;
const stats={intervals:[],work:[],frames:0};
const buttons={hero:'hero-play',path:'path-play',sampling:'sampling-play',energy:'energy-play',seeds:'seeds-play',diagnostic:'diagnostic-play',forces:'forces-play',story:'story-play'};
const labels={hero:'▷ Play',path:'▷ Play path',sampling:'▷ Reveal the experiment',energy:'▷ Reveal the profiles',seeds:'▷ Reveal the five pairs',diagnostic:'▷ Follow the frames',forces:'▷ Reveal the vectors',story:'▷ Play the story'};
const text=(id,value)=>{const n=$(id);if(n)n.textContent=value;};
function stage(id,xyz,options={}){if(!stages.has(id))stages.set(id,new MolecularStage($(id),xyz,options));return stages.get(id);}
function ensureRendererResize(){for(const [id,s]of stages)if($(id).getClientRects().length)s.resize();}
function fmt(v,n=3){return Math.abs(v)<.5*10**(-n)?(0).toFixed(n):v.toFixed(n);}
function datum(i){return data.forces.find(f=>f.index===Number(i));}
function profiles(names){return names.map(name=>({name,values:data.molecule.map((m,i)=>({x:m.q,y:data.profiles[name][i],image:i}))}));}
function stop(){if(raf)cancelAnimationFrame(raf);raf=0;motion=null;for(const[k,id]of Object.entries(buttons)){text(id,labels[k]);$(id)?.setAttribute('aria-pressed','false');}}
function play(key,duration,update,start=0){
  userAction=true;if(motion?.key===key){stop();return;}stop();
  motion={key,duration,update,start:clamp(start,0,1),t0:performance.now(),last:0};text(buttons[key],'Ⅱ Pause');$(buttons[key]).setAttribute('aria-pressed','true');
  function tick(now){if(!motion||document.hidden)return;const m=motion,before=performance.now();
    if(m.last){stats.intervals.push(now-m.last);if(stats.intervals.length>600)stats.intervals.shift();}m.last=now;
    const t=clamp(m.start+(now-m.t0)/duration,0,1);m.update(t);stats.frames++;stats.work.push(performance.now()-before);if(stats.work.length>600)stats.work.shift();
    if(t>=1)stop();else raf=requestAnimationFrame(tick);
  }
  raf=requestAnimationFrame(tick);
}
function hero(t){state.hero=clamp(t,0,8);const p=pathState(data.molecule,data.profiles.PBE,state.hero);const s=stage('hero-molecule',p.xyz,{compact:true});s.update(p.xyz);s.setView(-.38+.14*(state.hero/8),.23,.65);$('hero-slider').value=state.hero;text('hero-roo',fmt(p.roo,3));text('hero-q',fmt(p.q,3));text('hero-frame',p.saved?`PBE IMAGE ${String(p.image).padStart(2,'0')} / 09`:`DISPLAY INTERPOLATION ${p.between[0]} → ${p.between[1]}`);}
function molecularPath(t){state.path=clamp(t,0,8);if($('path-snap').checked)state.path=Math.round(state.path);const p=pathState(data.molecule,data.profiles.PBE,state.path);stage('path-molecule',p.xyz).update(p.xyz);$('path-slider').value=state.path;text('path-left',fmt(p.left,4));text('path-right',fmt(p.right,4));text('path-roo',fmt(p.roo,4));text('path-energy',fmt(p.energy,3));text('path-state',p.saved?`Saved image ${p.image} / 9`:`Interpolated ${p.between[0]} → ${p.between[1]}`);document.querySelectorAll('[data-image]').forEach(b=>b.setAttribute('aria-pressed',String(p.saved&&Number(b.dataset.image)===p.image-1)));charts.path?.cursor(p.q,{PBE:p.energy});}
function sampling(t){state.sampling=clamp(t,0,1);const c=charts.samplingB?.reveal(t);charts.samplingT?.reveal(t);if(c)text('sampling-count',t===1?'36 shared + 24 added per model':`Revealed: ${c.shared} / 36 shared · ${c.added} / 24 added`);}
function energy(t){state.energy=clamp(t,0,1);charts.energy?.reveal(t);charts.residual?.reveal(t);}
function selectedEnergy(i){state.energyImage=clamp(Math.round(i),0,8);$('energy-image').value=state.energyImage;const q=data.molecule[state.energyImage].q;charts.energy?.cursor(q);charts.residual?.cursor(q);const names=['PBE',...Object.keys(state.models).filter(k=>state.models[k])];text('energy-readout',`Image ${state.energyImage+1} · qPT ${fmt(q,4)} Å · `+names.map(k=>`${k}: ${fmt(data.profiles[k][state.energyImage],4)} meV`).join(' · '));}
function seedReveal(t){state.seeds=clamp(t,0,1);charts.seedB?.reveal(t);charts.seedF?.reveal(t);}
function seedSelection(id){state.seed=id;$('seed-select').value=id;charts.seedB?.select(id);charts.seedF?.select(id);if(id==='all')text('seed-description','One pair reverses both results; another has a mixed ordering.');else{const p=pairedSeeds(data.seeds)[Number(id)];text('seed-description',`Pair ${p.index+1} · seed ${p.seed}. `+(p.both?'Targeted is lower on both primary errors.':p.targeted.barrier>p.basin.barrier&&p.targeted.force>p.basin.force?'Basin is lower on both primary errors.':'The ordering differs between the two metrics.'));}}
function renderDiagnostics(){const rows=data.forces.filter(f=>f.group===state.group);charts.diagnostics=diagnosticPlots($('gamma-chart'),$('force-error-chart'),rows,data.stop,data.a2,p=>{stop();diagnosticFrame(p.index);});}
function diagnosticFrame(index){const f=datum(index);if(!f)throw new Error('Unknown saved diagnostic frame');state.frame=f.index;if(f.group!==state.group){state.group=f.group;$('diagnostic-group').value=state.group;renderDiagnostics();}charts.diagnostics?.select(f.index);$('diagnostic-frame').value=f.index;
  const r=$('diagnostic-readout');r.replaceChildren();
  for(const [label,value] of [['Saved frame',String(f.index)],['Gamma',f.gamma.toFixed(12)],['Force RMSE',f.rmse.toFixed(6)+' eV/Å']]){const s=document.createElement('span');s.append(label+' ');const b=document.createElement('strong');b.textContent=value;s.append(b);r.append(s);}
  const verdict=document.createElement('span');verdict.className='verdict';verdict.textContent=f.gamma>data.stop?'Coverage crossing · local A2 satisfied':'Below stop · local A2 satisfied';r.append(verdict);$('inspect-forces-link').href=`#forces?frame=${f.index}&atom=1`;
}
function forceFrame(index=state.frame,atom=state.atom){const f=datum(index);if(!f)throw new Error('Unknown force frame');state.frame=f.index;state.atom=clamp(Math.round(atom),0,8);$('force-frame').value=f.index;
  const s=stage('force-molecule',f.xyz,{onSelect:i=>{stop();forceFrame(state.frame,i);}});s.update(f.xyz,{selected:state.atom,forces:f,scale:state.scale,layers:state.vectors});
  document.querySelectorAll('[data-atom]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.atom)===state.atom)));
  text('force-atom-badge',ATOMS[state.atom]);text('force-selection',`${ATOMS[state.atom]} · Replay ${f.index}`);
  const values=[['PBE',f.pbe[state.atom]],['MTP',f.mtp[state.atom]],['ΔF',f.error[state.atom]]];
  const table=document.createElement('table');table.innerHTML='<caption>Original laboratory components / eV/Å</caption><thead><tr><th scope="col">Force</th><th scope="col">x</th><th scope="col">y</th><th scope="col">z</th></tr></thead>';
  const body=document.createElement('tbody');for(const [label,row] of values){const tr=document.createElement('tr');for(const val of [label,...row.map(x=>fmt(x,5))]){const td=document.createElement('td');td.textContent=val;tr.append(td);}body.append(tr);}table.append(body);$('force-components').replaceChildren(table);
  text('selected-error',fmt(norm(f.error[state.atom]),5));text('selected-rmse',fmt(f.rmse,5));const a=document.createElement('a');a.href=data.evidence[f.source_key].url;a.textContent=`Inspect the original QE force block for frame ${f.index} ↗`;$('force-source').replaceChildren(a);
}
function forceReveal(t){const f=datum(state.frame),phase=t*3;const layers={pbe:phase>.05,mtp:phase>1,error:phase>2};if(t===1)Object.assign(layers,state.vectors);stage('force-molecule',f.xyz).update(f.xyz,{selected:state.atom,forces:f,scale:state.scale,layers});}
function renderTrainProfile(){charts.trainProfile=linePlot($('train119-profile'),{series:profiles(['PBE','Train119']),yLabel:'Development profiles / meV'});charts.trainResidual=linePlot($('train119-residual'),{series:[{name:'Train119',values:data.molecule.map((m,i)=>({x:m.q,y:data.residuals.Train119[i]}))}],yLabel:'Relative profile residual / meV',thresholds:[{value:0,label:'PBE reference',color:'var(--muted)'}]});}
function story(t){state.story=clamp(t,0,1);const j=journeyState(state.story);$('story-slider').value=state.story;text('story-count',`${String(j.chapter+1).padStart(2,'0')} / 06`);text('story-title',j.title);text('story-caption',j.caption);text('story-kicker',['THE MOVING SCAFFOLD','THE TRAINING GEOMETRIES','THE ORIGINAL FROZEN PAIR','TRAINING RANDOMNESS','LOCAL DEVELOPMENT EVIDENCE','THE SCIENTIFIC BOUNDARY'][j.chapter]);$('story-link').href='#'+j.route;
  document.querySelectorAll('[data-chapter]').forEach(b=>{if(Number(b.dataset.chapter)===j.chapter)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
  const showMol=[0,5].includes(j.chapter);$('story-molecule').style.display=showMol?'block':'none';$('story-chart').style.display=showMol?'none':'block';
  if(showMol){const p=pathState(data.molecule,data.profiles.PBE,j.chapter===0?j.path:4);const s=stage('story-molecule',p.xyz);if(lastStoryChapter!==j.chapter)s.resize();s.update(p.xyz);s.setView(-.45+.45*j.local,.22,.65);}
  if(lastStoryChapter!==j.chapter){lastStoryChapter=j.chapter;charts.story=null;if(j.chapter===1){const all=[...data.sampling.basin,...data.sampling.targeted];const domain=samplingDomain(all);const combined=[...data.sampling.basin.map(p=>({...p,branch:'basin'})),...data.sampling.targeted.filter(p=>!p.shared).map(p=>({...p,branch:'targeted'}))];charts.story=samplingPlot($('story-chart'),combined,'both',domain);}if(j.chapter===2)charts.story=linePlot($('story-chart'),{series:profiles(['PBE','Basin60','Targeted60']),height:360});if(j.chapter===3)charts.story=seedPlot($('story-chart'),data.seeds,'barrier');if(j.chapter===4){const fs=data.forces.filter(f=>f.group==='CROSSING7');charts.story=linePlot($('story-chart'),{series:[{name:'Force RMSE',color:'var(--targeted)',values:fs.map(f=>({x:f.index,y:f.rmse}))}],xLabel:'Saved Replay228 frame',yLabel:'Force-component RMSE / eV/Å',yDomain:[0,.1],thresholds:[{value:data.a2,label:'A2 = 0.09'}],height:360});}}
  text('story-progress-label',j.chapter===0?`qPT ${fmt(pathState(data.molecule,data.profiles.PBE,j.path).q,3)} Å · O–O ${fmt(pathState(data.molecule,data.profiles.PBE,j.path).roo,3)} Å · DISPLAY INTERPOLATION`:j.chapter===1?'GRAY: 36 SHARED · RUST: 24 BASIN · TEAL: 24 TARGETED':'GEOMETRY / DATA / ROBUSTNESS / COVERAGE');
  charts.story?.reveal(clamp(j.local*1.8,0,1));if(j.chapter===4)charts.story?.cursor(142+Math.min(6,Math.floor(7*j.local)));
}
function samplingDomain(all){const q=all.map(p=>p.q),r=all.map(p=>p.roo),dx=Math.max(...q)-Math.min(...q),dy=Math.max(...r)-Math.min(...r);return{x:[Math.min(...q)-dx*.06,Math.max(...q)+dx*.06],y:[Math.min(...r)-dy*.08,Math.max(...r)+dy*.08]};}
function drawActive(){
  const r=state.route;
  if(r==='overview')hero(state.hero);
  if(r==='molecule'){charts.path=linePlot($('path-chart'),{series:profiles(['PBE']),height:205,yLabel:'Relative PBE energy / meV'});molecularPath(state.path);}
  if(r==='sampling'){const domain=samplingDomain([...data.sampling.basin,...data.sampling.targeted]);charts.samplingB=samplingPlot($('sampling-basin'),data.sampling.basin,'basin',domain);charts.samplingT=samplingPlot($('sampling-targeted'),data.sampling.targeted,'targeted',domain);sampling(state.sampling);}
  if(r==='landscape'){const names=['PBE',...Object.keys(state.models).filter(k=>state.models[k])];charts.energy=linePlot($('energy-chart'),{series:profiles(names),onPoint:p=>{stop();selectedEnergy(p.image);}});charts.residual=linePlot($('energy-residual'),{series:names.filter(k=>k!=='PBE').length?names.filter(k=>k!=='PBE').map(name=>({name,values:data.molecule.map((m,i)=>({x:m.q,y:data.residuals[name][i],image:i}))})):[{name:'PBE',values:data.molecule.map(m=>({x:m.q,y:0}))}],yLabel:'Model − PBE relative profile / meV',height:235,thresholds:[{value:0,label:'PBE reference',color:'var(--muted)'}]});energy(state.energy);selectedEnergy(state.energyImage);}
  if(r==='seeds'){charts.seedB=seedPlot($('seeds-barrier'),data.seeds,'barrier');charts.seedF=seedPlot($('seeds-force'),data.seeds,'force');seedReveal(state.seeds);seedSelection(state.seed);}
  if(r==='train119'){renderDiagnostics();diagnosticFrame(state.frame);if(document.querySelector('.sub-study').open)renderTrainProfile();}
  if(r==='forces')forceFrame();
  if(r==='story'){lastStoryChapter=-1;story(state.story);}
  ensureRendererResize();
}
function navigate(){if(!data)return;stop();userAction=true;state.route=route(location.hash);const params=new URLSearchParams(location.hash.split('?')[1]||'');if(params.has('frame')&&datum(params.get('frame')))state.frame=Number(params.get('frame'));if(params.has('atom'))state.atom=clamp(Number(params.get('atom'))||0,0,8);
  document.querySelectorAll('[data-page]').forEach(p=>p.classList.toggle('active',p.id===state.route));document.querySelectorAll('[data-route]').forEach(a=>{if(a.dataset.route===state.route)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});drawActive();
  if(location.hash.startsWith('#read-'))setTimeout(()=>$(location.hash.slice(1))?.scrollIntoView({behavior:'auto',block:'start'}),0);else window.scrollTo({top:0,behavior:'auto'});
}
function theme(){const dark=document.documentElement.dataset.theme==='dark';text('theme',dark?'Light mode':'Dark mode');$('theme').setAttribute('aria-label',dark?'Switch to light theme':'Switch to dark theme');for(const s of stages.values())s.setTheme(dark);}
function bind(){
  document.addEventListener('pointerdown',()=>{userAction=true;},{passive:true});
  const event=(id,kind,fn)=>$(id).addEventListener(kind,fn);
  event('theme','click',()=>{const dark=document.documentElement.dataset.theme!=='dark';document.documentElement.dataset.theme=dark?'dark':'light';try{localStorage.setItem('proton-theme',dark?'dark':'light');}catch{}theme();});
  event('hero-play','click',()=>play('hero',14000,t=>hero(t*8),state.hero>=8?0:state.hero/8));event('hero-slider','input',e=>{stop();hero(+e.target.value);});event('hero-reset','click',()=>{stop();hero(0);});
  event('path-play','click',()=>play('path',16000,t=>molecularPath(t*8),state.path>=8?0:state.path/8));event('path-slider','input',e=>{stop();molecularPath(+e.target.value);});event('path-snap','change',()=>{stop();molecularPath(state.path);});event('path-reset','click',()=>{stop();stage('path-molecule',data.molecule[0].xyz).resetView();molecularPath(0);});event('path-front','click',()=>{stop();stage('path-molecule',data.molecule[0].xyz).setView(0,0,.65);});event('path-studio','click',()=>stage('path-molecule',data.molecule[0].xyz).resetView());
  document.querySelectorAll('[data-image]').forEach(b=>b.addEventListener('click',()=>{stop();molecularPath(+b.dataset.image);}));
  event('sampling-play','click',()=>play('sampling',8000,sampling,state.sampling>=1?0:state.sampling));event('sampling-reset','click',()=>{stop();sampling(1);});
  event('energy-play','click',()=>play('energy',6500,energy,state.energy>=1?0:state.energy));event('energy-image','input',e=>{stop();selectedEnergy(+e.target.value);});document.querySelectorAll('[data-model]').forEach(b=>b.addEventListener('change',()=>{stop();state.models[b.dataset.model]=b.checked;drawActive();}));
  event('seeds-play','click',()=>play('seeds',10000,seedReveal,state.seeds>=1?0:state.seeds));event('seeds-all','click',()=>{stop();seedReveal(1);});event('seed-select','change',e=>seedSelection(e.target.value));
  event('diagnostic-group','change',e=>{stop();state.group=e.target.value;diagnosticFrame(data.forces.find(f=>f.group===state.group).index);renderDiagnostics();diagnosticFrame(state.frame);});event('diagnostic-frame','change',e=>{stop();diagnosticFrame(+e.target.value);});event('diagnostic-play','click',()=>{const frames=data.forces.filter(f=>f.group===state.group);let previous=-1;play('diagnostic',frames.length*1100,t=>{const i=Math.min(frames.length-1,Math.floor(t*frames.length));if(i!==previous){previous=i;diagnosticFrame(frames[i].index);}});});
  document.querySelector('.sub-study').addEventListener('toggle',e=>{if(e.target.open&&state.route==='train119')renderTrainProfile();});
  event('force-frame','change',e=>{stop();forceFrame(+e.target.value);});document.querySelectorAll('[data-atom]').forEach(b=>b.addEventListener('click',()=>{stop();forceFrame(state.frame,+b.dataset.atom);}));event('force-scale','change',e=>{stop();state.scale=+e.target.value;forceFrame();});document.querySelectorAll('[data-vector]').forEach(b=>b.addEventListener('change',()=>{stop();state.vectors[b.dataset.vector]=b.checked;forceFrame();}));event('force-reset','click',()=>stage('force-molecule',datum(state.frame).xyz).resetView());event('forces-play','click',()=>play('forces',7200,forceReveal));
  event('story-play','click',()=>play('story',30000,story,state.story>=1?0:state.story));event('story-slider','input',e=>{stop();story(+e.target.value);});event('story-reset','click',()=>{stop();story(0);});document.querySelectorAll('[data-chapter]').forEach(b=>b.addEventListener('click',()=>{stop();story(+b.dataset.chapter/6);}));
  window.addEventListener('hashchange',navigate);let timer;window.addEventListener('resize',()=>{clearTimeout(timer);timer=setTimeout(()=>{stop();drawActive();},140);});document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});reduce.addEventListener('change',()=>{if(reduce.matches)stop();});
}
function films(){const area=$('film-area');if(!data.films?.length)return;const h=document.createElement('h2');h.textContent='English cinematic editions';const wrap=document.createElement('div');wrap.className='film-grid';for(const film of data.films){const fig=document.createElement('figure'),v=document.createElement('video');v.controls=true;v.preload='none';v.playsInline=true;v.poster=film.poster;v.setAttribute('aria-label',film.title);const source=document.createElement('source');source.src=film.file;source.type='video/mp4';v.append(source);if(film.captions){const track=document.createElement('track');track.kind='captions';track.srclang='en';track.label='English scene descriptions';track.src=film.captions;v.append(track);}const cap=document.createElement('figcaption');cap.textContent=film.title+'. '+film.scope;fig.append(v,cap);wrap.append(fig);}area.append(h,wrap);}

try{
  try{const saved=localStorage.getItem('proton-theme');if(saved==='dark')document.documentElement.dataset.theme='dark';}catch{}theme();
  const response=await fetch('data/science.json');if(!response.ok)throw new Error(`Data request returned ${response.status}`);data=await response.json();if(data.schema!=='proton-potential-cinematic-v2'||data.molecule.length!==9||data.forces.length!==11)throw new Error('Unexpected scientific payload');
  document.documentElement.classList.add('js-ready');bind();films();navigate();userAction=false;document.body.dataset.ready='true';
  window.exhibit={getState:()=>({...state,motion:motion?.key||null}),stop,seek:(key,t)=>{stop();finite(t);({hero,path:molecularPath,sampling,energy,seeds:seedReveal,story})[key]?.(t);},setFrame:(index,atom=1)=>{stop();if(state.route==='forces')forceFrame(index,atom);else diagnosticFrame(index);},renderers:()=>Object.fromEntries([...stages].map(([k,s])=>[k,s.el.dataset.renderer])),stats:()=>JSON.parse(JSON.stringify(stats)),science:()=>data};
  // One finite introduction, never an endless loop. Users can pause it immediately.
  if(!reduce.matches&&state.route==='overview'&&!new URLSearchParams(location.search).has('still'))setTimeout(()=>{if(!userAction&&state.route==='overview'&&!document.hidden){hero(0);play('hero',14000,t=>hero(t*8));}},700);
}catch(error){stop();document.documentElement.classList.remove('js-ready');const box=$('load-error');box.hidden=false;box.textContent='Interactive data could not be loaded. The complete English text, source links and tables are still available below. '+error.message;document.body.dataset.ready='error';}
