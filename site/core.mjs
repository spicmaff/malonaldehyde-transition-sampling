/* Pure scientific display mathematics. MIT. No model inference. */
export const ATOMS = ['O1','H2','C3','H4','C5','H6','C7','O8','H9'];
export const BONDS = [[0,2],[2,3],[2,4],[4,5],[4,6],[6,7],[6,8]];
export const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
export const mix=(a,b,t)=>a+(b-a)*t;
export const smooth=x=>{x=clamp(x);return x*x*(3-2*x);};
export const norm=v=>Math.hypot(...v);
export const subtract=(a,b)=>a.map((v,i)=>v-b[i]);
export const distance=(a,b)=>norm(subtract(a,b));
export function geometry(xyz){return {q:distance(xyz[0],xyz[1])-distance(xyz[7],xyz[1]),roo:distance(xyz[0],xyz[7]),left:distance(xyz[0],xyz[1]),right:distance(xyz[7],xyz[1])};}
export function pathState(data,position){
 const p=clamp(Number(position),0,8),i=Math.min(7,Math.floor(p)),t=p-i;
 const xyz=data.molecule[i].xyz.map((v,k)=>v.map((x,j)=>mix(x,data.molecule[i+1].xyz[k][j],t)));
 return {xyz,...geometry(xyz),energy:mix(data.profiles.PBE[i],data.profiles.PBE[i+1],t),position:p,saved:Math.abs(p-Math.round(p))<1e-8,image:Math.round(p)+1};
}
export function matrix(yaw=0,tilt=0,roll=0){
 const cy=Math.cos(yaw),sy=Math.sin(yaw),ct=Math.cos(tilt),st=Math.sin(tilt),cr=Math.cos(roll),sr=Math.sin(roll);
 return [[cy*cr+sy*st*sr,-cy*sr+sy*st*cr,sy*ct],[ct*sr,ct*cr,-st],[-sy*cr+cy*st*sr,sy*sr+cy*st*cr,cy*ct]];
}
export const rotate=(v,m)=>m.map(r=>r.reduce((s,x,i)=>s+x*v[i],0));
export function center(xyz){return [0,1,2].map(j=>[0,2,4,6,7].reduce((s,i)=>s+xyz[i][j],0)/5);}
export function forceError(reference,prediction){const err=prediction.map((r,i)=>r.map((x,j)=>x-reference[i][j]));return {err,rmse:Math.sqrt(err.flat().reduce((s,x)=>s+x*x,0)/27),max:Math.max(...err.flat().map(Math.abs))};}
export const residuals=(a,b)=>a.map((v,i)=>v-b[i]);
export function frameAt(progress,ids){return ids[Math.min(ids.length-1,Math.floor(clamp(progress)*ids.length))];}
export function route(hash){let s=String(hash).replace(/^#/,'').split('?')[0];const aliases={films:'story',forces:'forces',randomness:'seeds',methods:'reproduce'};s=aliases[s]||s;return ['overview','molecule','sampling','landscape','seeds','applicability','train119','forces','story','longread','reproduce'].includes(s)?s:'overview';}
export function sceneState(kind,t){
 t=clamp(t); const sweep=8*smooth(clamp((t-.08)/.82));
 if(kind==='hero')return {position:sweep,yaw:-.38+.42*smooth(t),tilt:.54-.18*Math.sin(Math.PI*t),phase:t<.22?'Two oxygen atoms':t<.62?'The scaffold moves too':'One path. Nine calculated structures.'};
 return {position:sweep,yaw:-.15,tilt:.22,phase:t<.47?'Approaching the central image':'Leaving the central image'};
}
export function finiteTree(value){if(typeof value==='number')return Number.isFinite(value);if(Array.isArray(value))return value.every(finiteTree);if(value&&typeof value==='object')return Object.values(value).every(finiteTree);return true;}
