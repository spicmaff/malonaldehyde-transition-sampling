// Original dependency-free SVG plots. Paths join saved samples, not fitted physics.
import {clamp} from './core.mjs';
const esc=x=>String(x).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
const fmt=x=>Math.abs(x)>=100?x.toFixed(0):Math.abs(x)>=1?x.toFixed(2):Math.abs(x)>.001?x.toFixed(3):x===0?'0':x.toExponential(1);
export function palette(){const s=getComputedStyle(document.documentElement);return Object.fromEntries(['ink','muted','line','pbe','basin','targeted','train119','warning','panel'].map(k=>[k,s.getPropertyValue('--'+k).trim()]));}
export function chart(el,opt){
 const w=Math.max(290,el.clientWidth||640),h=opt.height||270,p={l:57,r:20,t:35,b:49},iw=w-p.l-p.r,ih=h-p.t-p.b,c=palette();
 const all=opt.series.flatMap(s=>s.points);if(!all.length)return;
 let xd=opt.xDomain||[Math.min(...all.map(p=>p.x)),Math.max(...all.map(p=>p.x))],yd=opt.yDomain||[Math.min(0,...all.map(p=>p.y)),Math.max(...all.map(p=>p.y))*1.12];if(yd[0]===yd[1])yd=[yd[0]-1,yd[1]+1];
 const x=v=>p.l+(v-xd[0])/(xd[1]-xd[0])*iw,y=v=>p.t+ih-(v-yd[0])/(yd[1]-yd[0])*ih;
 let s=`<svg viewBox="0 0 ${w} ${h}" role="${opt.interactive?'group':'img'}" aria-label="${esc(opt.label||'Saved numerical data')}"><title>${esc(opt.label||'Saved numerical data')}</title>`;
 if(opt.region){const a=Math.max(xd[0],opt.region[0]),b=Math.min(xd[1],opt.region[1]);if(b>a)s+=`<rect x="${x(a)}" y="${p.t}" width="${x(b)-x(a)}" height="${ih}" fill="${c.targeted}" opacity=".07"/>`;}
 s+=`<text x="${p.l}" y="16" class="axis-title">${esc(opt.ylabel||'')}</text>`;
 for(let j=0;j<=4;j++){const v=yd[0]+(yd[1]-yd[0])*j/4,yy=y(v);s+=`<path d="M${p.l},${yy}H${w-p.r}" class="grid-line"/><text x="${p.l-9}" y="${yy+4}" text-anchor="end" class="tick">${esc(opt.yFormat?opt.yFormat(v):fmt(v))}</text>`;}
 const ticks=opt.xTicks||[xd[0],xd[0]+(xd[1]-xd[0])*.25,(xd[0]+xd[1])/2,xd[0]+(xd[1]-xd[0])*.75,xd[1]];
 for(const v of ticks)s+=`<text x="${x(v)}" y="${h-27}" text-anchor="middle" class="tick">${esc(opt.xFormat?opt.xFormat(v):fmt(v))}</text>`;
 s+=`<text x="${p.l+iw/2}" y="${h-7}" text-anchor="middle" class="axis-title">${esc(opt.xlabel||'')}</text>`;
 if(opt.reference){const yy=y(opt.reference.value);s+=`<path d="M${p.l},${yy}H${w-p.r}" stroke="${c.warning}" stroke-width="1.5" stroke-dasharray="5 4"/><text x="${w-p.r}" y="${yy-6}" text-anchor="end" class="threshold">${esc(opt.reference.label)}</text>`;}
 if(opt.activeX!==undefined)s+=`<path d="M${x(opt.activeX)},${p.t}V${p.t+ih}" class="cursor-line"/>`;
 for(const serie of opt.series){const pts=serie.points.filter(pt=>pt.x>=xd[0]&&pt.x<=xd[1]);if(!pts.length)continue;const color=serie.color||c[serie.key]||c.pbe;
  if(serie.line!==false){let path=pts.map((pt,i)=>`${i?'L':'M'}${x(pt.x)},${y(pt.y)}`).join(' ');s+=`<path d="${path}" fill="none" stroke="${color}" stroke-width="${serie.key==='pbe'?2.3:2}" ${serie.dash?'stroke-dasharray="'+serie.dash+'"':''} opacity="${serie.opacity??1}"/>`;}
  for(const [i,pt] of pts.entries()){const alpha=opt.reveal===undefined?1:clamp(opt.reveal*pts.length-i);const active=pt.index===opt.activeIndex;
   s+=`<circle cx="${x(pt.x)}" cy="${y(pt.y)}" r="${active?6.5:serie.r||3.4}" fill="${active?color:c.panel}" stroke="${color}" stroke-width="${active?2.5:1.7}" opacity="${alpha*(serie.opacity??1)}" data-index="${pt.index??i}" data-value="${pt.y}" ${opt.interactive?'tabindex="0" role="button"':''} aria-label="${esc((serie.name||serie.key)+' '+(pt.label||'sample '+(i+1))+', '+fmt(pt.y))}"><title>${esc(serie.name||serie.key)} · ${esc(pt.label||pt.x)}: ${pt.y}</title></circle>`;
  }
 }
 s+='</svg>';el.innerHTML=s;
 if(opt.onSelect)for(const node of el.querySelectorAll('[data-index]')){const call=()=>opt.onSelect(Number(node.dataset.index));node.addEventListener('click',call);node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();call();}});}
}
export function samplingPlot(el,data,reveal=1){
 const p=palette(),common=data.basin.filter(r=>r.shared),b=data.basin.filter(r=>!r.shared),t=data.targeted.filter(r=>!r.shared);
 const series=[{key:'pbe',name:'Common36',color:p.muted,points:common.map((a,i)=>({x:a.q,y:a.roo,label:a.id,index:i})),r:2.7,line:false,opacity:clamp(reveal*3)},
 {key:'basin',name:'Basin additions',points:b.map((a,i)=>({x:a.q,y:a.roo,label:a.id,index:i+36})),r:3.8,line:false,opacity:clamp(reveal*3-1)},
 {key:'targeted',name:'Targeted additions',points:t.map((a,i)=>({x:a.q,y:a.roo,label:a.id,index:i+60})),r:3.8,line:false,opacity:clamp(reveal*3-2)}];
 chart(el,{series,height:350,xlabel:'qPT (Å)',ylabel:'O1–O8 distance (Å)',label:'Actual training structures projected to two coordinates. Not a trajectory.',xDomain:[-.65,.65],yDomain:[2.47,2.55],region:[-.15,.15]});
}
export function seedPlot(el,seeds,metric='barrier',active=0,reveal=1){
 const w=Math.max(290,el.clientWidth||600),h=324,c=palette(),l=45,r=30,iw=w-l-r,max=Math.max(...seeds.map(d=>d[metric]))*1.12,x=v=>l+v/max*iw;
 let s=`<svg viewBox="0 0 ${w} ${h}" role="group" aria-label="All five paired seeds, ${metric==='barrier'?'barrier error in meV':'force-component RMSE in eV per angstrom'}"><title>Five paired training seeds; lower is more accurate</title>`;
 for(let j=0;j<=4;j++){const v=max*j/4;s+=`<path d="M${x(v)},28V280" class="grid-line"/><text x="${x(v)}" y="299" text-anchor="middle" class="tick">${fmt(v)}</text>`;}
 for(let i=0;i<5;i++){const a=seeds.find(s=>s.index===i&&s.model==='basin'),b=seeds.find(s=>s.index===i&&s.model==='targeted'),y=52+i*49,op=clamp(reveal*5-i);s+=`<g opacity="${op}"><text x="14" y="${y+4}" class="tick">${i+1}</text><path d="M${x(a[metric])},${y}H${x(b[metric])}" stroke="${c.muted}" stroke-width="1.5"/>`;
 for(const row of [a,b])s+=`<circle cx="${x(row[metric])}" cy="${y}" r="${active===i?7:5}" fill="${c[row.model]}" tabindex="0" role="button" data-seed="${i}" aria-label="Seed ${i+1}, ${row.model}, ${row[metric]}"><title>Seed ${i+1}, ${row.model}: ${row[metric]}</title></circle>`;s+='</g>';}
 s+=`<text x="${w/2}" y="321" text-anchor="middle" class="axis-title">${metric==='barrier'?'Absolute barrier error (meV)':'Central force-component RMSE (eV/Å)'}</text></svg>`;el.innerHTML=s;
}
