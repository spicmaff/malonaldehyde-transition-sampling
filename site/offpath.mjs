/* A new, namespaced chapter. No live model calls, no edits to old scene state. */
import {MolecularStage} from './molecule.mjs';
import {clamp} from './core.mjs';
const $=id=>document.getElementById(id);
const NS='http://www.w3.org/2000/svg';
const modes=['OO_breathing','C_skeletal_bend','H_lateral','H_out_of_plane'];
const names={'OO_breathing':'O–O breathing','C_skeletal_bend':'Carbon skeletal bend','H_lateral':'Lateral hydrogen','H_out_of_plane':'Out-of-plane hydrogen'};
const reduce=matchMedia('(prefers-reduced-motion: reduce)');
let payload=null,stage=null,animation=null,raf=0,started=false,progress=1;
const svg=(tag,attributes={},text=null)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attributes))n.setAttribute(k,String(v));if(text!==null)n.textContent=text;return n;};
const signed=(x,n=6)=>(x>=0?'+':'−')+Math.abs(x).toFixed(n);
const active=()=>$('offpath')?.classList.contains('active');
const mean=rows=>rows.reduce((s,r)=>s+r.force_RMSE_eV_A,0)/rows.length;
function validNumber(x){if(!Number.isFinite(x))throw new Error('Non-finite off-path number');return x;}
function primary(){
 const el=$('off-primary-chart'),w=Math.max(220,el.getBoundingClientRect().width),h=330,l=w<430?48:65,r=w<430?75:95,lo=-.52,hi=.18;
 const x=v=>l+(v-lo)/(hi-lo)*(w-l-r),g=svg('svg',{viewBox:`0 0 ${w} ${h}`,role:'img','aria-label':'All five signed primary contrasts, Targeted minus Basin, transition cap8000, eV/Å'});
 g.append(svg('title',{},'Negative favors Targeted; every prescribed seed is retained'));
 for(const t of (w<430?[-.5,0,.1]:[-.5,-.4,-.3,-.2,-.1,0,.1])){
  g.append(svg('line',{x1:x(t),x2:x(t),y1:31,y2:270,class:'off-grid'}));
  g.append(svg('text',{x:x(t),y:291,'text-anchor':'middle',class:'off-svg-axis'},String(t)));
 }
 g.append(svg('line',{x1:x(0),x2:x(0),y1:25,y2:270,class:'off-zero'}));
 for(const [i,row] of payload.benchmark.primary.contrasts.entries()){
  const value=validNumber(row.targeted_minus_basin_eV_A),yy=55+i*46,xx=x(value),group=svg('g',{class:'off-seed-mark '+(value<0?'targeted':'basin'),'data-off-seed':row.seed_index});
  group.append(svg('title',{},`Seed ${row.seed_index} / ${row.seed_u64}: ${signed(value,10)} eV/Å`));
  group.append(svg('text',{x:0,y:yy+4,class:'off-svg-axis'},`Seed ${row.seed_index}`));
  group.append(svg('line',{x1:x(0),x2:xx,y1:yy,y2:yy,class:'off-contrast-line'}));
  group.append(value<0?svg('path',{d:`M${xx} ${yy-5}l5 5 -5 5 -5 -5Z`}):svg('circle',{cx:xx,cy:yy,r:5}));
  group.append(svg('text',{x:w-1,y:yy+4,'text-anchor':'end',class:'off-svg-value'},signed(value,w<330?5:6)));
  g.append(group);
 }
 g.append(svg('text',{x:l,y:321,class:'off-svg-axis'},'← Targeted lower'));
 if(w>390)g.append(svg('text',{x:w-r,y:321,'text-anchor':'end',class:'off-svg-axis'},'Basin lower →'));
 el.replaceChildren(g);reveal(progress);
}
function reveal(t){
 progress=clamp(validNumber(t),0,1);$('off-progress').value=progress;
 document.querySelectorAll('#off-primary-chart [data-off-seed]').forEach((n,i)=>n.style.opacity=String(clamp(progress*5-i,0,1)));
 $('off-reveal-status').textContent=progress===1?'All five pairs visible':`${Math.min(5,Math.floor(progress*5))} of 5 pairs revealed; complete values stay in the table`;
}
function stop(){if(raf)cancelAnimationFrame(raf);raf=0;animation=null;$('off-reveal').textContent='▷ Reveal five pairs';$('off-reveal').setAttribute('aria-pressed','false');}
function play(){
 if(animation){stop();return;}
 if(reduce.matches){stop();reveal(1);return;}
 const start=progress>=1?0:progress;reveal(start);animation={start,at:performance.now()};
 $('off-reveal').textContent='Ⅱ Pause';$('off-reveal').setAttribute('aria-pressed','true');
 function tick(now){if(!animation||!active()||document.hidden){stop();return;}reveal(animation.start+(now-animation.at)/6500);if(progress>=1)stop();else raf=requestAnimationFrame(tick);}
 raf=requestAnimationFrame(tick);
}
function slope(container,region){
 const el=$(container),w=Math.max(220,el.getBoundingClientRect().width),h=270,l=42,r=78,top=32,bot=50;
 const upper=region==='TRANSITION_CENTER'?.36:.08;
 const y=v=>top+(upper-v)/upper*(h-top-bot),x1=l+12,x2=w-r;
 const g=svg('svg',{viewBox:`0 0 ${w} ${h}`,role:'img','aria-label':`${region}, five-seed mean force RMSE at 2000 and 8000 steps; scale 0 to ${upper} eV/Å`});
 g.append(svg('title',{},`${region}: mean of five seeds; all endpoints STEP_LIMIT`));
 for(const v of (region==='TRANSITION_CENTER'?[0,.1,.2,.3]:[0,.02,.04,.06,.08])){
  g.append(svg('line',{x1:l,x2:x2,y1:y(v),y2:y(v),class:'off-grid'}));g.append(svg('text',{x:l-9,y:y(v)+4,'text-anchor':'end',class:'off-svg-axis'},String(v)));
 }
 for(const branch of ['basin','targeted']){
  const vals=[2000,8000].map(cap=>payload.benchmark.cell_means.find(r=>r.branch===branch&&r.budget===cap&&r.region===region).force_RMSE_eV_A);
  const group=svg('g',{class:branch,'data-off-branch':branch});
  group.append(svg('path',{d:`M${x1} ${y(vals[0])}L${x2} ${y(vals[1])}`,class:'off-slope-line'}));
  [x1,x2].forEach((x,i)=>group.append(branch==='targeted'?svg('path',{d:`M${x} ${y(vals[i])-5}l5 5 -5 5 -5 -5Z`}):svg('circle',{cx:x,cy:y(vals[i]),r:5})));
  group.append(svg('text',{x:x2+11,y:y(vals[1])+4,class:'off-svg-value'},vals[1].toFixed(4)));g.append(group);
 }
 for(const [x,cap] of [[x1,2000],[x2,8000]])g.append(svg('text',{x,y:h-22,'text-anchor':'middle',class:'off-svg-axis'},String(cap)));
 g.append(svg('text',{x:(x1+x2)/2,y:h-2,'text-anchor':'middle',class:'off-svg-axis'},'Main step cap'));el.replaceChildren(g);
}
function direction(){
 const region=$('off-region').value,cap=Number($('off-cap').value),seed=$('off-seed').value;
 const max=Math.ceil(Math.max(...payload.benchmark.block_rows.map(r=>r.force_RMSE_eV_A))*10)/10;
 const el=$('off-direction-chart');el.replaceChildren();
 for(const mode of modes){
  const row=document.createElement('div');row.className='off-block-row';row.dataset.mode=mode;
  const title=document.createElement('div');title.className='off-block-label';title.textContent=names[mode];
  const note=document.createElement('small');note.textContent=mode==='H_out_of_plane'?'+ only ·1 geometry':'± pair ·2 geometries';title.append(note);row.append(title);
  for(const branch of ['basin','targeted']){
   const selected=payload.benchmark.block_rows.filter(r=>r.region===region&&r.budget===cap&&r.mode===mode&&r.branch===branch&&(seed==='all'||r.seed_index===Number(seed)));
   if(selected.length!==(seed==='all'?5:1))throw new Error('Invalid off-path selection');const value=mean(selected);
   const pair=document.createElement('div');pair.className='off-block-pair';pair.dataset.branch=branch;
   const label=document.createElement('span');label.textContent=branch==='basin'?'Basin':'Targeted';
   const track=document.createElement('div');track.className='off-block-track';track.setAttribute('aria-hidden','true');const fill=document.createElement('div');fill.className='off-block-fill '+branch;fill.style.width=(value/max*100)+'%';track.append(fill);
   const numeric=document.createElement('span');numeric.className='off-block-value';numeric.textContent=value.toFixed(6);numeric.dataset.value=String(value);
   pair.append(label,track,numeric);row.append(pair);
  }el.append(row);
 }
 const axis=document.createElement('p');axis.className='off-direction-axis';axis.textContent=`Shared bar scale: 0–${max.toFixed(1)} eV/Å, unchanged across all filters.`;el.append(axis);
 $('off-direction-description').textContent=`${region==='TRANSITION_CENTER'?'Transition region':'Near the minimum'} ·${cap} steps ·${seed==='all'?'mean of all five initializations':`seed ${seed} / ${payload.benchmark.primary.contrasts[Number(seed)].seed_u64}`}. Equal block weighting; all 280 cases remain in the table.`;
}
function geometry(){
 const g=payload.benchmark.geometries.find(g=>g.id===$('off-geometry').value);if(!g)throw new Error('Unknown saved geometry');
 if(!stage)stage=new MolecularStage($('offpath-molecule'),g.xyz);
 stage.update(g.xyz);stage.resize();stage.setTheme(document.documentElement.dataset.theme==='dark');
 $('off-geometry-id').textContent=g.id+' · '+(g.region==='TRANSITION_CENTER'?'TRANSITION':'MINIMUM');$('off-q').textContent=g.q.toFixed(4);$('off-roo').textContent=g.roo.toFixed(4);
}
function draw(){if(!payload||!active())return;const nav=document.querySelector('nav'),link=document.querySelector('[data-route=offpath]');const a=link.getBoundingClientRect(),n=nav.getBoundingClientRect();if(a.right>n.right||a.left<n.left)nav.scrollLeft+=a.left-n.left-12;primary();slope('off-budget-transition','TRANSITION_CENTER');slope('off-budget-basin','BASIN_LEFT');direction();geometry();}
function initialize(){
 if(started||!payload||document.body.dataset.ready!=='true')return;started=true;
 $('off-reveal').addEventListener('click',play);$('off-reveal-reset').addEventListener('click',()=>{stop();reveal(1);});$('off-progress').addEventListener('input',e=>{stop();reveal(Number(e.target.value));});
 $('off-geometry').addEventListener('change',geometry);$('off-view-reset').addEventListener('click',()=>stage?.resetView());
 for(const id of ['off-region','off-cap','off-seed'])$(id).addEventListener('change',direction);
 window.addEventListener('hashchange',()=>{stop();requestAnimationFrame(draw);});let resize;
 window.addEventListener('resize',()=>{clearTimeout(resize);resize=setTimeout(()=>{stop();draw();},170);});
 new MutationObserver(()=>stage?.setTheme(document.documentElement.dataset.theme==='dark')).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});reduce.addEventListener('change',()=>{if(reduce.matches){stop();reveal(1);}});
 window.offpathExhibit={data:()=>payload,draw,stop,getState:()=>({ready:true,progress,playing:!!animation,geometry:$('off-geometry').value,region:$('off-region').value,cap:Number($('off-cap').value),seed:$('off-seed').value,renderer:stage?.el.dataset.renderer||null})};
 $('offpath').dataset.interactive='true';document.body.dataset.offpathReady='true';$('offpath-load-status').textContent='Saved-data verification: 14 references ·20 models ·280 force comparisons. Interactive exploration is ready.';draw();
}
try{
 const response=await fetch('data/offpath.json');if(!response.ok)throw new Error('Off-path payload not available');payload=await response.json();
 if(payload.schema!=='proton-offpath-v1'||payload.benchmark.n_models!==20||payload.benchmark.n_geometries!==14||payload.benchmark.case_rows.length!==280)throw new Error('Off-path payload cardinality');
 initialize();if(!started){const watch=new MutationObserver(()=>{initialize();if(started)watch.disconnect();});watch.observe(document.body,{attributes:true,attributeFilter:['data-ready']});}
}catch(error){document.body.dataset.offpathReady='error';$('offpath-load-status').textContent='Interactive off-path data could not be loaded. The complete static results, source links and tables remain available. '+error.message;}
