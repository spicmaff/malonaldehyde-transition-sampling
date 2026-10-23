"""Source-verified editorial layer. Frozen experiments and their payloads stay intact."""
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '76e0e22967f408480b5a713d8f94f6c9e9981105'
ORDER = ['overview', 'molecule', 'sampling', 'landscape', 'seeds', 'offpath',
         'train119', 'forces', 'optimization', 'story', 'longread', 'reproduce']
LABELS = ['Overview', 'The molecule', 'The data', 'Energy profiles', 'Five seeds',
          'Off the path', 'Two verdicts', 'Inside the forces', 'Optimization',
          'The story', 'Read the essay', 'Evidence']
ESSAY_SCOPE = ('This essay connects five distinct studies of one molecule. '
               'Geometry and force comparisons use saved calculations; optimizer examples '
               'use published summary values. The goal is to understand what each test '
               'reveals about a model, rather than to claim experimental accuracy.')


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Editorial anchor changed: ' + old[:100])
    return text.replace(old, new, 1)


class Pages(HTMLParser):
    """Locate complete page sections, including Optimization's nested sections."""
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0]
        self.lines += [m.end() for m in re.finditer('\n', source)]
        self.depth = 0
        self.current = None
        self.spans = {}
        self.feed(source)

    def position(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag != 'section':
            return
        attrs = dict(attrs)
        self.depth += 1
        if 'data-page' in attrs:
            if self.current:
                raise ValueError('Nested page')
            self.current = (attrs['id'], self.depth, self.position())

    def handle_endtag(self, tag):
        if tag != 'section':
            return
        if self.current and self.current[1] == self.depth:
            key, _, start = self.current
            self.spans[key] = (start, self.position() + len('</section>'))
            self.current = None
        self.depth -= 1


def table(headers, rows, caption):
    return '<div class="ed-table-scroll" tabindex="0" role="region" aria-label="' + escape(caption, quote=True) + '"><table><caption>' + caption + '</caption><thead><tr>' + ''.join(
        '<th scope="col">' + escape(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join(('<th scope="row">' if i == 0 else '<td>') + escape(str(v)) +
                            ('</th>' if i == 0 else '</td>') for i, v in enumerate(row)) + '</tr>' for row in rows
        ) + '</tbody></table></div>'


def coverage_svg(data, branch):
    """Static, isotropic-in-each-axis descriptor plot; same domain in both panels."""
    x = lambda q: 62 + (q + .7) / 1.4 * 456
    y = lambda r: 294 - (r - 2.37) / .19 * 250
    bits = ['<svg class="ed-coverage-static" viewBox="0 0 550 350" role="img" aria-label="Saved training geometries and nine PBE path supports on common axes">',
            '<title>Training coverage and the relaxed PBE path; O–O training floor 2.479 Å</title>']
    for r in [2.40, 2.45, 2.50, 2.55]:
        bits.append(f'<path d="M62 {y(r)}H518" class="chart-grid"/><text x="52" y="{y(r)+4}" text-anchor="end" class="chart-axis">{r:.2f}</text>')
    for q in [-.5, 0, .5]:
        bits.append(f'<text x="{x(q)}" y="318" text-anchor="middle" class="chart-axis">{q:g}</text>')
    floor = min(p['roo'] for p in data['sampling'][branch])
    bits.append(f'<path d="M62 {y(floor)}H518" class="ed-floor"/>')
    for p in data['sampling'][branch]:
        color = 'var(--muted)' if p['shared'] else 'var(--basin)' if branch == 'basin' else 'var(--targeted)'
        xx, yy = x(p['q']), y(p['roo'])
        if branch == 'targeted' and not p['shared']:
            bits.append(f'<path d="M{xx} {yy-4}l4 4-4 4-4-4Z" fill="{color}"/>')
        else:
            bits.append(f'<circle cx="{xx}" cy="{yy}" r="3.5" fill="{color}" opacity="{.75 if p["shared"] else 1}"/>')
    path = ' '.join(('M' if i == 0 else 'L') + f'{x(p["q"])} {y(p["roo"])}' for i, p in enumerate(data['molecule']))
    bits.append(f'<path d="{path}" class="ed-reference-path"/>')
    for p in data['molecule']:
        bits.append(f'<rect x="{x(p["q"])-3}" y="{y(p["roo"])-3}" width="6" height="6" fill="var(--pbe)"/>')
    bits += ['<text x="62" y="20" class="chart-title">O1–O8 distance / Å</text>',
             '<text x="290" y="344" text-anchor="middle" class="chart-axis">Proton-transfer coordinate qPT / Å</text></svg>']
    return ''.join(bits)


def scene(data, kind):
    from pages import fallback
    m = data['molecule'][4]
    control = ('<label for="ed-sampling-image">Saved PBE image</label><input id="ed-sampling-image" type="range" min="0" max="8" step="1" value="4">'
               if kind == 'sampling' else '<p class="small">Use Selected image above, or choose a point on the energy profile.</p>')
    return f'''<div class="ed-linked-scene"><div class="ed-mini-stage"><div id="ed-{kind}-molecule" class="molecular-stage" role="img" aria-label="Selected saved PBE geometry of malonaldehyde">{fallback(m['xyz'])}</div></div><div class="ed-scene-copy"><p class="eyebrow">One geometry · linked views</p><h2>{'The missing contraction.' if kind == 'sampling' else 'Read the structure behind the point.'}</h2><div class="ed-scene-control js-control">{control}</div><output id="ed-{kind}-readout" class="ed-distances" aria-live="polite">Image 5 / 9 · qPT {m['q']:.4f} Å · O1–O8 {m['roo']:.4f} Å<br>O1–H2 {m['left']:.4f} Å · H2–O8 {m['right']:.4f} Å</output><p class="small">Saved coordinates only. Drag to rotate; focus the molecule and use arrow keys. Home restores the view.</p></div></div>'''


def refine_document(document, data, findings):
    g, off, opt = (findings[k] for k in ('geometry', 'offpath', 'optimization'))
    document = once(document, '<h1>One proton.<br><em>Several tests<br> of trust.</em></h1>',
                    '<h1>One proton.<br><em>Where should<br>the data go?</em></h1>')
    document = once(document, 'A small molecule. Two ways to place the training data. And a much harder question: when should we trust a machine-learned potential?',
                    'Malonaldehyde: two Moment Tensor Potentials, 60 training configurations each. Compare 24 additions near the minima with 24 along an aligned-endpoint tube, then test both against saved PBE energies and forces.')
    document = once(document, 'A computational chemistry case study', 'An interactive study in computational chemistry')
    document = once(document, '<p class="fineprint">An explorable account of saved calculations.<br>No live molecular simulation. No invented physics.</p>',
                    '<p class="fineprint">Explore saved calculations, one claim at a time.<br>Every scene connects a question, a measurement and its limits.</p>')
    document = once(document, 'A convincing fit is a beginning.<br><em>It is not the final verdict.</em>',
                    'Which errors improve?<br><em>Under which test?</em>')
    study_map = '''<div class="ed-study-map"><div class="ed-map-intro"><p class="eyebrow">Five studies, one evolving question</p><h2>A good fit is<br><em>the beginning.</em></h2><p>Follow what changed—and what each test can actually establish.</p></div><ol>
<li><a href="#landscape"><span class="ed-study-id">A · Train60</span><strong>Place the labels</strong><span>One preserved model pair on nine saved path images.</span></a></li>
<li><a href="#seeds"><span class="ed-study-id">B · Five seeds</span><strong>Repeat the training</strong><span>Five paired initializations; the data allocations stay fixed.</span></a></li>
<li><a href="#offpath"><span class="ed-study-id">C · PBE14</span><strong>Leave the path</strong><span>Four perturbation directions and two training budgets.</span></a></li>
<li><a href="#train119"><span class="ed-study-id">D · Train119</span><strong>Test applicability</strong><span>Adaptive development, then a fixed coverage diagnostic.</span></a></li>
<li><a href="#optimization"><span class="ed-study-id">E · Optimizer</span><strong>Inspect the update</strong><span>Separate the native objective, saved-row loss and external forces.</span></a></li>
</ol></div>'''
    document = once(document, '<div class="editorial-note">', study_map + '<div class="editorial-note">')
    document = once(document, 'Both original models saw 36 shared configurations. The other 24 labels were placed near the minima or toward the proton-transfer region.',
                    'Two Moment Tensor Potentials, 60 labels each: 36 shared geometries plus 24 different additions. The relaxed PBE path reveals what the transition-directed tube misses.')
    for branch in ('basin', 'targeted'):
        pattern = rf'(<div id="sampling-{branch}"[^>]*>)(</div>)'
        document, count = re.subn(pattern, lambda m: m[1] + coverage_svg(data, branch) + m[2], document)
        if count != 1:
            raise ValueError('Sampling chart anchor changed')
    legend = '<span class="ed-path-key"><i></i>Saved PBE path · squares</span><span class="ed-floor-key"><i></i>Training O–O minimum</span>'
    marker = '<span><i class="legend-diamond targeted"></i>Targeted additions</span></div>'
    document = once(document, marker, marker[:-6] + legend + '</div>' + scene(data, 'sampling') + f'''
<div class="ed-finding" id="ed-geometry-gap"><p class="eyebrow">Geometry audit · recomputed from saved coordinates</p><h2>Transition-directed is not<br><em>path-covering.</em></h2><div class="ed-number-pair"><span><strong>{g['training_OO_range_A']['basin'][0]:.3f}</strong> Å · training minimum O–O</span><span><strong>{g['central_PBE_OO_A']:.3f}</strong> Å · central PBE O–O</span></div><p>All seven internal PBE images lie below the training O–O range. At the center, the gap is {g['OO_gap_below_training_minimum_A']:.3f} Å. <code>generate_tube</code> perturbs a straight interpolation between aligned minima; it does not follow the relaxed PBE path.</p><p>The original advantage remains a result on the saved evaluation path. It does not demonstrate coverage of transition geometry, nor isolate sampling along a fully relaxed reaction coordinate. These two descriptors reveal a gap; they cannot certify coverage in all 27 Cartesian dimensions.</p><p class="chapter-source">Source: frozen Train60 coordinates, nine PBE supports and <code>generate_tube</code>. <a href="data/editorial.json">Recomputed findings and source hashes</a> · <a href="#reproduce">Methods and evidence</a></p></div>''')
    document = once(document, '<div id="energy-readout"', scene(data, 'energy') + '<div id="energy-readout"') if '<div id="energy-readout"' in document else once(document, '<p id="energy-readout"', scene(data, 'energy') + '<p id="energy-readout"')
    budget_rows = []
    cells = {(r['region'], r['budget'], r['branch']): r['force_RMSE_eV_A'] for r in off['cell_means']}
    for region, label in [('TRANSITION_CENTER', 'Transition'), ('BASIN_LEFT', 'Near minimum')]:
        for budget in (2000, 8000):
            b, t = (cells[region, budget, branch] for branch in ('basin', 'targeted'))
            budget_rows.append([label, budget, f'{b:.6f}', f'{t:.6f}', f'{t-b:+.6f}'])
    dec = off['budget_difference_decomposition']
    sensitivity = [[r['removed_mode'].replace('_', ' '), f"{r['mean_difference_eV_A']:+.6f}", f"{r['targeted_win_count']} / 5"] for r in off['leave_one_block_out']]
    absolute = '<div class="ed-budget-audit"><h3>The absolute errors explain the widening gap.</h3>' + table(
        ['Region', 'Step cap', 'Basin / eV/Å', 'Targeted / eV/Å', 'Targeted − Basin / eV/Å'], budget_rows,
        'Mean of five seed-level endpoints; equal weights for four physical blocks. Exact saved values: downloadable PBE14 tables.') + f'''<div class="ed-arithmetic"><span><strong>{dec['basin_error_change_eV_A']:+.3f}</strong> Basin change</span><span><strong>{dec['targeted_error_change_eV_A']:+.3f}</strong> Targeted change</span><span><strong>{100*dec['basin_fraction_of_gap_growth']:.0f}%</strong> of gap growth comes from the Basin increase</span></div><p>This is an arithmetic decomposition in eV/Å. It does not establish why the models diverged: native trajectories, checkpoint selection and nonlinear parameter evolution require separate evidence. All 20 saved endpoints stopped at the step limit; neither budget is a convergence guarantee. The ten cap-2000 model hashes match the earlier five-seed Audit21 audit: these potentials are reused in a later geometry test.</p></div>'''
    document = once(document, '<div class="twin-panels off-budget-panels">', absolute + '<div class="twin-panels off-budget-panels">')
    sensitivity_html = '<div class="ed-sensitivity"><p class="eyebrow">Additional analysis · exploratory sensitivity</p><h3>How much depends on the block weights?</h3><p>O–O breathing supplies about 70% of the signed primary mean contrast. Removing it leaves a mean contrast of −0.058 eV/Å and 4/5 pairs favoring Targeted. The ordering is not equally stable under every deletion.</p>' + table(
        ['Omitted block', 'Mean contrast / eV/Å', 'Targeted lower'], sensitivity,
        'Transition region, cap 8000; reweight the three remaining blocks equally.') + f'''<p>Equal weighting of the seven individual geometries gives {off['equal_geometry_weight_sensitivity']['mean_difference_eV_A']:+.3f} eV/Å. These checks describe sensitivity; the predeclared four-block endpoint above remains the primary result.</p></div>'''
    document = once(document, '<div class="off-downloads">', sensitivity_html + '<div class="off-downloads">')
    top_limit = '''<div class="ed-evidence-limit"><span class="ed-status ed-status-aggregate">Published aggregates</span><p><strong>The complete main4500 recovery archive is unavailable.</strong> This chapter checks reported arithmetic and source locators. Missing matrices, native model states and process receipts prevent a fresh native reconstruction. The public Train60 and PBE14 arrays have a different evidence status.</p><a href="#opt-sources">What would restore reproducibility? →</a></div>'''
    # Keep the substantial disclosure outside the compact sticky chapter map.
    # Otherwise the map can cover the very playback controls it navigates to.
    document = once(document, '<div class="cin-chapter-map"', top_limit + '<div class="cin-chapter-map"')
    document = once(document, 'What 248 parameters, one periodic refit, and a safer candidate actually tell us.',
                    'What 248 parameters, one periodic refit, and a candidate with a fixed-row guarantee actually tell us.')
    document = once(document, 'One recovered diagnostic; measured saved physical states.',
                    'Published aggregate snapshots; the native model and matrix archive is unavailable.')
    delta = opt['S1c_to_S2_row_deltas']
    ledger = '<div class="ed-q-ledger"><p class="eyebrow">S1c → S2 · one fixed-row problem · all terms divided by 60</p><h3>Q falls while the data fit gets worse.</h3><div class="ed-q-terms">' + ''.join(
        f'<div><span>{label}</span><strong>{float(delta[key]):+.6f}</strong><span class="ed-q-track"><i style="width:{abs(float(delta[key]))/.0018*100:.5f}%" class="{kind}"></i></span></div>'
        for key, label, kind in [('data_loss', 'Data-loss change', 'ed-q-worse'), ('ridge_penalty', 'Penalty change', 'ed-q-lower'), ('Q', 'Total Q change', 'ed-q-total')]) + f'''</div><p>The penalty reduction outweighs the data-loss increase: ΔQ = Δloss + Δpenalty. Q decreases by {float(opt['Q_reduction_percent']):.1f}% in this reported problem. Native J is a separate weighted objective; external force error requires a separate physical evaluation.</p><p class="chapter-source">Source: public ROW_EXACT_FIXED_D aggregate table. This identity checks arithmetic; it does not reconstruct the missing matrices.</p></div>'''
    document = once(document, '<div class="opt-native-deltas">', ledger + '<div class="opt-native-deltas">')
    cov_note = f'''<div class="ed-cov-limit"><h3>A fixed-row guarantee with a demanding numerical context.</h3><p>COV regularizes the coefficient increment from the current state; the fixed-D comparison above penalizes absolute coefficients. The exact constrained minimizer cannot increase saved-row loss when A, r, the feasible subspace and the metric stay fixed, zero is feasible, and the increment penalty is nonnegative and vanishes at zero. In this quadratic problem M is positive on the feasible subspace. The comparison is ℓ(δ) ≤ ℓ(δ) + δᵀMδ ≤ ℓ(0). An approximate numerical solution must verify the achieved inequality rather than inherit an exact-solver guarantee. This does not guarantee the native objective after nonlinear updates or force accuracy on other geometries.</p><dl><div><dt>Reported coefficient increment ‖δ‖₂</dt><dd>{opt['COV']['coefficient_increment_l2']:,.0f}</dd></div><div><dt>Regularized-stack condition number</dt><dd>{opt['COV']['regularized_stack_condition_number']:.2e}</dd></div><div><dt>Candidate native energies / forces</dt><dd>Not evaluated</dd></div></dl><p>The norm depends on coefficient scaling and parameterization; its size alone is not a physical displacement or evidence of instability. Conditioning calls for residual and sensitivity checks in the stated basis. The displayed stationarity and QR/SVD residuals are published diagnostics; their underlying matrices are unavailable here. Transporting a chosen metric preserves that quadratic penalty; rebuilding a diagonal metric in a different gauge is a different policy.</p></div>'''
    document = once(document, '<div class="opt-cov-layout">', cov_note + '<div class="opt-cov-layout">')
    document = once(document, '<div class="opt-downloads">', '''<details class="ed-recovery"><summary>Minimum native recovery package for a reproducible continuation</summary><p>Release S0, S1, S1c, S2, S2q and S4 model states; the exact saved rows, targets, A, r, D and feasible-basis transforms; executable versions, build flags, commands and random seeds; native J, gradients, E/F receipts and optimizer/checkpoint logs. Verify hashes, row/atom order and units, reconstruct Q = loss + penalty, check native parity and independently evaluate any COV candidate on held-out geometries. A new run needs a new study ID and may not silently stand in for main4500.</p></details><div class="opt-downloads">''')
    passport = f'''<div class="ed-methods"><p class="eyebrow">Methods / Provenance</p><h2>Different evidence supports<br><em>different kinds of checking.</em></h2><div class="ed-evidence-tiers"><article><span class="ed-status ed-status-primary">Saved primary arrays</span><h3>Train60 · PBE14</h3><p>Coordinates, labels and predictions permit geometry and force-error recomputation. The five seeds repeat training, not the data allocation. The separate five-seed Audit21 headline can be checked from its metric table; its ten prediction arrays are not included.</p></article><article><span class="ed-status ed-status-aggregate">Published aggregates</span><h3>Optimization</h3><p>Q identities, ratios and reported inequalities can be checked from public tables. These checks do not rerun the native optimizer.</p></article><article><span class="ed-status ed-status-missing">Unavailable native archive</span><h3>main4500</h3><p>Complete matrices, model states and receipts are missing. Hashes establish identity only when the corresponding bytes are available.</p></article></div><details open><summary>PBE / NEB reference passport and numerical precision</summary><p>PBE with scalar-relativistic PSlibrary PAW pseudopotentials; isolated molecule in a 16 Å periodic cell, Γ point, 80 Ry wavefunction and 960 Ry density cutoffs. The documented electronic threshold is 10⁻¹⁰ Ry. The saved path has nine images with fixed endpoints; the source guards use automatic climbing-image selection and 0 &lt; path threshold ≤ 0.05 eV/Å.</p><p>The public material does not provide a compact cutoff, cell-size and path-discretization convergence series or a newly verified final NEB residual. A discrete maximum among nine energies is not a certified saddle, a free-energy barrier, tunneling splitting or reaction rate.</p><p>The endpoint energy difference is {findings['original']['PBE_endpoint_asymmetry_meV']:.3f} meV. This is comparable in scale to the later Train119 barrier error (~0.123 meV), but is not an uncertainty bound. The maximum relative-profile residual is larger (~0.504 meV). Extra decimals in source tables preserve arithmetic, not independently established physical accuracy.</p><p class="chapter-source"><a href="https://github.com/spicmaff/malonaldehyde-transition-sampling/blob/{BASELINE}/docs/SOFTWARE_PROVENANCE.md">Software and numerical settings</a> · <a href="data/editorial.json">Recomputed audit with source hashes</a></p></details><p class="small">This edition starts from repository commit <code>{BASELINE}</code>. New work comprises coordinate/prediction-array recomputation, aggregate arithmetic checks and presentation changes. No new DFT, NEB, molecular dynamics or model training was run.</p></div>'''
    document = once(document, '<div class="reference-ladder">', passport + '<div class="reference-ladder">')
    document = once(document, '<article class="prose">', '<article class="prose"><div class="ed-essay-note"><p class="eyebrow">Reading the historical essay after the audit</p><p>' + escape(ESSAY_SCOPE) + '</p><p><a href="#sampling">Inspect the geometry gap</a> · <a href="#offpath">Compare the later physical tests</a> · <a href="#reproduce">Check evidence availability</a></p></div>')
    # A fixed comparison axis must never change when a model is hidden.
    document = once(document, '<div id="energy-residual"', '<div id="energy-residual"')
    document = once(document, '</head>', '<link rel="stylesheet" href="editorial.css"></head>')
    # Reorder existing chapters, keeping every historic route and anchor.
    parser = Pages(document)
    if set(parser.spans) != set(ORDER):
        raise ValueError('Unexpected editorial routes')
    sections = {}
    for i, key in enumerate(ORDER):
        start, end = parser.spans[key]
        content = document[start:end]
        content = re.sub(r'(<p class="eyebrow">)\d{2} / ', lambda m: m[1] + f'{i+1:02d} / ', content, count=1)
        if key != 'overview':
            badge = {'molecule':'Molecule / reference', 'sampling':'A / Train60', 'landscape':'A / Train60', 'seeds':'B / Five seeds', 'offpath':'C / PBE14', 'train119':'D / Train119', 'forces':'D / Train119', 'optimization':'E / Optimizer', 'story':'Original six-scene edition', 'longread':'Research essay', 'reproduce':'Methods / Provenance'}[key]
            content = content.replace('>', '><div class="ed-chapter-tag">' + badge + '</div>', 1)
        links = '<div class="ed-page-turn"><a href="#' + ORDER[max(0, i-1)] + '">← ' + LABELS[max(0, i-1)] + '</a>'
        if i + 1 < len(ORDER):
            links += '<a href="#' + ORDER[i+1] + '">Next: ' + LABELS[i+1] + ' →</a>'
        content = content[:-10] + links + '</div></section>'
        sections[key] = content
    starts, ends = zip(*parser.spans.values())
    document = document[:min(starts)] + ''.join(sections[k] for k in ORDER) + document[max(ends):]
    nav = re.search(r'<nav[^>]*>.*?</nav>', document, re.S)
    links = {m[1]: m[0] for m in re.finditer(r'<a[^>]*data-route="([^"]+)"[^>]*>.*?</a>', nav[0])}
    if set(links) != set(ORDER):
        raise ValueError('Unexpected chapter navigation')
    ordered_nav = re.sub(r'>.*</nav>', '>' + ''.join(links[k] for k in ORDER) + '</nav>', nav[0], flags=re.S)
    document = document[:nav.start()] + ordered_nav + document[nav.end():]
    contents = '<div class="ed-mobile-contents wrap js-control"><label for="ed-contents">Explore the study</label><select id="ed-contents">' + ''.join(
        '<option value="' + key + '">' + str(i+1).zfill(2) + ' / ' + LABELS[i] + '</option>' for i, key in enumerate(ORDER)) + '</select></div>'
    document = once(document, '</header>', contents + '</header>')
    return document


def build(document, data, out):
    sys.path.insert(0, str(ROOT / 'tools'))
    from verify_editorial_findings import verify
    findings = verify()
    stored = json.loads((ROOT / 'docs/editorial-findings.json').read_text())
    if findings != stored:
        raise ValueError('Editorial findings changed; review and regenerate explicitly')
    (out / 'data/editorial.json').write_text(json.dumps(findings, sort_keys=True, indent=2) + '\n')
    (out / 'editorial.css').write_bytes((ROOT / 'site/editorial.css').read_bytes())
    return refine_document(document, data, findings)
