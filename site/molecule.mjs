import {ATOMS,BONDS,matrix,rotate,center,subtract,norm,clamp} from './core.mjs';
// Uniform orthographic 3-D projection, shaded with Canvas2D. No simulated forces.
const ROLL=.6164;
const colors=i=>i===1?['#fff4c9','#dfbb61','#776027']:i===0||i===7?['#ffe2d7','#c86d56','#653d38']:[2,4,6].includes(i)?['#9fb9b5','#536d70','#233d45']:['#ffffff','#ccd7d2','#7b9492'];
const radius=i=>i===1?.17:i===0||i===7?.245:[2,4,6].includes(i)?.22:.135;
export class MoleculeView {
 constructor(canvas){this.canvas=canvas;this.ctx=canvas.getContext('2d');this.points=[];this.last=null;}
 render(xyz,opts={}){
  this.last={xyz,opts};const canvas=this.canvas,c=this.ctx,r=canvas.getBoundingClientRect();
  if(r.width<1||r.height<1||!c)return;
  const dpr=Math.min(devicePixelRatio||1,2),w=r.width,h=r.height;
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,w,h);
  const dark=opts.dark!==false;const bg=c.createRadialGradient(w*.55,h*.46,5,w*.55,h*.48,w*.74);
  bg.addColorStop(0,dark?'#203d42':'#eef1e9');bg.addColorStop(1,dark?'#0b1d25':'#dfe8df');c.fillStyle=bg;c.fillRect(0,0,w,h);
  const camera=opts.camera||{yaw:-.24,tilt:.32,roll:0};
  const m=matrix(camera.yaw,camera.tilt,ROLL+(camera.roll||0)),origin=center(xyz);
  const rotated=xyz.map(p=>rotate(subtract(p,origin),m));
  const ext={xmin:Math.min(...rotated.map(v=>v[0])),xmax:Math.max(...rotated.map(v=>v[0])),ymin:Math.min(...rotated.map(v=>v[1])),ymax:Math.max(...rotated.map(v=>v[1]))};
  const scale=Math.min((w-85)/(ext.xmax-ext.xmin+.5),(h-105)/(ext.ymax-ext.ymin+.45))*Math.min(opts.zoom||1,1.05),cx=w/2-(ext.xmin+ext.xmax)*scale/2,cy=(h-20)/2+(ext.ymin+ext.ymax)*scale/2;
  const points=xyz.map((p,i)=>{const v=rotate(subtract(p,origin),m);return {x:cx+v[0]*scale,y:cy-v[1]*scale,z:v[2],r:radius(i)*scale,i};});this.points=points;
  // The floor is a lighting cue only; it is not a potential-energy surface.
  const shadow=c.createRadialGradient(cx,h*.83,2,cx,h*.83,w*.35);shadow.addColorStop(0,'#010c1433');shadow.addColorStop(1,'#010c1400');
  c.save();c.translate(cx,h*.84);c.scale(1,.17);c.fillStyle=shadow;c.translate(-cx,-h*.83);c.fillRect(0,0,w,h*2);c.restore();
  c.strokeStyle=dark?'#58767c20':'#92a49c25';c.lineWidth=.65;
  for(let y=h*.77;y<h;y+=22){c.beginPath();c.moveTo(w*.08,y);c.lineTo(w*.92,y);c.stroke();}
  if(opts.ghost){const ghost=opts.ghost.map(p=>{const v=rotate(subtract(p,center(opts.ghost)),m);return {x:cx+v[0]*scale,y:cy-v[1]*scale};});c.save();c.strokeStyle=dark?'#c7d8d44a':'#405f5a60';c.setLineDash([3,6]);c.lineWidth=1;for(const [a,b] of BONDS){c.beginPath();c.moveTo(ghost[a].x,ghost[a].y);c.lineTo(ghost[b].x,ghost[b].y);c.stroke();}for(const i of [0,2,4,6,7]){c.beginPath();c.arc(ghost[i].x,ghost[i].y,radius(i)*scale+3,0,Math.PI*2);c.stroke();}c.restore();}
  // Contacts are distance guides, never inferred bond-order values.
  c.save();c.lineWidth=1.5;c.strokeStyle='#e1c774aa';c.setLineDash([4,6]);
  for(const [a,b] of [[0,1],[1,7]]){c.beginPath();c.moveTo(points[a].x,points[a].y);c.lineTo(points[b].x,points[b].y);c.stroke();}
  c.restore();
  const items=BONDS.map(([a,b])=>({type:'bond',a,b,z:(points[a].z+points[b].z)/2-.05})).concat(points.map(p=>({...p,type:'atom'}))).sort((a,b)=>a.z-b.z);
  for(const item of items){
   if(item.type==='bond'){
    const a=points[item.a],b=points[item.b],dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1;
    const thick=scale*.066;const g=c.createLinearGradient(a.x-dy/len*thick,a.y+dx/len*thick,a.x+dy/len*thick,a.y-dx/len*thick);
    g.addColorStop(0,'#304c53');g.addColorStop(.35,'#c3d4cd');g.addColorStop(.6,'#869c9b');g.addColorStop(1,'#233f49');
    c.beginPath();c.moveTo(a.x+dx/len*a.r*.94,a.y+dy/len*a.r*.94);c.lineTo(b.x-dx/len*b.r*.94,b.y-dy/len*b.r*.94);c.lineWidth=thick*2;c.strokeStyle=g;c.lineCap='round';c.stroke();
   }else{
    const p=item,col=colors(p.i),rr=p.r;
    if(p.i===1){c.beginPath();c.arc(p.x,p.y,rr+9,0,Math.PI*2);c.strokeStyle='#e6c46655';c.lineWidth=1;c.stroke();}
    const grad=c.createRadialGradient(p.x-rr*.35,p.y-rr*.38,rr*.07,p.x+rr*.16,p.y+rr*.2,rr*1.06);grad.addColorStop(0,col[0]);grad.addColorStop(.38,col[1]);grad.addColorStop(1,col[2]);
    c.beginPath();c.arc(p.x,p.y,rr,0,Math.PI*2);c.fillStyle=grad;c.shadowColor='#00000035';c.shadowBlur=9;c.shadowOffsetY=4;c.fill();c.shadowBlur=0;c.shadowOffsetY=0;
    c.strokeStyle='#e6eeea35';c.lineWidth=.75;c.stroke();
    if(p.i===opts.selected){c.beginPath();c.arc(p.x,p.y,rr+5,0,Math.PI*2);c.strokeStyle='#ffe5a0';c.lineWidth=2;c.stroke();}
   }
  }
  // Draw force vectors in the SAME camera frame as the atomic coordinates.
  if(opts.force){
   const i=opts.selected??1,p=points[i],gain=opts.forceGain??4,reveal=opts.reveal??1;
   const f=opts.force,sets=[{name:'PBE',v:f.pbe[i],color:'#f0efdd',dash:[]},{name:'MTP',v:f.mtp[i],color:'#63c5b5',dash:[7,3]},{name:'ΔF',v:f.difference[i],color:'#eaba64',dash:[2,3]}];
   for(let k=0;k<sets.length;k++){
    const set=sets[k];if(opts.layer && opts.layer!=='all' && opts.layer!==['pbe','mtp','difference'][k])continue;
    const prog=clamp(reveal*3-k);if(prog===0)continue;const v=rotate(set.v,m),length=scale*gain;
    const end={x:p.x+v[0]*length*prog,y:p.y-v[1]*length*prog};this.arrow(p,end,set.color,set.dash);
   }
   c.font='11px system-ui';c.fillStyle='#bdd0cc';c.textAlign='left';c.fillText('Vector length: 1 eV/Å = '+Math.round(scale*gain)+' screen px',18,h-46);
  }
  if(opts.labels!==false){
   c.font='600 '+Math.max(11,Math.min(13,w/42))+'px system-ui';c.textAlign='center';
   for(const i of (opts.force?[0,1,2,7]:[0,1,7])){const p=points[i];c.fillStyle=i===1?'#ffe5a0':dark?'#e0e9e2':'#203e41';const off=i===1?16:18;c.fillText(ATOMS[i],p.x,i===1?p.y-p.r-11:p.y+p.r+off);}
  }
  if(opts.measure){
   const a=points[0],b=points[7],dy=h-43;this.dimension({x:a.x,y:dy},{x:b.x,y:dy},'O1–O8  '+norm(subtract(xyz[0],xyz[7])).toFixed(4)+' Å');
  }
  canvas.dataset.rendered='true';canvas.dataset.atomCount='9';
 }
 arrow(a,b,color,dash=[]){const c=this.ctx,dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy);if(len<.3)return;const angle=Math.atan2(dy,dx),size=Math.min(9,len*.4);c.save();c.strokeStyle=color;c.fillStyle=color;c.lineWidth=2.5;c.setLineDash(dash);c.beginPath();c.moveTo(a.x,a.y);c.lineTo(b.x,b.y);c.stroke();c.setLineDash([]);c.beginPath();c.moveTo(b.x,b.y);c.lineTo(b.x-size*Math.cos(angle-.45),b.y-size*Math.sin(angle-.45));c.lineTo(b.x-size*Math.cos(angle+.45),b.y-size*Math.sin(angle+.45));c.closePath();c.fill();c.restore();}
 dimension(a,b,label){const c=this.ctx;c.save();c.strokeStyle='#88aaa7';c.fillStyle='#c9deda';c.lineWidth=1;const mid=(a.x+b.x)/2;c.beginPath();c.moveTo(a.x,a.y-4);c.lineTo(a.x,a.y+4);c.moveTo(b.x,b.y-4);c.lineTo(b.x,b.y+4);c.moveTo(a.x,a.y);c.lineTo(b.x,b.y);c.stroke();c.fillStyle='#183238';c.fillRect(mid-88,a.y-10,176,20);c.textAlign='center';c.font='11px system-ui';c.fillStyle='#c9deda';c.fillText(label,mid,a.y+4);c.restore();}
 pick(x,y){let out=null;for(const p of this.points)if(Math.hypot(x-p.x,y-p.y)<p.r+8)out=p.i;return out;}
 resize(){if(this.last)this.render(this.last.xyz,this.last.opts);}
}
