/* Project-owned numerical and motion primitives. MIT. No DOM or model calls. */
export const ATOMS = ['O1','H2*','C3','H4','C5','H6','C7','O8','H9'];
export const ELEMENTS = ['O','H','C','H','C','H','C','O','H'];
export const HEAVY = [0,2,4,6,7];
export const BONDS = [[0,2],[2,3],[2,4],[4,5],[4,6],[6,7],[6,8]];
export const ROUTES = ['overview','molecule','sampling','landscape','seeds','train119','forces','story','longread','reproduce'];
export const clamp = (x,a,b) => Math.max(a,Math.min(b,x));
export function finite(x) { if (!Number.isFinite(x)) throw new Error('Non-finite numerical input'); return x; }
export const norm = a => Math.hypot(...a);
export const distance = (a,b) => Math.hypot(...a.map((v,i)=>v-b[i]));
export const mix = (a,b,t) => a+(b-a)*t;
export const smooth = x => { const t=clamp(x,0,1); return t*t*(3-2*t); };
export function geometry(xyz) {
  if(xyz.length!==9 || xyz.some(row=>row.length!==3 || row.some(x=>!Number.isFinite(x)))) throw new Error('Expected nine finite xyz triples');
  const left=distance(xyz[0],xyz[1]),right=distance(xyz[7],xyz[1]);
  return {left,right,q:left-right,roo:distance(xyz[0],xyz[7])};
}
export function center(xyz) {
  const c=[0,1,2].map(k=>HEAVY.reduce((s,i)=>s+xyz[i][k],0)/HEAVY.length);
  return xyz.map(row=>row.map((v,k)=>v-c[k]));
}
export function pathState(molecule,profile,t) {
  finite(t); if(molecule.length!==9 || profile.length!==9) throw new Error('Nine saved images required');
  t=clamp(t,0,8); const i=Math.min(7,Math.floor(t)),u=t-i;
  const xyz=molecule[i].xyz.map((r,a)=>r.map((v,k)=>mix(v,molecule[i+1].xyz[a][k],u)));
  const saved=Math.abs(t-Math.round(t))<1e-7;
  return {xyz,...geometry(xyz),energy:mix(profile[i],profile[i+1],u),t,saved,
    image:saved?Math.round(t)+1:null,between:[i+1,i+2]};
}
export function rotate(v,yaw,pitch,roll=0) {
  const [x,y,z]=v,c=Math.cos(yaw),s=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),cr=Math.cos(roll),sr=Math.sin(roll);
  const a=x*c+z*s,b=-x*s+z*c;
  const yy=y*cp-b*sp,zz=y*sp+b*cp;
  return [a*cr-yy*sr,a*sr+yy*cr,zz];
}
export function project(v,width,height,yaw,pitch,roll=0,scale=1) {
  const r=rotate(v,yaw,pitch,roll),unit=Math.min(width,height)/6.2*scale;
  return [width/2+r[0]*unit,height/2-r[1]*unit,r[2],unit];
}
export function vectorDifference(reference,predicted) {
  if(reference.length!==9 || predicted.length!==9 || [...reference,...predicted].some(r=>r.length!==3)) throw new Error('Nine xyz force vectors required');
  return reference.map((r,i)=>r.map((x,j)=>finite(predicted[i][j])-finite(x)));
}
export function forceRMSE(reference,predicted) {
  const v=vectorDifference(reference,predicted).flat();
  return Math.sqrt(v.reduce((s,x)=>s+x*x,0)/27);
}
export function pairedSeeds(rows) {
  const pairs=[];
  for(let i=0;i<5;i++) {
    const b=rows.find(r=>r.index===i&&r.model==='basin'),t=rows.find(r=>r.index===i&&r.model==='targeted');
    if(!b||!t||typeof b.seed!=='string'||b.seed!==t.seed) throw new Error('Invalid paired seed identity');
    pairs.push({index:i,seed:b.seed,basin:b,targeted:t,both:t.barrier<b.barrier&&t.force<b.force});
  }
  return pairs;
}
export function route(hash) {
  const raw=String(hash||'').replace(/^#/,'').split('?')[0];
  if(raw==='applicability') return 'train119';
  if(raw.startsWith('read-')) return 'longread';
  return ROUTES.includes(raw)?raw:'overview';
}
export function visibleCount(fraction,total) { return clamp(Math.floor(finite(fraction)*total+1e-9),0,total); }
export const CHAPTERS = [
  {title:'One proton. A moving scaffold.',caption:'Nine saved PBE images. Display time is not reaction time.',route:'molecule'},
  {title:'Spend the labels differently.',caption:'The same 36 shared configurations, then 24 additions in each branch.',route:'sampling'},
  {title:'A striking original result.',caption:'One frozen model pair; not a seed-robust causal estimate.',route:'landscape'},
  {title:'Then repeat the training.',caption:'Targeted wins both metrics in three of five paired seeds.',route:'seeds'},
  {title:'A warning is not a force error.',caption:'Five saved coverage crossings. Eleven local force-RMSE checks below A2.',route:'train119'},
  {title:'Keep the boundary of the claim.',caption:'Local PBE agreement, not independent deployment validation.',route:'reproduce'}
];
export function journeyState(t) {
  t=clamp(finite(t),0,1); const scaled=Math.min(5.999999,t*6),chapter=Math.floor(scaled);
  return {chapter,local:scaled-chapter,path:8*smooth((scaled-chapter)),...CHAPTERS[chapter]};
}
