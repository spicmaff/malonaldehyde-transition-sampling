/* Validate saved scientific relationships before enabling any scene. */
const require=(ok,message)=>{if(!ok)throw new Error('Invalid scientific data: '+message);};
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const close=(a,b,t=1e-10)=>finite(a)&&finite(b)&&Math.abs(a-b)<=t;
const vector=v=>Array.isArray(v)&&v.length===3&&v.every(finite);
const matrix=m=>Array.isArray(m)&&m.length===9&&m.every(vector);
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
const sequence=(v,n)=>Array.isArray(v)&&v.length===n&&v.every(finite);
function geometry(c){
  require(matrix(c.xyz),'nine finite atomic coordinates');
  const left=distance(c.xyz[0],c.xyz[1]),right=distance(c.xyz[7],c.xyz[1]);
  require(close(c.q,left-right)&&close(c.roo,distance(c.xyz[0],c.xyz[7])),'geometry / descriptor correspondence');
  require(close(c.left,left)&&close(c.right,right),'O–H distance correspondence');
}
export function validateScience(d){
  require(d?.schema==='proton-potential-cinematic-v2','schema');
  require(Array.isArray(d.molecule)&&d.molecule.length===9,'nine saved images');
  d.molecule.forEach((m,i)=>{require(m.image===i+1,'ordered saved images');geometry(m);});
  for(const key of ['PBE','Basin60','Targeted60','Train119']){
    require(sequence(d.profiles?.[key],9)&&sequence(d.residuals?.[key],9),'complete energy arrays');
    require(close(Math.min(d.profiles[key][0],d.profiles[key][8]),0),'individual lower-endpoint zero');
    d.profiles[key].forEach((e,i)=>require(close(d.residuals[key][i],e-d.profiles.PBE[i]),'relative profile residual'));
    const m=d.metrics?.[key];
    require(m&&close(m.barrier,Math.max(...d.profiles[key]))&&finite(m.force_rmse)&&m.force_rmse>=0,'barrier / force metric');
  }
  for(const branch of ['basin','targeted']){
    const rows=d.sampling?.[branch];
    require(Array.isArray(rows)&&rows.length===60&&new Set(rows.map(r=>r.id)).size===60,'60 unique training identities');
    require(rows.filter(r=>r.shared===true).length===36&&rows.every(r=>typeof r.id==='string'&&typeof r.shared==='boolean'&&finite(r.q)&&finite(r.roo)),'training roles / descriptors');
  }
  const b=new Map(d.sampling.basin.map(r=>[r.id,r]));
  require(d.sampling.targeted.filter(r=>b.has(r.id)).length===36,'shared training intersection');
  for(const r of d.sampling.targeted){const common=b.get(r.id);require(r.shared===Boolean(common),'common identity flag');if(common)require(common.shared&&close(common.q,r.q)&&close(common.roo,r.roo),'shared geometry correspondence');}
  require(Array.isArray(d.seeds)&&d.seeds.length===10,'ten paired training records');
  for(let i=0;i<5;i++){
    const pair=d.seeds.filter(r=>r.index===i);
    require(pair.length===2&&new Set(pair.map(r=>r.model)).size===2&&pair.every(r=>['basin','targeted'].includes(r.model)&&typeof r.seed==='string'&&/^\d+$/.test(r.seed)&&finite(r.barrier)&&r.barrier>=0&&finite(r.force)&&r.force>=0)&&pair[0].seed===pair[1].seed,'paired seed identities and finite errors');
  }
  require(finite(d.stop)&&d.stop>0&&finite(d.a2)&&d.a2>0,'applicability and force thresholds');
  require(Array.isArray(d.replay)&&d.replay.length===228&&d.replay.every((r,i)=>r.index===i+1&&finite(r.gamma)),'228 ordered coverage grades');
  require(Array.isArray(d.forces)&&d.forces.length===11&&new Set(d.forces.map(f=>f.index)).size===11,'eleven distinct force frames');
  for(const f of d.forces){
    geometry(f);
    require(['CROSSING7','CHALLENGE4'].includes(f.group)&&matrix(f.pbe)&&matrix(f.mtp)&&matrix(f.error),'frame groups / force vectors');
    require(f.ids?.join(',')==='1,2,3,4,5,6,7,8,9'&&f.elements?.join(',')==='O,H,C,H,C,H,C,O,H','atom IDs and elements');
    const squared=[];
    f.error.forEach((v,i)=>v.forEach((x,j)=>{require(close(x,f.mtp[i][j]-f.pbe[i][j]),'force difference sign');squared.push(x*x);}));
    require(close(f.rmse,Math.sqrt(squared.reduce((a,b)=>a+b,0)/27)),'27-component RMSE');
    require(close(f.gamma,d.replay[f.index-1]?.gamma),'frame / saved grade correspondence');
  }
  return d;
}
