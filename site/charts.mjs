/* SVG charts with explicit units, fixed comparison scales and persistent marks.
 * Motion reveals saved values; it never invents trajectories or error intervals.
 */
import {clamp,smooth,pairedSeeds} from './core.mjs';
const NS='http://www.w3.org/2000/svg';let serial=0;
const el=(tag,attrs={},text=null)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==null)n.textContent=text;return n;};
const number=(x,d=3)=>Math.abs(x)<1e-12?'0':Number(x.toFixed(d)).toString();
export const colors={PBE:'var(--pbe)',Basin60:'var(--basin)',Targeted60:'var(--targeted)',Train119:'var(--targeted)'};

function frame(container,{xDomain,yDomain,xLabel='',yLabel='',height=null,xTicks=null,yTicks=null,xFormat=null,yFormat=null,left=61}={}){
  const w=Math.max(260,container.getBoundingClientRect().width||600);
  if(document.body.classList.contains('export-mode'))height=680;
  const h=height||(container.classList.contains('short')?245:container.classList.contains('compact')?210:container.classList.contains('tall')?350:300);
  const pad={l:left,r:22,t:36,b:49};const pw=w-pad.l-pad.r,ph=h-pad.t-pad.b;
  const x=v=>pad.l+(v-xDomain[0])/(xDomain[1]-xDomain[0])*pw;
  const y=v=>pad.t+(yDomain[1]-v)/(yDomain[1]-yDomain[0])*ph;
  const svg=el('svg',{viewBox:`0 0 ${w} ${h}`,width:w,height:h,role:'img'});
  svg.append(el('title',{},container.getAttribute('aria-label')||`${yLabel} versus ${xLabel}`));
  const ticks=(a,b,n)=>Array.from({length:n},(_,i)=>a+(b-a)*i/(n-1));
  for(const v of yTicks||ticks(yDomain[0],yDomain[1],5)){
    svg.append(el('line',{x1:pad.l,x2:w-pad.r,y1:y(v),y2:y(v),class:'chart-grid'}));
    svg.append(el('text',{x:pad.l-10,y:y(v)+4,'text-anchor':'end',class:'chart-axis'},yFormat?yFormat(v):number(v,3)));
  }
  for(const v of xTicks||ticks(xDomain[0],xDomain[1],w<400?3:5)){
    svg.append(el('line',{x1:x(v),x2:x(v),y1:pad.t+ph,y2:pad.t+ph+5,stroke:'var(--muted)','stroke-width':.7}));
    svg.append(el('text',{x:x(v),y:pad.t+ph+21,'text-anchor':'middle',class:'chart-axis'},xFormat?xFormat(v):number(v,2)));
  }
  svg.append(el('text',{x:pad.l,y:16,class:'chart-title'},yLabel));
  svg.append(el('text',{x:pad.l+pw/2,y:h-4,'text-anchor':'middle',class:'chart-axis'},xLabel));
  container.replaceChildren(svg);return{svg,x,y,w,h,pad,pw,ph};
}
function dot(svg,cx,cy,color,{diamond=false,r=4.2,opacity=1,title='',onClick=null}={}){
  const n=diamond?el('path',{d:`M${cx},${cy-r-1}l${r+1},${r+1}l-${r+1},${r+1}l-${r+1},-${r+1}Z`,fill:color,opacity}):el('circle',{cx,cy,r,fill:color,opacity});
  n.append(el('title',{},title));if(onClick){n.style.cursor='pointer';n.addEventListener('click',onClick);}svg.append(n);return n;
}
export function linePlot(container,{series,xLabel='Proton-transfer coordinate qPT / Å',yLabel='Relative energy / meV',xDomain=null,yDomain=null,thresholds=[],onPoint=null,height=null,xTicks=null}={}){
  const values=series.flatMap(s=>s.values);const xs=values.map(p=>p.x),ys=values.map(p=>p.y);
  xDomain ||= [Math.min(...xs),Math.max(...xs)];
  if(!yDomain){const lo=Math.min(0,...ys),hi=Math.max(...ys),r=Math.max(hi-lo,.01);yDomain=[lo-r*.07,hi+r*.12];}
  const f=frame(container,{xDomain,yDomain,xLabel,yLabel,height,xTicks});const{svg,x,y,pad,pw,ph}=f;
  const clipID='plot-clip-'+(++serial),defs=el('defs'),cp=el('clipPath',{id:clipID}),clip=el('rect',{x:pad.l-7,y:pad.t-12,width:pw+14,height:ph+24});cp.append(clip);defs.append(cp);svg.append(defs);
  for(const th of thresholds){const yy=y(th.value);svg.append(el('line',{x1:pad.l,x2:pad.l+pw,y1:yy,y2:yy,stroke:th.color||'var(--basin)','stroke-width':1.3,'stroke-dasharray':'5 4'}));svg.append(el('text',{x:pad.l+pw-3,y:yy-7,'text-anchor':'end',class:'chart-label',fill:th.color||'var(--basin)'},th.label));}
  const marks=el('g',{'clip-path':`url(#${clipID})`});svg.append(marks);
  for(const s of series){const path=s.values.map((p,i)=>(i?'L':'M')+x(p.x)+','+y(p.y)).join(' ');marks.append(el('path',{d:path,fill:'none',stroke:s.color||colors[s.name]||'var(--teal)','stroke-width':2.1,'stroke-linejoin':'round','stroke-linecap':'round','data-series':s.name}));for(const p of s.values){dot(marks,x(p.x),y(p.y),s.color||colors[s.name]||'var(--teal)',{diamond:s.name==='Targeted60'||s.diamond,r:3.5,title:`${s.name}; ${xLabel}: ${p.x}; ${yLabel}: ${p.y}`,onClick:onPoint?()=>onPoint(p):null});}}
  const cursor=el('line',{x1:0,x2:0,y1:pad.t-4,y2:pad.t+ph,stroke:'var(--muted)','stroke-width':1,'stroke-dasharray':'3 5',opacity:0});svg.append(cursor);
  const markers=series.map(s=>{const c=el('circle',{r:6,fill:'var(--panel)',stroke:s.color||colors[s.name]||'var(--teal)','stroke-width':2.2,opacity:0});svg.append(c);return c;});
  return {frame:f,reveal(t){clip.setAttribute('width',clamp(t,0,1)*(pw+14));},cursor(xx,explicit=null){cursor.setAttribute('x1',x(xx));cursor.setAttribute('x2',x(xx));cursor.setAttribute('opacity','1');series.forEach((s,i)=>{let yy=explicit?.[s.name];if(yy===undefined){const a=s.values;let j=a.findIndex(p=>p.x>=xx);j=clamp(j<0?a.length-1:j,1,a.length-1);const p=a[j-1],q=a[j];yy=p.y+(q.y-p.y)*clamp((xx-p.x)/(q.x-p.x||1),0,1);}markers[i].setAttribute('cx',x(xx));markers[i].setAttribute('cy',y(yy));markers[i].setAttribute('opacity','1');});},destroy(){container.replaceChildren();}};
}
export function samplingPlot(container,points,branch,domain){
  const{svg,x,y}=frame(container,{xDomain:domain.x,yDomain:domain.y,xLabel:'Proton-transfer coordinate qPT / Å',yLabel:'O1–O8 distance / Å'});
  const shared=points.filter(p=>p.shared),added=points.filter(p=>!p.shared),nodes=[];
  for(const [kind,arr] of [['shared',shared],['added',added]])arr.forEach((p,i)=>{const n=dot(svg,x(p.q),y(p.roo),kind==='shared'?'var(--muted)':(branch==='basin'||branch==='both'&&p.branch==='basin')?'var(--basin)':'var(--targeted)',{diamond:kind==='added'&&(branch==='targeted'||p.branch==='targeted'),r:kind==='shared'?3.1:4.4,opacity:kind==='shared'?.52:1,title:`${p.id}; ${kind}; qPT ${p.q.toFixed(6)} Å; O–O ${p.roo.toFixed(6)} Å`});n.dataset.kind=kind;n.dataset.candidate=p.id;nodes.push({n,i,kind});});
  return{reveal(t){t=clamp(t,0,1);for(const{n,i,kind}of nodes){const local=kind==='shared'?t/.44:((t-.44)/.56),count=kind==='shared'?shared.length:added.length;const opacity=smooth(local*count-i);n.setAttribute('opacity',opacity*(kind==='shared'?.52:1));}return{shared:clamp(Math.floor(t/.44*36),0,36),added:clamp(Math.floor((t-.44)/.56*24),0,24)};}};
}
export function seedPlot(container,rows,metric){
  const pairs=pairedSeeds(rows),maximum=Math.max(...pairs.flatMap(p=>[p.basin[metric],p.targeted[metric]]));
  const upper=metric==='barrier'?Math.ceil(maximum/5)*5:Math.ceil(maximum*20)/20;
  const{svg,x,y,pad,pw}=frame(container,{xDomain:[0,upper],yDomain:[5.6,.4],xLabel:metric==='barrier'?'Absolute barrier error / meV':'Central force-component RMSE / eV/Å',yLabel:'Five paired training seeds',yTicks:[1,2,3,4,5],yFormat:v=>`Pair ${v}`,xFormat:v=>number(v,metric==='barrier'?0:3),left:64});
  const groups=[];
  for(const p of pairs){const g=el('g',{'data-seed-pair':p.index}),yy=y(p.index+1);svg.append(g);const bg=el('rect',{x:pad.l-3,y:yy-16,width:pw+6,height:32,rx:2,fill:'var(--pale)',opacity:0});g.append(bg);g.append(el('line',{x1:x(p.basin[metric]),x2:x(p.targeted[metric]),y1:yy,y2:yy,stroke:'var(--muted)','stroke-width':1.2}));dot(g,x(p.basin[metric]),yy,'var(--basin)',{r:5,title:`Pair ${p.index+1}, seed ${p.seed}; Basin60 ${p.basin[metric]}`});dot(g,x(p.targeted[metric]),yy,'var(--targeted)',{r:5,diamond:true,title:`Pair ${p.index+1}, seed ${p.seed}; Targeted60 ${p.targeted[metric]}`});groups.push({g,bg,index:p.index});}
  return{reveal(t){groups.forEach(({g,index})=>g.setAttribute('opacity',smooth(clamp(t,0,1)*5-index)));},select(index){groups.forEach(({bg,index:i})=>bg.setAttribute('opacity',Number(index)===i&&index!=='all'?1:0));}};
}
export function diagnosticPlots(gammaContainer,errorContainer,frames,stop,a2,onPoint){
  const indexes=frames.map(f=>f.index),deviations=frames.map(f=>(f.gamma-stop)*1000);
  const range=Math.max(...deviations)-Math.min(...deviations)||1;
  const yd=[Math.min(0,...deviations)-range*.15,Math.max(0,...deviations)+range*.2];
  const gamma=linePlot(gammaContainer,{series:[{name:'Gamma excess',color:'var(--basin)',values:frames.map(f=>({x:f.index,y:(f.gamma-stop)*1000,index:f.index}))}],xLabel:'Saved Replay228 index',yLabel:'(γ − stop) × 10³',xDomain:[indexes[0],indexes.at(-1)],xTicks:indexes,yDomain:yd,thresholds:[{value:0,label:'Frozen stop',color:'var(--muted)'}],onPoint});
  const error=linePlot(errorContainer,{series:[{name:'Force RMSE',color:'var(--targeted)',values:frames.map(f=>({x:f.index,y:f.rmse,index:f.index}))}],xLabel:'Saved Replay228 index',yLabel:'Force-component RMSE / eV/Å',xDomain:[indexes[0],indexes.at(-1)],xTicks:indexes,yDomain:[0,.1],thresholds:[{value:a2,label:'A2 = 0.09',color:'var(--basin)'}],onPoint});
  return{select(index){gamma.cursor(index);error.cursor(index);},gamma,error};
}
export function clearPlot(container){container.replaceChildren();}
