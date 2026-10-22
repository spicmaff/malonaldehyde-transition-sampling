/* Source-derived, finite editorial reader. No model, optimizer or physical simulation. */
const root = document.getElementById('opt-finale-tradeoff');
const page = document.getElementById('optimization');
const $ = id => document.getElementById(id);
const buttons = root ? [...root.querySelectorAll('button')] : [];
const stepButtons = root ? [...root.querySelectorAll('[data-sf-step]')] : [];
const motion = matchMedia('(prefers-reduced-motion: reduce)');
let data = null, index = 5, timer = null, playing = false, failed = false;
const steps = [
  ['S1c','all','Begin at the compensated incumbent.','S1c is a diagnostic copy in the new frame. Its row loss is small, while the coefficient penalty is larger. This is not the original native S0 value.'],
  ['S1c','ell','Separate the fit from the penalty.','The orange segment is ℓ: squared weighted residual, divided by 60. It is not a force RMSE and does not include the coefficient ridge.'],
  ['both','ell','After refitting, the residual is larger.','Compare the two stored orange segments on the same fixed scale. The row data fit worsens from S1c to S2. There are no interpolated measurement states.'],
  ['both','R','The refit buys a smaller penalty.','The green segment shrinks by more than the orange segment grows. This coefficient ridge is distinct from the radial penalty in native J.'],
  ['both','Q','Q improves by rewarding that tradeoff.','Q = ℓ + R falls even though ℓ rises. The inner solve is doing what its own criterion asks; numerical accuracy alone does not align the two criteria.'],
  ['both','all','The improvement is real. It belongs to Q.','Regularization may intentionally make this tradeoff. The diagnosed result does not establish that every refit is harmful, nor that a candidate improves unseen forces.']
];
const ready = () => !!data && !failed && document.body.dataset.optimizationReady === 'true';
const finite = value => typeof value === 'number' && Number.isFinite(value);
const near = (a,b,tol=1e-13) => Math.abs(a-b) <= tol;
function validate(d) {
  if (d.schema !== 'proton-scientific-finale-v1' || d.source?.sha256 !== '91ba4b11b43a6966b2e1cc4ef43eef765bedd58a7de1f0975ae14b2550185131' || d.normalization !== 60 || d.system !== 'ROW_EXACT_FIXED_D') throw Error('Unreviewed schema or source');
  if (d.rows?.map(r=>r.state).join() !== 'S1c,S2') throw Error('Wrong compared states');
  for (const r of d.rows) {
    for (const k of ['ell','R','Q']) {
      const v=Number(r[k]), cell=root.querySelector(`[data-sf-exact="${r.state}-${k}"]`);
      if (!finite(v) || v < 0 || !cell || r[k] !== cell.dataset.value) throw Error('Data differ from the verified static figure');
    }
    if (!near(Number(r.ell)+Number(r.R),Number(r.Q),1e-17)) throw Error('Q is not ell plus R');
  }
  const [a,b]=d.rows;
  if (!(Number(b.ell)>Number(a.ell) && Number(b.R)<Number(a.R) && Number(b.Q)<Number(a.Q)) || !near(d.q_drop_percent,100*(Number(a.Q)-Number(b.Q))/Number(a.Q),1e-10)) throw Error('Incorrect tradeoff');
  if (d.axis_max !== 0.004 || d.native.S3 !== null || d.native.target !== 'ROW_EXACT_FIXED_D' || !near(d.native.S2q-d.native.S2,d.native.S2q_minus_S2,1e-18)) throw Error('Native comparison scope');
  const q=d.direction;
  if (![q.l0,q.a,q.b].every(finite) || q.a<=0 || q.b<=0 || q.alpha_min!==0 || q.alpha_max!==1 || q.minimum_on_domain!==0 || q.kind!=='DERIVED_QUADRATIC_NOT_PHYSICAL_TRAJECTORY' || !near(q.l0+q.a+q.b/2,Number(b.ell),1e-15)) throw Error('Invalid derived curve');
  if (d.counterexample.delta_J>=0 || d.cov.origin!=='S1c' || d.cov.native_evaluated!==false || d.cov.superiority!==false || d.limits.T2_executed!==false || d.limits.private_recovery_available!==false || d.limits.causes_prior_seed_results!==false || d.limits.regularization_always_harmful!==false || d.metric_transport.global_gauge_invariance!==false) throw Error('Unsupported scientific claim');
  return d;
}
function stop() {
  if (timer !== null) clearTimeout(timer);
  timer=null;playing=false;
  if ($('sf-play')) { $('sf-play').textContent='Play explanation';$('sf-play').setAttribute('aria-pressed','false'); }
}
function show(i,manual=true) {
  if (!ready() || !Number.isInteger(i) || i<0 || i>=steps.length) return false;
  if (manual) stop();
  index=i;
  const [state,focus,title,text]=steps[i], stage=root.querySelector('.sf-stage');
  stage.dataset.sfState=state;stage.dataset.sfFocus=focus;
  stepButtons.forEach((b,n)=>b.setAttribute('aria-pressed',String(n===i)));
  $('sf-narrative-title').textContent=title;$('sf-narrative-text').textContent=text;
  $('sf-progress').textContent=`${i+1} / ${steps.length} · two stored states`;
  return true;
}
function play() {
  if (!ready() || motion.matches) return;
  if (playing) {stop();return;}
  if (index===steps.length-1) show(0);
  playing=true;$('sf-play').textContent='Pause explanation';$('sf-play').setAttribute('aria-pressed','true');
  const tick=()=>{
    if (!ready() || !page.classList.contains('active') || document.hidden || motion.matches) {stop();return;}
    if (index>=steps.length-1) {stop();return;}
    show(index+1,false);
    if (index>=steps.length-1) stop(); else timer=setTimeout(tick,2400);
  };
  timer=setTimeout(tick,2400);
}
function alpha(value) {
  if (!ready() || !finite(value) || value<0 || value>1) return false;
  const q=data.direction, loss=q.l0+q.a*value+q.b*value*value/2;
  $('sf-alpha').value=String(value);$('sf-alpha-value').textContent=value.toFixed(2);
  $('sf-loss-value').textContent=loss.toPrecision(10);
  $('sf-alpha').setAttribute('aria-valuetext',`Alpha ${value.toFixed(2)}; calculated row loss ${loss.toPrecision(6)}`);
  $('sf-curve-marker').setAttribute('cx',String(52+584*value));$('sf-curve-marker').setAttribute('cy',String(20+182*(1-loss/.0008)));
  return true;
}
function syncReady() {
  const enabled=ready();
  buttons.forEach(b=>{b.disabled=!enabled;});
  if ($('sf-alpha')) $('sf-alpha').disabled=!enabled;
  if (!enabled) stop();
  if (enabled) {
    $('sf-play').disabled=motion.matches;
    $('sf-load-status').textContent=motion.matches?'Saved-data controls are ready. Reduced motion: use the manual steps; no automatic playback.':'Saved-data controls are ready. The reader explains two stored states; the alpha curve is calculated from saved coefficients.';
  } else if (failed || document.body.dataset.optimizationReady==='error') {
    $('sf-load-status').textContent='Interactive data unavailable or inconsistent. The verified static figure, exact table, definitions and conclusion remain readable.';
  }
}
if (root && page) {
  stepButtons.forEach(b=>b.addEventListener('click',()=>show(Number(b.dataset.sfStep))));
  $('sf-play').addEventListener('click',play);
  $('sf-prev').addEventListener('click',()=>show(Math.max(0,index-1)));
  $('sf-next').addEventListener('click',()=>show(Math.min(steps.length-1,index+1)));
  $('sf-reset').addEventListener('click',()=>{show(0);alpha(0);});
  root.querySelector('.sf-reader').addEventListener('keydown',e=>{
    if (!ready() || !['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
    e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?5:Math.max(0,Math.min(5,index+(e.key==='ArrowLeft'?-1:1)));
    show(next);stepButtons[next].focus({preventScroll:true});
  });
  $('sf-alpha').addEventListener('input',e=>alpha(Number(e.target.value)));
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  new MutationObserver(()=>{if(!page.classList.contains('active'))stop();}).observe(page,{attributes:true,attributeFilter:['class']});
  new MutationObserver(syncReady).observe(document.body,{attributes:true,attributeFilter:['data-optimization-ready']});
  motion.addEventListener('change',()=>{stop();syncReady();});
  fetch('data/finale.json').then(r=>{if(!r.ok)throw Error('Missing finale data');return r.json();}).then(d=>{data=validate(d);syncReady();if(ready())show(5,false);}).catch(()=>{failed=true;syncReady();});
  window.scientificFinale={selectStep:show,setAlpha:alpha,stop,getState:()=>({ready:ready(),index,playing,reducedMotion:motion.matches,failed})};
}
