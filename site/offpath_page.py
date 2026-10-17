"""Editorial extension generated exclusively from the verified study payload."""
from html import escape
import math
from pages import fallback

LABELS={'OO_breathing':'O–O breathing','C_skeletal_bend':'Carbon skeletal bend','H_lateral':'Lateral hydrogen','H_out_of_plane':'Out-of-plane hydrogen'}


def number(x,d=6):
    return f'{x:+.{d}f}'.replace('-','−')


def table(caption,headers,rows):
    body=''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)
    return '<div class="table-wrap" tabindex="0" role="region" aria-label="'+escape(caption)+'"><table><caption>'+escape(caption)+'</caption><thead><tr>'+''.join('<th scope="col">'+escape(s)+'</th>' for s in headers)+'</tr></thead><tbody>'+body+'</tbody></table></div>'


def signed_plot(rows):
    # A readable static fallback; JS redraws at actual container width without shifting data.
    w,h=760,330;l,r,lo,hi=76,108,-.52,.18
    x=lambda v:l+(v-lo)/(hi-lo)*(w-l-r)
    parts=[f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="All five signed primary PBE14 contrasts; negative favors Targeted"><title>Targeted minus Basin at 8000 steps, transition region, eV/Å</title>']
    for t in [-.5,-.4,-.3,-.2,-.1,0,.1]:
        parts.append(f'<line x1="{x(t)}" x2="{x(t)}" y1="35" y2="268" class="off-grid"/><text x="{x(t)}" y="290" text-anchor="middle" class="off-svg-axis">{t:g}</text>')
    parts.append(f'<line x1="{x(0)}" x2="{x(0)}" y1="28" y2="268" class="off-zero"/>')
    for i,row in enumerate(rows):
        y=57+i*46;v=row['targeted_minus_basin_eV_A'];kind='targeted' if v<0 else 'basin';xx=x(v)
        mark=f'<path d="M{xx} {y-6}l6 6 -6 6 -6 -6Z"/>' if v<0 else f'<circle cx="{xx}" cy="{y}" r="5.5"/>'
        parts.append(f'<g class="off-seed-mark {kind}" data-off-seed="{i}"><text x="5" y="{y+4}" class="off-svg-axis">Seed {i}</text><line x1="{x(0)}" x2="{xx}" y1="{y}" y2="{y}" class="off-contrast-line"/>{mark}<text x="{w-4}" y="{y+4}" text-anchor="end" class="off-svg-value">{number(v,6)}</text></g>')
    parts.append(f'<text x="{l}" y="320" class="off-svg-axis">← Targeted lower</text><text x="{w-r}" y="320" text-anchor="end" class="off-svg-axis">Basin lower →</text></svg>')
    return ''.join(parts)


def slope_static(b,region):
    rows=[r for r in b['cell_means'] if r['region']==region];upper=.36 if region=='TRANSITION_CENTER' else .08
    w,h,l,r,top,bottom=560,270,60,105,35,53
    y=lambda v:top+(upper-v)/upper*(h-top-bottom)
    parts=[f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Two finite budgets; mean of five seeds"><title>{region}: both model branches and two budgets</title>']
    for t in ([0,.1,.2,.3] if region=='TRANSITION_CENTER' else [0,.02,.04,.06,.08]):
        parts.append(f'<line x1="{l}" x2="{w-r}" y1="{y(t)}" y2="{y(t)}" class="off-grid"/><text x="{l-12}" y="{y(t)+4}" text-anchor="end" class="off-svg-axis">{t:g}</text>')
    for branch in ['basin','targeted']:
        vals=[next(r['force_RMSE_eV_A'] for r in rows if r['branch']==branch and r['budget']==cap) for cap in [2000,8000]]
        parts.append(f'<g class="{branch}"><path d="M{l+22} {y(vals[0])}L{w-r} {y(vals[1])}" class="off-slope-line"/>')
        for xx,yy in [(l+22,y(vals[0])),(w-r,y(vals[1]))]:
            parts.append(f'<path d="M{xx} {yy-5}l5 5 -5 5 -5 -5Z"/>' if branch=='targeted' else f'<circle cx="{xx}" cy="{yy}" r="5"/>')
        parts.append(f'<text x="{w-r+12}" y="{y(vals[1])+4}" class="off-svg-value">{vals[1]:.4f}</text></g>')
    for xx,cap in [(l+22,2000),(w-r,8000)]:parts.append(f'<text x="{xx}" y="{h-24}" text-anchor="middle" class="off-svg-axis">{cap}</text>')
    parts.append(f'<text x="{(w+l-r)/2}" y="{h-3}" text-anchor="middle" class="off-svg-axis">Maximum main optimizer steps</text></svg>')
    return ''.join(parts)


def direction_static(b):
    upper=math.ceil(max(r['force_RMSE_eV_A'] for r in b['block_rows'])*10)/10
    parts=[]
    for mode in LABELS:
        count='1 geometry' if mode=='H_out_of_plane' else '2 geometries'
        row='<div class="off-block-row"><div class="off-block-label">'+LABELS[mode]+'<small>'+count+'</small></div>'
        for branch in ['basin','targeted']:
            rr=[r['force_RMSE_eV_A'] for r in b['block_rows'] if r['region']=='TRANSITION_CENTER' and r['budget']==8000 and r['branch']==branch and r['mode']==mode]
            value=math.fsum(rr)/len(rr)
            row+=f'<div class="off-block-pair"><span>{branch.title()}</span><div class="off-block-track" aria-hidden="true"><div class="off-block-fill {branch}" style="width:{value/upper*100}%"></div></div><span class="off-block-value">{value:.6f}</span></div>'
        parts.append(row+'</div>')
    return ''.join(parts)+f'<p class="off-direction-axis">Shared bar scale: 0–{upper:.1f} eV/Å.</p>'


def render(d):
    b=d['benchmark'];primary=b['primary'];selected=next(x for x in b['geometries'] if x['id']=='T01p')
    source=d['source_url'];verifier=source.split('/tree/')[0]+'/blob/'+d['source_ref']+'/tools/verify_pbe14_offpath.py'
    means=table('Mean of five matched initialization seeds; block-averaged force RMSE / eV/Å',['Region','Cap','Basin60','Targeted60'],
        [[region.replace('_',' ').title(),cap]+[f"{next(r['force_RMSE_eV_A'] for r in b['cell_means'] if r['region']==region and r['budget']==cap and r['branch']==branch):.9f}" for branch in ['basin','targeted']] for region in ['TRANSITION_CENTER','BASIN_LEFT'] for cap in [2000,8000]])
    exact=table('Primary PBE14 transition contrast at cap 8000; exact seed identities',['Index','64-bit seed','Basin','Targeted','Targeted − Basin'],
        [[r['seed_index'],r['seed_u64'],f"{r['basin']:.9f}",f"{r['targeted']:.9f}",number(r['targeted_minus_basin_eV_A'],9)] for r in primary['contrasts']])
    cases=table('All 280 saved model–geometry force comparisons; eV/Å',['Seed','Branch','Cap','Geometry','Block','Component RMSE','Max |component|'],
        [[r['seed_index'],r['branch'],r['budget'],r['candidate_id'],LABELS[r['mode']],f"{r['force_RMSE_eV_A']:.9f}",f"{r['max_component_abs_eV_A']:.9f}"] for r in b['case_rows']])
    contribution=next(x['fraction_of_signed_primary'] for x in b['direction_contributions'] if x['mode']=='OO_breathing')*100
    geomopts=''.join(f'<option value="{g["id"]}"'+(' selected' if g['id']=='T01p' else '')+'>'+g['id']+' · '+LABELS[g['mode']]+'</option>' for g in b['geometries'])
    geometrytable=table('Fourteen fixed local geometries; not a trajectory',['ID','Region','Direction','Sign','Anchor image','qPT / Å','O–O / Å'],
        [[g['id'],g['region'],LABELS[g['mode']],g['sign'],g['anchor_image'],f"{g['q']:.6f}",f"{g['roo']:.6f}"] for g in b['geometries']])
    nearest=table('Nearest historical configuration under the archived alignment screen',['ID','Nearest source','Nearest index','Aligned RMS / Å','Within 0.020 Å'],
        [[x['id'],x['nearest_source'],x['nearest_index'],x['nearest_aligned_RMS_A'],x['close_0p02']] for x in d['nearest_geometry']])
    return f'''<section id="offpath" data-page class="page offpath-page">
<div class="page-head offpath-head"><p class="eyebrow">10 / A later, prespecified local test</p>
<h1>The same data budget.<br><em>A different answer off the path.</em></h1>
<p class="lede">A favorable path fit is only the start. Fourteen nearby geometries, twenty saved models and two optimization budgets reveal where the comparison holds—and where it changes.</p></div>
<div class="offpath-ribbon"><span>14 PBE reference geometries</span><span>20 fixed model endpoints</span><span>5 paired initializations</span><span>No new calculations in this exhibit</span></div>
<div id="offpath-load-status" class="small" role="status">The complete numerical results below are available without JavaScript.</div>
<div class="off-orientation"><div class="off-orientation-copy"><p class="eyebrow">01 / Leave the line, keep the question</p><h2>Near two anchors.<br>Along four directions.</h2><p>Seven configurations near the left minimum. Seven near the central transition image. Three signed pairs and one out-of-plane singleton in each region.</p><p>These are actual stored geometries, not frames in a simulated trajectory. The largest prescribed single-atom displacement is 0.075 Å.</p><div class="off-mode-list"><span>01 · O–O breathing <small>± pair</small></span><span>02 · Carbon skeletal bend <small>± pair</small></span><span>03 · Lateral hydrogen <small>± pair</small></span><span>04 · Out-of-plane hydrogen <small>+ only</small></span></div><p class="small">Four blocks receive equal weight. The singleton is not duplicated to manufacture a pair.</p></div>
<div class="panel off-geometry-panel"><div class="panel-heading"><span class="micro">Frozen local geometry</span><strong id="off-geometry-id">T01p · TRANSITION</strong></div><div id="offpath-molecule" class="molecular-stage" role="img" aria-label="Selected saved PBE14 molecular geometry">{fallback(selected['xyz'])}</div>
<div class="off-geometry-readout"><span>qPT <strong id="off-q">{selected['q']:.4f}</strong> Å</span><span>O–O <strong id="off-roo">{selected['roo']:.4f}</strong> Å</span></div>
<div class="controls off-controls"><label>Inspect saved geometry <select id="off-geometry">{geomopts}</select></label><button id="off-view-reset" type="button">Reset view</button></div><p class="stage-caption">Drag to rotate. No interpolation between PBE14 geometries; no physical time. Atom IDs and the original renderer are unchanged.</p></div></div>
<details class="data-table"><summary>Inspect the 14 coordinates, roles and nearest-neighbor limitations</summary>{geometrytable}{nearest}<p class="small">The local anchors were already known. Geometric proximity is disclosed, not turned into a claim of independent global validation.</p></details>
<div class="off-chapter-head"><p class="eyebrow">02 / The predeclared primary comparison</p><h2>Four pairs favor Targeted.<br><em>The fifth stays on the page.</em></h2><p>Transition-region block-averaged force RMSE, cap 8000. Every line below is one initialization pair—not a new allocation of training data.</p></div>
<div class="off-primary-layout"><div class="chart-panel"><div class="panel-heading"><span class="micro">Targeted − Basin / eV/Å</span><span class="badge">8000 · transition</span></div><div id="off-primary-chart" class="off-chart off-primary-chart">{signed_plot(primary['contrasts'])}</div><div class="controls off-reveal-controls"><button id="off-reveal" type="button" aria-pressed="false">▷ Reveal five pairs</button><button id="off-reveal-reset" type="button">Show all</button><label class="off-progress-label" for="off-progress">Reveal</label><input id="off-progress" type="range" min="0" max="1" step="0.01" value="1"><span id="off-reveal-status" class="small" aria-live="polite">All five pairs visible</span></div><p class="stage-caption">Negative: Targeted lower. Positive: Basin lower. Fixed axis throughout the reveal; all exact numbers remain available.</p></div>
<aside class="off-primary-aside"><p class="micro">Descriptive, not a win probability</p><strong class="off-large-number">{primary['targeted_better_count']}<span> / 5</span></strong><div class="off-key-number"><span>Mean paired contrast</span><strong>{number(primary['mean'],6)}</strong><small>eV/Å</small></div><div class="off-key-number"><span>Median paired contrast</span><strong>{number(primary['median'],6)}</strong><small>eV/Å</small></div><p class="small">This is not the original <a href="#seeds">3/5 comparison</a>. That figure concerns both original NEB metrics; this one concerns a later, single PBE14 force endpoint.</p></aside></div>
<details class="data-table"><summary>Read every exact seed and primary contrast</summary>{exact}</details>
<p class="chapter-source">Sources: <a href="{source}/results/PRIMARY_PAIRED_SEEDS.tsv">Versioned primary table</a> · <a href="data/offpath/PRIMARY_PAIRED_SEEDS.tsv" download>Download TSV</a> · <a href="{verifier}">Independent arithmetic</a></p>
<div class="off-chapter-head"><p class="eyebrow">03 / More steps do not settle the question</p><h2>A larger budget.<br>A less uniform improvement.</h2><p>The transition gap grows largely as Basin deteriorates. Around the minimum, Basin remains lower on average. Both observations belong in the result.</p></div>
<div class="twin-panels off-budget-panels"><div class="chart-panel"><div class="panel-heading"><h3>Transition region</h3><span class="micro">eV/Å · scale 0–0.36</span></div><div id="off-budget-transition" class="off-chart">{slope_static(b,'TRANSITION_CENTER')}</div></div><div class="chart-panel"><div class="panel-heading"><h3>Near the minimum</h3><span class="micro">eV/Å · scale 0–0.08</span></div><div id="off-budget-basin" class="off-chart">{slope_static(b,'BASIN_LEFT')}</div></div></div>
<div class="legend"><span><i class="legend-dot basin"></i>Basin60</span><span><i class="legend-diamond targeted"></i>Targeted60</span><span>Means of five matched seeds. Separate labeled vertical scales.</span></div>
<div class="off-stop-note"><strong>20 / 20 · STEP_LIMIT</strong><p>These are finite-budget endpoints, not certified converged fits. The final saved model can differ from the last printed BFGS state after terminal refitting and rescaling.</p></div>
<details class="data-table"><summary>Exact means for both regions and both caps</summary>{means}</details>
<p class="chapter-source"><a href="{source}/results/BUDGET_REGION_MEANS.tsv">Region/budget source table</a> · <a href="data/offpath/BUDGET_REGION_MEANS.tsv" download>Download TSV</a> · <a href="{source.replace('pbe14_mtp20_v001','optimization_budget_v001')}/MODEL_STOP_AND_SHA256.tsv">20 endpoint identities and raw logs</a></p>
<div class="off-chapter-head"><p class="eyebrow">04 / The direction matters</p><h2>Look beneath the average.</h2><p>Each mark is a mean for one physical block. Inspect a region and budget without losing the all-seed comparison or the underlying 280 cases.</p></div>
<div class="chart-panel off-direction-panel"><div class="controls off-filters"><label>Region <select id="off-region"><option value="TRANSITION_CENTER">Transition region</option><option value="BASIN_LEFT">Near the minimum</option></select></label><label>Main cap <select id="off-cap"><option value="8000">8000 steps</option><option value="2000">2000 steps</option></select></label><label>Initialization <select id="off-seed"><option value="all">Mean of all five</option>{''.join(f'<option value="{i}">Seed {i}</option>' for i in range(5))}</select></label></div><div id="off-direction-chart" class="off-chart">{direction_static(b)}</div><p id="off-direction-description" class="small">Transition ·8000 ·mean of five seeds. O–O breathing contributes {contribution:.2f}% to the signed primary mean, not to a universal causal effect.</p></div>
<div class="off-boundary"><div><p class="eyebrow">05 / A narrower conclusion, kept intact</p><h2>Local transfer.<br>Not universal trust.</h2></div><div><p>Two fixed 60-configuration allocations. Five optimizer initializations. Four dependent local blocks per region. PBE as an internal computational reference.</p><p>The geometry test was prespecified for this comparison. It later became development data for optimizer experiments. It does not certify reactive dynamics, PES topology, an untouched global holdout or Blind12 performance.</p><p><span class="badge">SEED_SENSITIVE</span> <span class="badge">STATIC_APPLICABILITY_FAIL</span></p></div></div>
<details class="data-table"><summary>All 280 force-error records, including unfavorable cases</summary>{cases}</details>
<div class="off-downloads"><a class="button" href="data/offpath/PER_GEOMETRY_280.tsv" download>All 280 comparisons ↓</a><a class="button" href="data/offpath/PHYSICAL_BLOCKS_160.tsv" download>Physical blocks ↓</a><a class="button" href="{source}">Frozen source package ↗</a></div>
<details class="evidence"><summary>Read the provenance and reproduction boundary</summary><div class="evidence-body"><p>Source revision: <code>{escape(d['source_ref'])}</code>. Recomputed from 14 saved PBE force blocks and 20 prediction CFGs. No new model evaluation, fitting or DFT.</p><p>Reference-coordinate serialization tolerances remain 1.1×10⁻⁶ Å (coordinate) and 2.1×10⁻⁶ Å (pair distance). Raw/public hashes distinguish path-prefix sanitation from unchanged numbers. The interrupted historical T02m job and its separately authorized recovery remain disclosed.</p><p><a href="{verifier}">Run the independent verifier</a> · <a href="{source}/SOURCE_TO_PUBLIC_MANIFEST.tsv">Source/public SHA map</a> · <a href="{source}/INPUT_MANIFEST.json">Frozen input hashes</a> · <a href="data/offpath.json">Complete browser payload</a></p><pre><code>python3 tools/verify_pbe14_offpath.py
python3 tools/verify_optimizer_budget.py</code></pre></div></details>
</section>'''


def extend_document(document,d):
    if 'id="offpath"' in document:raise ValueError('Duplicate offpath section')
    document=document.replace('</head>','<link rel="stylesheet" href="offpath.css"><script type="module" src="offpath.mjs"></script></head>',1)
    document=document.replace('</nav>','<a href="#offpath" data-route="offpath">Off the path <span aria-hidden="true">↗</span></a></nav>',1)
    return document.replace('</main>',render(d)+'</main>',1)
