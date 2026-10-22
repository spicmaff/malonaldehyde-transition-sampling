"""Source-bound finale for the existing Optimization route. Static evidence first."""
from __future__ import annotations
from html import escape
from pathlib import Path
import re


def num(x, digits=7):
    return f'{float(x):.{digits}g}'.replace('-', '−')


def once(document, old, new):
    if document.count(old) != 1:
        raise ValueError('Finale extension point is not unique: '+old[:70])
    return document.replace(old,new,1)


def link(field='$.theory.linear_system.row_loss_table', title='Source and exact fields'):
    return ('<a href="#opt-source-theory-new_main4500">'+escape(title)+' ↗</a>'
            '<span class="sf-field">'+escape(field)+'</span>')


def chart(d):
    rows=d['rows']; left=104; width=632; upper=d['axis_max']
    grid=''.join(f'<line x1="{left+i*width/4}" y1="36" x2="{left+i*width/4}" y2="230" class="sf-grid"/><text x="{left+i*width/4}" y="265" text-anchor="middle" class="sf-axis">{i}</text>' for i in range(5))
    marks=[]
    for i,r in enumerate(rows):
        y=62+i*94;w1=float(r['ell'])/upper*width;w2=float(r['R'])/upper*width
        marks.append(f'<g data-sf-bar="{r["state"]}"><text x="0" y="{y+23}" class="sf-row-label">{r["state"]}</text><rect data-sf-metric="ell" x="{left}" y="{y}" width="{w1:.12f}" height="34" class="sf-data"/><rect data-sf-metric="R" x="{left+w1:.12f}" y="{y}" width="{w2:.12f}" height="34" class="sf-penalty"/><line data-sf-metric="Q" x1="{left+w1+w2:.12f}" y1="{y-9}" x2="{left+w1+w2:.12f}" y2="{y+43}" class="sf-total"/><text x="{left}" y="{y+58}" class="sf-caption">Q = {num(r["Q"],9)}</text></g>')
    return f'<svg viewBox="0 0 800 286" role="img" aria-labelledby="sf-chart-title sf-chart-description"><title id="sf-chart-title">The hidden tradeoff: two stored states, one fixed row problem</title><desc id="sf-chart-description">Each total Q is the sum of orange data loss and green coefficient penalty. From S1c to S2, data loss rises, the penalty falls, and Q falls. The axis is linear, from zero to 0.004. These are not native J or force RMSE.</desc>{grid}{"".join(marks)}<text x="736" y="283" text-anchor="end" class="sf-axis">×10⁻³ · fixed linear scale</text></svg>' + mobile_chart(d)



def mobile_chart(d):
    rows=[]
    for r in d['rows']:
        rows.append(f'<div class="sf-mobile-row" data-sf-bar="{r["state"]}"><div><strong>{r["state"]}</strong><span>Q = {num(r["Q"],7)}</span></div><div class="sf-mobile-track" aria-hidden="true"><span class="sf-data" data-sf-metric="ell" style="width:{float(r["ell"])/d["axis_max"]*100:.10f}%"></span><span class="sf-penalty" data-sf-metric="R" style="width:{float(r["R"])/d["axis_max"]*100:.10f}%"></span></div></div>')
    return '<div class="sf-mobile-chart"><div class="sf-mobile-axis"><span>0</span><span>0.004 · same linear scale</span></div>'+''.join(rows)+'</div>'


def tradeoff(d):
    table=''.join('<tr><th scope="row">'+r['state']+'</th>'+''.join(f'<td data-sf-exact="{r["state"]}-{k}" data-value="{escape(r[k])}">{num(r[k],16)}</td>' for k in ('ell','R','Q'))+'</tr>' for r in d['rows'])
    delta=''.join(f'<div class="sf-delta sf-delta-{k}"><span>{label}</span><strong>{"+" if float(d["delta"][k])>0 else ""}{num(d["delta"][k],8)}</strong><small>{meaning}</small></div>' for k,label,meaning in [('ell','Δℓ · data loss','The fit gets worse'),('R','ΔR · coefficient penalty','The penalty gets smaller'),('Q','ΔQ · inner objective','The inner problem improves')])
    steps=['The incumbent','Isolate the data fit','Follow the refit','Find the tradeoff','Read the total','Keep the conclusion']
    buttons=''.join(f'<button type="button" data-sf-step="{i}" aria-pressed="false" disabled><span>{i+1:02}</span>{s}</button>' for i,s in enumerate(steps))
    return f'''<div id="opt-finale-tradeoff" class="sf-scene" role="group" tabindex="-1" aria-labelledby="sf-tradeoff-title">
<div class="sf-kicker"><span class="eyebrow">The decisive comparison</span><span class="sf-kind">Saved-row arithmetic · not a new experiment</span></div>
<div class="sf-scene-heading"><h3 id="sf-tradeoff-title">One refit.<br><em>Two different answers.</em></h3><p>The inner problem improves. The data fit gets worse. The missing piece is the coefficient penalty—not a hidden physical trajectory.</p></div>
<div class="sf-stage" data-sf-focus="all" data-sf-state="both"><div class="sf-equation"><span class="sf-ell-text">ℓ <small>data loss</small></span><b>+</b><span class="sf-r-text">R <small>coefficient penalty</small></span><b>=</b><span>Q <small>inner objective</small></span></div>
<div class="sf-chart">{chart(d)}</div><div class="sf-legend"><span><i class="sf-data"></i>ℓ · residual error</span><span><i class="sf-penalty"></i>R · coefficient ridge</span><span>│ Q · total length</span></div>
<p class="sf-scale-note">Both rows: fixed A, y and D; every term divided by 60. This is <strong>ROW_EXACT_FIXED_D</strong>, not native J or external force RMSE.</p>
<div class="sf-reader" role="group" aria-label="Read the tradeoff in six steps">{buttons}</div>
<div class="sf-playback" role="group" aria-label="Tradeoff playback"><button type="button" id="sf-play" aria-pressed="false" disabled>Play explanation</button><button type="button" id="sf-prev" disabled>← Previous</button><button type="button" id="sf-next" disabled>Next →</button><button type="button" id="sf-reset" disabled>Reset</button><span id="sf-progress">All evidence visible</span></div>
<div class="sf-narrative" aria-live="polite" aria-atomic="true"><strong id="sf-narrative-title">The improvement is real. It belongs to Q.</strong><p id="sf-narrative-text">A smaller coefficient penalty more than offsets a larger data residual. Regularization may intentionally make this tradeoff; it is not a promise of lower native J or better unseen forces.</p></div>
<p class="sf-scale-note">Only two stored row-system states. Highlights explain them; transitions are presentation, not measured intermediate states. Arrow keys, Home and End work in the six-step reader.</p></div>
<div class="sf-deltas">{delta}</div>
<div class="table-wrap sf-table" role="region" aria-label="Exact source-derived tradeoff values" tabindex="0"><table><caption>Two saved states · display rounded to 16 significant digits</caption><thead><tr><th scope="col">State</th><th scope="col">ℓ</th><th scope="col">R</th><th scope="col">Q = ℓ + R</th></tr></thead><tbody>{table}</tbody></table></div>
<p class="sf-source">{link()} <a href="data/finale.json" download>Full decimal values and derivation fields ↓</a></p>
<p id="sf-load-status" class="sf-status" role="status">The complete figure and results are available without JavaScript. Controls require both verified data payloads.</p>
</div>'''


def controls(d):
    dr=d['direction'];upper=.0008;left=52;w=584;top=20;h=182
    points=' '.join(f'{left+w*i/80:.6f},{top+h*(1-(dr["l0"]+dr["a"]*i/80+dr["b"]*(i/80)**2/2)/upper):.6f}' for i in range(81))
    origin_y=top+h*(1-dr['l0']/upper)
    return f'''<div id="opt-finale-controls" class="sf-controls-grid" tabindex="-1">
<article class="sf-control"><p class="eyebrow">Control 01 / Precision</p><h3>A more accurate solve.<br><em>Almost the same native J.</em></h3><p class="sf-control-big">{num(d['native']['S2q_minus_S2'],8)}</p><p class="sf-small">S2q − S2 · native weighted training J</p><dl class="sf-exact-pair"><dt>S2</dt><dd>{num(d['native']['S2'],16)}</dd><dt>S2q</dt><dd>{num(d['native']['S2q'],16)}</dd></dl><p>The physical S2q copy targets the high-precision <strong>ROW_EXACT_FIXED_D</strong> solution. It barely changes the elevated native objective in this episode.</p><p class="sf-boundary">The row system, captured G + D and actual captured K are three different systems. This is not simply “the same native matrix solved more accurately”.</p><p class="sf-source">{link('$.theory.main4500.states; $.theory.linear_system.systems')}</p></article>
<article class="sf-control"><p class="eyebrow">Control 02 / Direction</p><h3>A shorter step.<br><em>Still the wrong direction for ℓ.</em></h3><p>Along this fixed direction from the compensated S1c, both the initial slope and curvature are positive. Every α &gt; 0 in [0, 1] increases the row loss.</p>
<p class="sf-small">Row loss ℓ · vertical labels ×10⁻⁴</p>
<svg id="sf-curve" viewBox="0 0 668 251" role="img" aria-labelledby="sf-curve-title sf-curve-desc"><title id="sf-curve-title">Derived quadratic row loss versus alpha</title><desc id="sf-curve-desc">Calculated from saved rounded coefficients, not physical measurements. On alpha zero to one the minimum is at zero. The fixed vertical scale is zero to 0.0008.</desc><path d="M52 20V202H636" class="sf-curve-axis" fill="none"/><path d="M52 111H636 M52 20H636" class="sf-grid"/><polyline points="{points}" class="sf-curve-line" fill="none"/><circle id="sf-curve-marker" cx="52" cy="{origin_y:.6f}" r="6"/><text x="52" y="224" class="sf-axis">0 · S1c</text><text x="636" y="224" text-anchor="end" class="sf-axis">1 · toward native ridge</text><text x="43" y="205" text-anchor="end" class="sf-axis">0</text><text x="43" y="24" text-anchor="end" class="sf-axis">8</text><text x="52" y="246" class="sf-axis">α · fixed linear axes · calculated curve</text></svg>
<label class="sf-slider-label" for="sf-alpha">Inspect a calculated α <output id="sf-alpha-value" for="sf-alpha">0.00</output></label><input id="sf-alpha" type="range" min="0" max="1" step="0.01" value="0" disabled aria-describedby="sf-curve-scope"><p class="sf-row-readout">Calculated ℓ(α) <output id="sf-loss-value" for="sf-alpha">{num(dr['l0'],10)}</output></p>
<details class="sf-details"><summary>Formula, coefficients and the fixed-system boundary</summary><p>ℓ(α) = ℓ(0) + aα + ½bα²</p><p>ℓ(0) = {num(dr['l0'],16)}<br>a = {num(dr['a'],16)}<br>b = {num(dr['b'],16)}</p><p>Coefficients are saved rounded scalar diagnostics; the curve endpoint agrees with the separate high-precision row table within 10⁻¹⁵ absolute error. It is not a new least-squares solve or an interval certificate.</p></details>
<p id="sf-curve-scope" class="sf-boundary">Fixed A, y and radial block; starting from S1c. This does not test damping the complete S0 → S4 operation.</p><p class="sf-source">{link('$.theory.prediction_prox.native_ridge_direction; $.theory.prediction_prox.data_loss_incumbent')}</p></article>
</div><aside class="sf-counterexample"><span class="eyebrow">The opposite case stays visible</span><h3>At main{d['counterexample']['iteration']}, refitting improves J.</h3><p>S0 → S2: <strong>{num(d['counterexample']['delta_J'],10)}</strong>. A historical rounded summary, not a new physical replay. This is a diagnosis of one selected event—not a verdict against every refit.</p><a href="#opt-source-OBS_IXA_READER">Counterexample source ↗</a></aside>'''


def geometry():
    return '''<div id="opt-finale-geometry" class="sf-geometry" role="group" tabindex="-1" aria-labelledby="sf-geometry-title"><p class="eyebrow">Representation is not the objective</p><h3 id="sf-geometry-title">Same predictions.<br><em>A penalty that needs to travel.</em></h3><div class="sf-geometry-rail"><div><span class="micro">Old coordinates</span><p>Aβ</p><small>Penalty βᵀDβ</small></div><span aria-hidden="true">↔</span><div><span class="micro">Compensated coordinates</span><p>A′β′ = Aβ</p><small>A′ = ATᵀ · β′ = T⁻ᵀβ</small></div><span aria-hidden="true">→</span><div><span class="micro">Same chosen penalty</span><p>D′ = TDTᵀ</p><small>β′ᵀD′β′ = βᵀDβ</small></div></div><p>Conceptual coordinate diagram, not an observed parameter landscape. Under an allowed invertible transport, changing coordinates can preserve the physical predictions. Preserving a quadratic penalty requires transporting its metric too.</p><p class="sf-boundary">For the reviewed L12 graph: the allowed lower-triangular channel map induces T. Force equality additionally assumes a smooth geometry region. Fixed-composition increments use the stated 32 × 30 feasible map. Rebuilding a diagonal penalty in each frame does not establish global gauge invariance of the policy; native J also has its distinct radial penalty.</p><p><a href="#opt-source-theory-proof_register">Conditional proof register ↗</a> · <a href="#opt-source-theory-new_main4500">Saved diagnostic and metric scope ↗</a></p></div>'''


def conclusion(d):
    return f'''<section id="opt-next-study" class="opt-chapter sf-conclusion" aria-labelledby="opt-next-title" tabindex="-1"><p class="eyebrow">06 / What we actually learned</p><h2 id="opt-next-title">The improvement was real.<br><em>It belonged to a different objective.</em></h2><p class="sf-conclusion-lede">In this audited MTP refit, a lower inner Q came with a worse data fit. An accurate answer to one optimization problem is not automatically an improvement of another.</p><div class="sf-verdict"><div><span class="micro">Established in this event</span><h3>Q decreased.<br>ℓ increased.</h3><p>The reduction in coefficient penalty outweighed the increase in the residual. This is a signed balance, not an attribution of every change in native J.</p></div><div><span class="micro">Two controls</span><h3>Precision is not enough.<br>Nor is this shorter step.</h3><p>The selected high-precision row solution barely changes native J. Positive damping from S1c along the recorded ridge direction cannot decrease the corresponding row loss.</p></div><div><span class="micro">Boundary of the finding</span><h3>A diagnosis.<br>Not a universal prohibition.</h3><p>Regularization may intentionally trade fit for other properties. main50 shows the opposite direction. No universal refit frequency, external-accuracy gain or globally invariant optimizer is established.</p></div></div>
<div class="sf-connected"><h3>One proton. Different tests. Different answers.</h3><p>The original data-allocation comparison is conditional on its training protocol. Seeds change some rankings; evaluation region changes the question; an applicability warning is not a force-error measurement. The refit diagnosis adds another boundary: improvement of an inner criterion need not transfer to the original fit.</p><p>These are separate studies connected by a question of reliability. This episode does not establish the cause of the earlier seed sensitivity or basin-region errors.</p><div class="opt-next-links"><a href="#seeds">Initialization ↗</a><a href="#offpath">Evaluation region ↗</a><a href="#train119">Applicability ↗</a><a href="#reproduce">Public verification ↗</a></div></div>
<aside class="sf-future"><span class="micro">The next hypothesis—not the missing ending</span><h3>Does a more consistent update improve complete training?</h3><p>C-PROX-COV reduces saved-row loss by {d['cov']['percent']:.6f}% from the compensated incumbent S1c, not from S2. A fixed-system guarantee is not a demonstrated real-data win. T2 requires matched cost, a fixed checkpoint policy and independent physical evaluation; PBE14 is development evidence.</p><p><strong>{escape(d['limits']['visible'])}</strong></p><p>T2_NOT_AUTHORIZED_NOT_EXECUTED. The full private recovery bundle is unavailable; public scalars support arithmetic, not a fresh native reproduction.</p></aside></section>'''


def refine_document(document: str, data: dict) -> str:
    if 'id="opt-finale-tradeoff"' in document:
        raise ValueError('Finale already applied')
    old='A training run can improve between steps and still lose ground at a refit. Follow one measured boundary, separate the objective from the solve, and see how far a safer update has actually been checked.'
    document=once(document,old,'An accurate refit can worsen the original fit. In one audited event, the inner objective rewards a different tradeoff. Follow the evidence, the controls, and the exact boundary of that conclusion.')
    # Keep the established title and native snapshot contract; replace the candidate-led hero ending.
    pattern=r'<div class="opt-hero-candidate">.*?</div></div><p class="small">Fixed matrices only\..*?</p>'
    replacement=f'<div class="opt-hero-candidate"><strong>−{data["q_drop_percent"]:.2f}%</strong><div><span>inner Q · S1c → S2</span><p>Q improves while the data fit worsens.</p></div></div><p class="small">A separate fixed-row comparison, not the native-J ratio above. <a href="#opt-finale-tradeoff">Read the decisive figure ↓</a></p>'
    if len(re.findall(pattern,document,flags=re.S))!=1:
        raise ValueError('Finale hero extension mismatch')
    document=re.sub(pattern,lambda _:replacement,document,count=1,flags=re.S)
    document=once(document,'<div class="opt-native-path">',tradeoff(data)+controls(data)+'<div class="opt-native-path">')
    document=once(document,'<details class="opt-details"><summary>The objective, the 210-dimensional flag, and the qualified 240 bound</summary>',geometry()+'<details class="opt-details"><summary>The objective, the 210-dimensional flag, and the qualified 240 bound</summary>')
    document=once(document,'<div class="opt-cov-layout">','<p class="sf-candidate-boundary">Constructive continuation, not a demonstrated repair of S2. The saved COV comparison starts at compensated S1c and concerns row loss; it is separate from the native S0 → S2 jump.</p><div class="opt-cov-layout">')
    start=document.index('<section id="opt-next-study"');end=document.index('<section id="opt-sources"',start)
    document=document[:start]+conclusion(data)+'\n\n'+document[end:]
    document=once(document,'06 · The next question','06 · The conclusion')
    return once(document,'</head>','<link rel="stylesheet" href="scientific_finale.css"><script type="module" src="scientific_finale.mjs"></script></head>')


def copy_assets(out: Path) -> None:
    for suffix in ('.css','.mjs'):
        source=Path(__file__).with_suffix(suffix)
        (out/source.name).write_bytes(source.read_bytes())
