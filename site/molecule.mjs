/* Data-driven molecular stage. Coordinates and forces share one rigid transform.
 * Radii, lighting and dashed distance guides are illustrative, not electronic data.
 * Three.js is vendored with its unmodified MIT license. Canvas fallback is local.
 */
import {ATOMS,ELEMENTS,BONDS,center,project,norm,clamp} from './core.mjs';
let library;
const loadThree = () => library ||= import('./vendor/three/three.module.js');
const PALETTE={O:'#bd4c35',C:'#526561',H:'#eee9dd',star:'#199783'};

export class MolecularStage {
  constructor(element,xyz,{onSelect=null,compact=false}={}) {
    this.el=element; this.xyz=xyz; this.points=center(xyz); this.onSelect=onSelect;
    this.yaw=-.34; this.pitch=.24; this.roll=.65; this.zoom=1; this.compact=compact;
    this.selected=-1; this.forces=null; this.forceScale=2; this.layers={pbe:true,mtp:true,error:true};
    this.dark=document.documentElement.dataset.theme==='dark'; this.drag=null;this.disposed=false;
    this.canvas=document.createElement('canvas');this.canvas.className='molecule-canvas';
    this.canvas.setAttribute('aria-hidden','true');this.el.append(this.canvas);
    this.labels=document.createElement('div');this.labels.className='atom-labels';this.labels.setAttribute('aria-hidden','true');this.el.append(this.labels);
    this.labelNodes=ATOMS.map((name,i)=>{const d=document.createElement('span');d.textContent=name;d.className=i===1?'proton-label':'';this.labels.append(d);return d;});
    this.el.dataset.renderer='canvas'; this.ctx=this.canvas.getContext('2d');
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(element);
    this.canvas.style.touchAction='pan-y';
    this.el.addEventListener('pointerdown',e=>{if(e.target.closest('button,input,a'))return;this.drag={x:e.clientX,y:e.clientY,yaw:this.yaw,pitch:this.pitch,moved:false};});
    this.el.addEventListener('pointermove',e=>{if(!this.drag)return;const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;if(Math.abs(dx)>5){this.drag.moved=true;this.yaw=this.drag.yaw+dx*.008;this.pitch=clamp(this.drag.pitch+dy*.005,-1.1,1.1);this.render();}});
    const up=e=>{if(this.drag&&!this.drag.moved)this.pick(e);this.drag=null;};
    this.el.addEventListener('pointerup',up);this.el.addEventListener('pointerleave',()=>this.drag=null);
    this.resize();
    this.ready=this.initialize().catch(()=>{this.el.dataset.renderer='canvas-fallback';this.render();});
  }
  async initialize() {
    if(new URLSearchParams(location.search).has('fallback')){this.el.dataset.renderer='canvas-fallback';return;}
    const T=await loadThree();if(this.disposed)return;
    const renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power',preserveDrawingBuffer:true});
    this.T=T;this.renderer=renderer;renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.75));
    renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;
    renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;
    this.scene=new T.Scene();this.camera=new T.OrthographicCamera(-3,3,3,-3,.1,40);this.camera.position.set(0,0,10);
    this.group=new T.Group();this.scene.add(this.group);
    this.scene.add(new T.HemisphereLight(0xffffff,0x74786c,2.6));
    const key=new T.DirectionalLight(0xfff8e8,3.3);key.position.set(-3,5,7);key.castShadow=true;
    key.shadow.mapSize.set(1024,1024);Object.assign(key.shadow.camera,{left:-4,right:4,top:4,bottom:-4,near:.1,far:25});
    key.shadow.bias=-.0005;key.shadow.radius=4;this.scene.add(key);
    const rim=new T.DirectionalLight(0xb6e2d5,2.1);rim.position.set(4,-1,3);this.scene.add(rim);
    const back=new T.DirectionalLight(0xffd6b0,1.3);back.position.set(2,3,-4);this.scene.add(back);
    this.sphere=new T.SphereGeometry(1,40,28);this.cylinder=new T.CylinderGeometry(1,1,1,18);
    this.materials=ELEMENTS.map((e,i)=>new T.MeshStandardMaterial({color:i===1?PALETTE.star:PALETTE[e],roughness:.32,metalness:i===1?.25:.12}));
    this.atoms=this.points.map((p,i)=>{const m=new T.Mesh(this.sphere,this.materials[i]);m.scale.setScalar(i===1?.175:ELEMENTS[i]==='H'?.125:ELEMENTS[i]==='O'?.265:.24);m.castShadow=true;m.receiveShadow=true;m.userData.atom=i;this.group.add(m);return m;});
    this.bondMat=new T.MeshStandardMaterial({color:0x87928c,roughness:.4,metalness:.25});
    this.bonds=BONDS.map(([a,b])=>{const m=new T.Mesh(this.cylinder,this.bondMat);m.castShadow=true;this.group.add(m);return{a,b,m};});
    const guideMat=new T.MeshStandardMaterial({color:0x71968e,transparent:true,opacity:.65,roughness:.7});
    this.guides=[];
    for(const [a,b] of [[0,1],[1,7]])for(let j=0;j<12;j++){const m=new T.Mesh(this.cylinder,guideMat);this.group.add(m);this.guides.push({a,b,j,m});}
    this.shadow=new T.Mesh(new T.PlaneGeometry(30,30),new T.ShadowMaterial({opacity:.05}));this.shadow.position.z=-1.9;this.shadow.receiveShadow=true;this.scene.add(this.shadow);
    this.ring=new T.Mesh(new T.TorusGeometry(.30,.013,10,64),new T.MeshBasicMaterial({color:0xbb6a43,transparent:true,opacity:.85}));this.group.add(this.ring);this.ring.visible=false;
    this.arrows={};for(const [k,col] of Object.entries({pbe:0x313e3c,mtp:0x168574,error:0xc6643c})) {const a=new T.ArrowHelper(new T.Vector3(1,0,0),new T.Vector3(),1,col,.16,.07);this.group.add(a);a.visible=false;this.arrows[k]=a;}
    this.raycaster=new T.Raycaster();this.mouse=new T.Vector2();
    const gl=renderer.domElement;gl.className='molecule-canvas';gl.setAttribute('aria-hidden','true');this.canvas.replaceWith(gl);this.canvas=gl;
    this.el.dataset.renderer='webgl';this.el.classList.add('rendered');this.resize();
    this.canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();this.el.dataset.renderer='context-lost';this.el.classList.remove('rendered');});
  }
  update(xyz,{selected=this.selected,forces=this.forces,scale=this.forceScale,layers=this.layers}={}) {
    this.xyz=xyz;this.points=center(xyz);this.selected=selected;this.forces=forces;this.forceScale=scale;this.layers=layers;this.render();
  }
  setView(yaw,pitch=this.pitch,roll=this.roll){this.yaw=yaw;this.pitch=pitch;this.roll=roll;this.render();}
  resetView(){this.yaw=-.34;this.pitch=.24;this.roll=.65;this.zoom=1;this.resize();}
  setTheme(dark){this.dark=dark;this.render();}
  resize(){const r=this.el.getBoundingClientRect();if(r.width<2||r.height<2)return;this.width=r.width;this.height=r.height;
    if(this.renderer){const aspect=r.width/r.height;const half=Math.max(2.25,2.8/aspect)/this.zoom;this.camera.left=-half*aspect;this.camera.right=half*aspect;this.camera.top=half;this.camera.bottom=-half;this.camera.updateProjectionMatrix();this.renderer.setSize(r.width,r.height,false);}
    else{const d=Math.min(devicePixelRatio||1,1.75);this.canvas.width=Math.round(r.width*d);this.canvas.height=Math.round(r.height*d);this.ctx.setTransform(d,0,0,d,0,0);}
    this.render();
  }
  segment(m,a,b,radius){const T=this.T,A=new T.Vector3(...a),B=new T.Vector3(...b),diff=B.clone().sub(A);m.position.copy(A.add(B).multiplyScalar(.5));m.scale.set(radius,diff.length(),radius);m.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),diff.normalize());}
  render(){if(this.disposed||!this.width||!this.el.getClientRects().length)return;
    if(!this.renderer){this.drawFallback();return;}
    const T=this.T;this.group.rotation.set(this.pitch,this.yaw,this.roll,'ZXY');
    this.atoms.forEach((m,i)=>m.position.set(...this.points[i]));
    for(const {a,b,m} of this.bonds)this.segment(m,this.points[a],this.points[b],.058);
    for(const {a,b,j,m} of this.guides){const pa=this.points[a],pb=this.points[b],s=(j+.15)/12,e=(j+.63)/12;this.segment(m,pa.map((x,k)=>x+(pb[k]-x)*s),pa.map((x,k)=>x+(pb[k]-x)*e),.014);}
    this.ring.visible=this.selected>=0;if(this.ring.visible){this.ring.position.set(...this.points[this.selected]);this.ring.position.z+=.025;}
    for(const [k,a] of Object.entries(this.arrows)){a.visible=Boolean(this.forces&&this.selected>=0&&this.layers[k]);if(!a.visible)continue;const v=this.forces[k][this.selected],length=norm(v)*this.forceScale;if(length<1e-10){a.visible=false;continue;}a.position.set(...this.points[this.selected]);a.setDirection(new T.Vector3(...v).normalize());a.setLength(length,Math.min(.16,length*.34),Math.min(.08,length*.18));a.setColor(k==='pbe'?(this.dark?0xf0e9dc:0x313e3c):k==='mtp'?0x2fbaa2:0xd7784c);}
    this.renderer.render(this.scene,this.camera);
    this.atoms.forEach((m,i)=>{const p=m.getWorldPosition(new T.Vector3()).project(this.camera);this.setLabel(i,(p.x*.5+.5)*this.width,(-p.y*.5+.5)*this.height);});
  }
  setLabel(i,x,y){const show=[0,1,7].includes(i)||i===this.selected;const el=this.labelNodes[i];el.hidden=!show;if(show){el.style.left=`${clamp(x,25,this.width-25)}px`;el.style.top=`${clamp(y+28,20,this.height-24)}px`;}}
  drawFallback(){const c=this.ctx,w=this.width,h=this.height;c.clearRect(0,0,w,h);const ps=this.points.map(p=>project(p,w,h,this.yaw,this.pitch,this.roll,this.zoom));
    c.lineCap='round';for(const [a,b] of [...BONDS,[0,1],[1,7]]){c.beginPath();c.moveTo(...ps[a].slice(0,2));c.lineTo(...ps[b].slice(0,2));c.strokeStyle=this.dark?'#83938c':'#8b9790';c.lineWidth=(a===1||b===1)?1.5:7;c.setLineDash(a===1||b===1?[4,6]:[]);c.stroke();}c.setLineDash([]);
    const ordered=ps.map((p,i)=>({p,i})).sort((a,b)=>a.p[2]-b.p[2]);for(const {p,i} of ordered){const radius=(i===1?.18:ELEMENTS[i]==='H'?.13:.25)*p[3],color=i===1?PALETTE.star:PALETTE[ELEMENTS[i]];const g=c.createRadialGradient(p[0]-radius*.3,p[1]-radius*.4,radius*.05,p[0],p[1],radius);g.addColorStop(0,'#ffffff');g.addColorStop(.25,color);g.addColorStop(1,i===1?'#0c5248':ELEMENTS[i]==='O'?'#642f23':ELEMENTS[i]==='C'?'#27332f':'#a6a394');c.fillStyle=g;c.beginPath();c.arc(p[0],p[1],radius,0,Math.PI*2);c.fill();this.setLabel(i,p[0],p[1]);}
    if(this.forces&&this.selected>=0){const origin=this.points[this.selected],p=ps[this.selected];for(const k of ['pbe','mtp','error'])if(this.layers[k]){const v=this.forces[k][this.selected],e=project(origin.map((x,j)=>x+v[j]*this.forceScale),w,h,this.yaw,this.pitch,this.roll,this.zoom),a=Math.atan2(e[1]-p[1],e[0]-p[0]);c.strokeStyle=c.fillStyle=k==='pbe'?(this.dark?'#ede8da':'#2d3835'):k==='mtp'?'#239c85':'#cf7245';c.lineWidth=2.5;c.beginPath();c.moveTo(p[0],p[1]);c.lineTo(e[0],e[1]);c.stroke();c.beginPath();c.moveTo(e[0],e[1]);c.lineTo(e[0]-8*Math.cos(a-.4),e[1]-8*Math.sin(a-.4));c.lineTo(e[0]-8*Math.cos(a+.4),e[1]-8*Math.sin(a+.4));c.fill();}}
    this.el.classList.add('rendered');
  }
  pick(e){if(!this.onSelect||!this.width)return;const rect=this.el.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;
    if(this.renderer){this.mouse.set(x/this.width*2-1,1-y/this.height*2);this.raycaster.setFromCamera(this.mouse,this.camera);const hit=this.raycaster.intersectObjects(this.atoms)[0];if(hit)this.onSelect(hit.object.userData.atom);}
    else{const candidates=this.points.map((p,i)=>({i,p:project(p,this.width,this.height,this.yaw,this.pitch,this.roll,this.zoom)})).filter(o=>Math.hypot(o.p[0]-x,o.p[1]-y)<24).sort((a,b)=>b.p[2]-a.p[2]);if(candidates[0])this.onSelect(candidates[0].i);}}
  dispose(){this.disposed=true;this.resizeObserver.disconnect();this.renderer?.dispose();}
}
