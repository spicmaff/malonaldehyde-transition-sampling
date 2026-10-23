"""Public reading edition. Figures retain their saved-data bindings and routes."""
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import math
import re

REPO = 'https://github.com/spicmaff/malonaldehyde-transition-sampling'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Elements(HTMLParser):
    """Track source spans without changing SVG, whitespace or exact data attributes."""
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source, self.stack, self.elements = source, [], []
        self.lines = [0] + [m.end() for m in re.finditer('\n', source)]
        self.feed(source)

    def pos(self):
        row, col = self.getpos()
        return self.lines[row-1] + col

    def handle_starttag(self, tag, attrs):
        start = self.pos()
        node = {'tag': tag, 'attrs': dict(attrs), 'start': start,
                'inner': start + len(self.get_starttag_text()), 'parent': self.stack[-1] if self.stack else None}
        self.elements.append(node)
        if tag in VOID:
            node.update(end=node['inner'], close=node['inner'])
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        start = self.pos()
        end = start + len(self.get_starttag_text())
        self.elements.append({'tag': tag, 'attrs': dict(attrs), 'start': start,
                              'inner': end, 'end': end, 'close': end,
                              'parent': self.stack[-1] if self.stack else None})

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1]['tag'] != tag:
            raise ValueError('Unbalanced public template: ' + tag)
        self.stack.pop().update(close=self.pos(), end=self.pos() + len(tag) + 3)

    def find(self, ident=None, cls=None, tag=None):
        found = [n for n in self.elements if (not ident or n['attrs'].get('id') == ident)
                 and (not cls or cls in n['attrs'].get('class', '').split()) and (not tag or n['tag'] == tag)]
        if len(found) != 1:
            raise ValueError(f'Public template anchor: {ident or cls or tag}, found {len(found)}')
        return found[0]


def fragment(source, **query):
    node = Elements(source).find(**query)
    return source[node['start']:node['end']]


def change(source, replacement, **query):
    node = Elements(source).find(**query)
    return source[:node['start']] + replacement + source[node['end']:]


def inside(source, replacement, **query):
    node = Elements(source).find(**query)
    return source[:node['inner']] + replacement + source[node['close']:]


def details(title, body, ident=''):
    attr = f' id="{ident}"' if ident else ''
    return f'<details{attr} class="pop-details"><summary>{title}</summary><div class="pop-details-body">{body}</div></details>'


def section(ident, title, body, kicker='A closer look'):
    return f'<section id="{ident}" class="opt-chapter" tabindex="-1"><div class="opt-chapter-heading"><p class="eyebrow">{kicker}</p><h2>{title}</h2></div>{body}</section>'


def takeaway(title, text):
    return f'<div class="pop-takeaway"><span class="pop-takeaway-mark" aria-hidden="true">↳</span><div><strong>{title}</strong><p>{text}</p></div></div>'


def preview_profiles(data):
    """All three profiles share the same physical axes; no smoothed invented points."""
    x = lambda q: 64 + (q + .65) / 1.3 * 540
    y = lambda e: 223 - (e + 6) / 48 * 195
    bits = ['<svg class="pop-profile" viewBox="0 0 650 280" role="img" aria-labelledby="pop-profile-title pop-profile-desc">',
            '<title id="pop-profile-title">One molecule, three energy profiles</title>',
            '<desc id="pop-profile-desc">Nine saved supports per series, joined by straight lines. PBE has a central hill; Basin60 has a central dip on this path; Targeted60 follows the hill more closely. Each series is relative to its own lower endpoint.</desc>']
    for e in (0, 20, 40):
        bits.append(f'<path d="M64 {y(e):.3f}H604" class="chart-grid"/><text x="48" y="{y(e)+4:.3f}" text-anchor="end" class="chart-axis">{e}</text>')
    for q in (-.5, 0, .5):
        bits.append(f'<text x="{x(q):.3f}" y="248" text-anchor="middle" class="chart-axis">{q:g}</text>')
    for name, color, dash, shape in [('PBE', 'var(--pbe)', '', 'square'), ('Basin60', 'var(--basin)', '3 5', 'circle'), ('Targeted60', 'var(--targeted)', '8 4', 'diamond')]:
        points = [(x(m['q']), y(v)) for m, v in zip(data['molecule'], data['profiles'][name])]
        path = ' '.join(('M' if i == 0 else 'L') + f'{xx:.4f},{yy:.4f}' for i, (xx, yy) in enumerate(points))
        bits.append(f'<g data-pop-profile="{name}" fill="{color}" stroke="{color}"><path d="{path}" fill="none" stroke-width="2.5" stroke-dasharray="{dash}"/>')
        for xx, yy in points:
            if shape == 'circle':
                bits.append(f'<circle cx="{xx:.4f}" cy="{yy:.4f}" r="3.7"/>')
            elif shape == 'square':
                bits.append(f'<rect x="{xx-3.5:.4f}" y="{yy-3.5:.4f}" width="7" height="7"/>')
            else:
                bits.append(f'<path d="M{xx:.4f} {yy-4.4:.4f}l4.4 4.4 -4.4 4.4 -4.4 -4.4Z"/>')
        bits.append('</g>')
    bits += ['<text x="64" y="18" class="chart-title">Relative energy / meV</text>',
             '<text x="334" y="275" class="chart-axis" text-anchor="middle">Proton-transfer coordinate qPT / Å</text></svg>']
    return ''.join(bits)


def overview(source, data):
    hero = fragment(source, cls='hero')
    hero = inside(hero, 'One proton.<br><em>A tiny move.<br>A big test.</em>', tag='h1')
    hero = inside(hero, 'Malonaldehyde is a nine-atom molecule with a proton that can switch between two oxygen atoms. Can a learned model capture that move—and does it matter where its training examples are placed?', cls='lede')
    hero = inside(hero, 'MALONALDEHYDE × MACHINE-LEARNED POTENTIALS', cls='eyebrow')
    hero = inside(hero, 'Drag the molecule. Move the slider. Follow the evidence.', cls='fineprint')
    hero = hero.replace('Play the research story', 'Watch the short story')
    hero = hero.replace('THE CARBON FRAME MOVES TOO', 'O = OXYGEN · H* = TRANSFERRED PROTON')
    hero = hero.replace('Nine computed images; smooth in-between motion is display interpolation. Drag horizontally to rotate.',
                        'Nine saved PBE geometries. In-between motion is a visual interpolation; the slider is position, not time.')
    intro = f'''<div class="pop-intro"><p class="eyebrow">The experiment in one minute</p><div class="pop-intro-grid"><div><h2>Same amount of data.<br><em>A different energy landscape.</em></h2><p>Moment Tensor Potentials (MTPs) learn energies and forces from quantum calculations. Here, two models receive <strong>60 training geometries each</strong>. Only the placement of 24 examples changes.</p><p>In the original pair, the targeted model follows the reference hill much more closely. Repeating the training shows why one good fit is only the first test.</p><a class="text-button" href="#landscape">Explore the full comparison →</a></div><figure class="pop-overview-figure">{preview_profiles(data)}<figcaption><span class="pop-key pbe">■ PBE reference</span><span class="pop-key basin">● Basin60</span><span class="pop-key targeted">◆ Targeted60</span></figcaption><p class="small">Original saved model pair · each curve uses its own lower endpoint as zero.</p></figure></div></div>
<div class="pop-question-grid"><a href="#molecule"><span>01 / The molecule</span><h2>What moves?</h2><p>Follow the proton and the changing molecular frame.</p><b aria-hidden="true">↗</b></a><a href="#sampling"><span>02 / The experiment</span><h2>Where to learn?</h2><p>Compare the two ways of spending the same data budget.</p><b aria-hidden="true">↗</b></a><a href="#seeds"><span>03 / The reality check</span><h2>Does it repeat?</h2><p>Targeted wins both metrics in 3 of 5 training pairs. Inspect the reversals, too.</p><b aria-hidden="true">↗</b></a></div>
{takeaway('The question is bigger than one molecule.', 'A model can look convincing on one test and behave differently on another. This small system lets us see exactly where that distinction comes from.')}
<div class="pop-reading-link"><span>Want the connected story?</span><a href="#longread">Read the illustrated research essay →</a></div>'''
    return '<section id="overview" data-page class="page active">' + hero + intro + '<div class="ed-page-turn"><a href="#molecule">Next: The molecule →</a></div></section>'


def static_forces(source, data):
    frame = next(f for f in data['forces'] if f['index'] == 145)
    rows = [('PBE', frame['pbe'][1]), ('MTP', frame['mtp'][1]), ('ΔF', frame['error'][1])]
    table = '<table><caption>Original laboratory components / eV/Å</caption><thead><tr><th scope="col">Force</th><th scope="col">x</th><th scope="col">y</th><th scope="col">z</th></tr></thead><tbody>'
    for label, row in rows:
        table += '<tr><th scope="row">' + label + '</th>' + ''.join(f'<td>{v:.5f}</td>' for v in row) + '</tr>'
    table += '</tbody></table>'
    source = inside(source, table, ident='force-components')
    source = inside(source, f'{math.sqrt(sum(v*v for v in frame["error"][1])):.5f}', ident='selected-error')
    source = inside(source, f'{frame["rmse"]:.5f}', ident='selected-rmse')
    source = source.replace('<option value="145">', '<option value="145" selected>')
    return source


def optimization(source, payload):
    """Make the measured tradeoff primary, with exact technical readers underneath."""
    from optimization_page import state_table, force_plot, source_anchor
    t = payload['theory']; states = t['main4500']['states']; cov = t['COV']
    tradeoff = fragment(source, ident='opt-finale-tradeoff')
    tradeoff = tradeoff.replace('The decisive comparison', 'Read the score, piece by piece')
    tradeoff = tradeoff.replace('The inner problem improves. The data fit gets worse. The missing piece is the coefficient penalty—not a hidden physical trajectory.',
                                'Training balances two goals: matching the examples and keeping a coefficient penalty small. In this reported refit, the total improves because the penalty falls by more than the fitting error rises.')
    tradeoff = tradeoff.replace('Saved-row arithmetic · not a new experiment', 'Arithmetic from published summary values')
    tradeoff = tradeoff.replace('<div class="table-wrap sf-table"', '<div class="table-wrap sf-table"')
    # Exact data attributes stay available to the interactive integrity checks.
    exact_table = fragment(tradeoff, cls='sf-table')
    tradeoff = change(tradeoff, details('Exact values and normalization', exact_table), cls='sf-table')
    native_chart = fragment(source, ident='opt-state-chart')
    playback = fragment(source, cls='opt-playback')
    selected = fragment(source, ident='opt-selection')
    for ident in ['opt-selected-evidence', 'opt-selected-status', 'opt-selected-source-field']:
        selected = inside(selected, '', ident=ident)
    selected = inside(selected, 'Published objective summary; this reader does not rerun the native model.', ident='opt-selected-live')
    native_rows = state_table(states).replace('Separate live-J parity: verified.', 'Live-J parity is reported in the source summary.').replace('No separate live-J parity claimed.', 'No separate live-J measurement is reported.')
    native = fragment(source, cls='opt-native-path') + '<div class="opt-episode-layout"><div class="panel opt-episode-panel">' + native_chart + playback + '</div>' + selected + '</div>' + native_rows
    atlas = fragment(source, ident='opt-coefficient-atlas')
    geometry = fragment(source, ident='opt-finale-geometry')
    controls = fragment(source, ident='opt-finale-controls')
    counterexample = fragment(source, cls='sf-counterexample')
    snapshot_title = Elements(source).find(ident='cin-snapshot-title')
    ancestor = snapshot_title['parent']
    while ancestor and ancestor['tag'] != 'figure':
        ancestor = ancestor['parent']
    snapshot = source[ancestor['start']:ancestor['end']] if ancestor else ''
    flow = fragment(source, cls='opt-transaction')
    total = fragment(source, cls='opt-parameter-total')
    parameters = details('Inside this MTP: 248 coefficients and a change of representation', total + atlas + geometry)
    episode = tradeoff + takeaway('A lower training score needs a definition.', 'Q falls by about 29% in this fixed-row example, while the data loss rises. That is an accounting result, not evidence of more accurate forces on new molecules or geometries.')
    ratio = f'<p>Ratio S2 / S0 · native training <i>J</i> <span class="review-ratio-context">from S0 to S2</span>: {t["main4500"]["S2_to_S0_ratio"]:.3f}×. This is a published objective comparison, separate from the Q bars above.</p>'
    episode += details('Inspect the seven saved states and the native objective J', '<p>J is the original weighted training objective. The five native states form one sequence; S1c and S2q are separate diagnostic copies. S3 has no independent objective measurement.</p>' + ratio + snapshot + native, 'opt-native-details')
    episode += details('Two mathematical checks: precision and a shorter step', controls + counterexample)
    end = payload['observer']['end_terminal']
    checkpoints = '<p>Which model file you keep can matter as much as the training score. These published checkpoint summaries compare force errors on the same PBE14 development geometries.</p>'
    checkpoints += '<div class="panel opt-checkpoint-force"><div class="panel-heading"><h3>Checkpoint force errors</h3><span class="micro">eV/Å · lower is better</span></div>' + force_plot(end['pbe14']) + '</div>'
    checkpoints += '<p class="pop-caption">End of main is better than terminal in both regions of this example. Relative to historical H, it improves the transition region and worsens the basin. These are published error aggregates, not an independent holdout test.</p>'
    condition = '<p>For fixed training rows A and y, a fixed feasible subspace and a fixed positive metric M, choose the coefficient change δ to minimize the residual plus a penalty on the change:</p><p class="pop-equation">min<sub>δ ∈ V</sub> ‖r + Aδ‖² + δᵀMδ</p><p>If zero is feasible and the penalty is nonnegative and vanishes at zero, an exact minimizer cannot increase the same saved-row data loss. An approximate numerical solution must verify the inequality explicitly. This guarantee does not extend automatically to native J or unseen force errors.</p>'
    condition += f'<p>The published COV example reports a <strong>{cov["percent_of_total_data_loss_removed"]:.2f}%</strong> saved-row decrease from S1c. It is a proposed update, not a demonstrated repair of S2 or a validated optimizer improvement. Candidate export, native energy/force parity and independent external testing remain the next checks.</p>'
    condition += details('Why a large coefficient change needs care', '<p>The reported coefficient increment has norm about 12,120 and the regularized stack has condition number about 8.1 × 10⁷. A coefficient norm depends on parameterization; a large value alone neither proves failure nor establishes safety. Changes in predicted energies and forces must be tested directly. Transporting a chosen metric preserves that quadratic penalty; choosing a new diagonal metric in each representation does not make the entire policy globally invariant.</p>')
    condition += flow
    evidence = '<div class="pop-score-grid"><article><span>01 / Exact conditional statement</span><h3>The algebra</h3><p>With fixed rows, space and penalty, zero is an admissible baseline for the incremental solve.</p></article><article><span>02 / Published summaries</span><h3>The numerical example</h3><p>The bars and tables reproduce arithmetic from the published optimizer aggregates. They are not a fresh native replay.</p></article><article><span>03 / Still a research question</span><h3>The useful model</h3><p>Better force predictions require a matched comparison and geometries kept separate from development.</p></article></div><p class="pop-caption">Engineered and checked on synthetic runs. Not yet demonstrated to be a better real-data optimizer.</p>'
    future = '<p>Does a consistent update improve complete training under the same data, initialization, cost and checkpoint policy? Test that question on independent geometries before using it to support a physical simulation.</p><p>The studies here show why data placement, initialization, evaluation geometry and the training objective all belong in the explanation of a model’s accuracy.</p><div class="opt-next-links"><a href="#seeds">Training repeats ↗</a><a href="#offpath">New geometries ↗</a><a href="#reproduce">Methods and sources ↗</a></div>'
    sources = []
    for entry in payload['sources']:
        url = entry.get('url') if entry.get('source_access') == 'PUBLIC' else None
        link = f'<a href="{escape(url, quote=True)}">Public source ↗</a>' if url else '<a href="data/optimization/OPTIMIZATION_STORY.json">Published summary record ↗</a>'
        label = entry['id'].replace('main4500', 'boundary')
        sources.append(f'<p id="{source_anchor(entry["id"])}" tabindex="-1"><code>{escape(label)}</code> · {link}</p>')
    downloads = '<div class="opt-downloads"><a class="button" href="data/finale.json" download>Figure values ↓</a><a class="button" href="data/optimization/OPTIMIZATION_STORY.json" download>Published aggregates ↓</a><a class="button" href="data/optimization/CLAIM_DATA_MAP.tsv" download>Definitions and source map ↓</a></div>'
    downloads += details('Technical source index', ''.join(sources), 'opt-source-registry')
    heading = '''<div class="pop-opt-hero"><div><p class="eyebrow">A model’s training score</p><h1 id="opt-title">A better score.<br><em>A better model?</em></h1><p class="lede">To judge an improvement, first ask what was minimized. A fit to the training data, a coefficient penalty and a force error on new geometries measure different things.</p></div><div class="pop-score-symbol" aria-hidden="true"><span>fit</span><b>+</b><span>penalty</span><b>=</b><strong>score</strong></div></div>'''
    guide = fragment(source, cls='cin-chapter-map')
    status = '<p id="opt-load-status" class="opt-load-status" role="status">The figures and tables remain readable without JavaScript. Interactive controls load the same saved values.</p>'
    body = heading + guide + status
    body += section('opt-parameters', 'What does the model learn?', '<p>An MTP describes local atomic environments and combines their contributions into an energy. Forces follow from how that energy changes when atoms move. Fitting adjusts its coefficients against reference examples.</p>' + parameters, 'The model behind the score')
    body += section('opt-episode', 'One refit. Two answers.', episode, 'The central example')
    body += section('opt-checkpoints', 'Which finished model?', checkpoints)
    body += section('opt-candidate', 'Penalize the change.', condition, 'A candidate idea · COV')
    body += section('opt-evidence', 'How far does the result travel?', evidence)
    body += section('opt-next-study', 'What would make the model more useful?', future)
    body += section('opt-sources', 'Inspect the numbers.', downloads, 'Data behind the figures')
    body += '<div class="ed-page-turn"><a href="#forces">← Inside the forces</a><a href="#story">Next: The story →</a></div>'
    return '<section id="optimization" data-page class="page optimization-page" aria-labelledby="opt-title">' + body + '</section>'


def evidence(source, data):
    reference_list = fragment(source, cls='reference-list')
    ledger_node = Elements(source).find(cls='data-table')
    ledger = source[ledger_node['start']:ledger_node['end']]
    methods = '''<div class="pop-methods-grid"><article><span class="eyebrow">The reference</span><h2>PBE calculations</h2><p>Electronic energies and forces for an isolated malonaldehyde molecule. The saved path contains nine NEB geometries. PBE is the comparison target in this exhibit, rather than an experimental ground truth.</p></article><article><span class="eyebrow">The learned model</span><h2>Moment Tensor Potentials</h2><p>Two fixed 60-geometry training sets test data placement. Five paired initializations test training variability. PBE14 perturbs geometries away from the path. Train119 is a separate adaptive development study.</p></article><article><span class="eyebrow">What the figures establish</span><h2>Different checks</h2><p>Geometry, energy and force figures use saved arrays; seed comparisons use published metrics; optimizer figures use published summary tables. Recomputing a number and repeating an entire experiment are different levels of reproduction.</p></article></div>'''
    numerical = '''<p>PBE, scalar-relativistic PSlibrary PAW pseudopotentials; neutral molecule, spin-unpolarized; 16 Å periodic cell, Γ-point sampling; 80 Ry wavefunction and 960 Ry charge-density cutoffs; documented SCF threshold 10⁻¹⁰ Ry. The nine-image path has fixed endpoints; the source settings use automatic climbing-image selection and a path threshold up to 0.05 eV/Å.</p><p>These are the documented settings, not a cutoff, cell-size or path-discretization convergence study. The plotted barrier is the maximum of nine saved electronic energies relative to the lower endpoint. It is not a certified saddle energy, a free-energy barrier, a tunneling splitting or a reaction rate.</p><p>The saved endpoint energies differ by about 0.107 meV. Later sub-meV model errors describe agreement with this same reference; additional decimal places preserve arithmetic, not established physical precision.</p><p><a href="https://github.com/spicmaff/malonaldehyde-transition-sampling/blob/main/docs/SOFTWARE_PROVENANCE.md">Software and reference settings ↗</a> · <a href="https://github.com/spicmaff/malonaldehyde-transition-sampling/blob/main/docs/METHODS.md">Study methods ↗</a></p>'''
    metrics = '''<dl class="pop-definition-list"><dt>Proton position</dt><dd>qPT = r(O1–H2*) − r(O8–H2*), in Å. Negative and positive values identify the two sides; zero means equal O–H distances.</dd><dt>Discrete path barrier</dt><dd>max(E₁…E₉) − min(E₁,E₉). Each profile uses its own lower endpoint as zero. The original barrier error is the absolute model–PBE difference of these barriers.</dd><dt>Force-component RMSE</dt><dd>√[Σ(ΔF)² / 27] for one nine-atom configuration; ΔF = MTP − PBE, in eV/Å. The original central-region score pools the three path images with |qPT| ≤ 0.15 Å.</dd><dt>PBE14 weighting</dt><dd>Average each ± pair within its physical direction (the out-of-plane block has one geometry), give the four directions equal weight, then average the five paired initializations. Weights are fixed before comparing models.</dd><dt>Applicability grade</dt><dd>A dimensionless model diagnostic, compared against its saved stop. It is neither a force error nor a universal probability of accuracy.</dd></dl>'''
    commands = f'''<div class="pop-reproduce"><div><p class="eyebrow">Check it yourself</p><h2>From a figure<br>to its source.</h2><p>Reproduce the displayed saved-data metrics and rebuild the site with the public repository. The downloads support arithmetic checks; new training or native model evaluations require their own computational setup.</p><a class="button primary" href="{REPO}">Open research &amp; code ↗</a></div><pre><code>git clone {REPO}.git
cd malonaldehyde-transition-sampling
python3 tools/recompute_primary_metrics.py
python3 tools/verify_pbe14_offpath.py
python3 tools/verify_train119_diagnostic.py \\
  --data data/post_publication/train119_diagnostic_v001
python3 tools/build_research_site.py --out _site</code></pre></div>'''
    downloads = '<div class="pop-downloads"><a href="data/science.json" download>Molecular geometries, energies &amp; forces ↓</a><a href="data/offpath.json" download>PBE14 figure data ↓</a><a href="data/editorial.json" download>Recomputed audit values ↓</a><a href="longread.en.md" download>Research essay ↓</a></div>'
    boundary = takeaway('Keep the scope with the result.', 'Training repeats use the same data allocations; neighboring trajectory frames are correlated; shared endpoints and adaptive development limit generalization claims. No prospective final holdout or experimental accuracy is established here.')
    body = '<div class="page-head"><p class="eyebrow">Methods and sources</p><h1>Follow the evidence.</h1><p class="lede">The definitions, calculation settings and public source files behind the story. Start with the figures; open the details when you want to go further.</p></div>'
    body += methods + boundary + details('Reference calculation settings and physical precision', numerical) + details('How each plotted quantity is defined', metrics) + commands + downloads + ledger
    body += '<div class="section-heading"><p class="eyebrow">Read further</p><h2>The science behind the story.</h2><p class="lede">Original methods and physical context. The reading notes distinguish full-text checks from abstract-level comparisons.</p><a href="data/literature.json" download>Annotated references ↓</a></div>' + reference_list
    body += '<div class="ed-page-turn"><a href="#longread">← Read the essay</a><a href="#overview">Back to the beginning ↑</a></div>'
    return '<section id="reproduce" data-page class="page">' + body + '</section>'


def build(document, data, payload, out):
    from editorial import Pages
    pages = Pages(document).spans
    fragments = {key: document[a:b] for key, (a, b) in pages.items()}
    fragments['overview'] = overview(fragments['overview'], data)
    fragments['forces'] = static_forces(fragments['forces'], data)
    fragments['optimization'] = optimization(fragments['optimization'], payload)
    fragments['reproduce'] = evidence(fragments['reproduce'], data)
    # Keep the controls and numerical evidence, shorten the interpretive detours.
    sampling = fragments['sampling']
    sampling = sampling.replace('Transition-directed is not<br><em>path-covering.</em>', 'The shortcut misses<br><em>the squeeze.</em>')
    sampling = sampling.replace('The original advantage remains a result on the saved evaluation path. It does not demonstrate coverage of transition geometry, nor isolate sampling along a fully relaxed reaction coordinate. These two descriptors reveal a gap; they cannot certify coverage in all 27 Cartesian dimensions.',
                                'The proton moves across, but the oxygen atoms also move closer. The targeted examples follow a perturbed straight connection between aligned minima, rather than the relaxed path. This geometric gap alone does not establish extrapolation in MTP feature space.')
    sampling = sampling.replace('These projections do not establish coverage in MTP feature space.', 'These projections do not establish coverage in MTP feature space.')
    fragments['sampling'] = sampling
    landscape = fragments['landscape']
    banner = takeaway('Look at the shape, too.', 'On these nine saved supports, Basin60 predicts a dip at the center where PBE has a hill. Targeted60 follows the hill more closely. This describes the sampled path, rather than proving a minimum or a saddle on the full molecular energy surface.')
    landscape = landscape.replace('<div class="profile-layout">', banner + '<div class="profile-layout">', 1)
    fragments['landscape'] = landscape
    # Repeated caveats become one concise explanation beside the relevant result.
    train = fragments['train119'].replace('Train119 makes that distinction visible without changing its historical failure.',
                                         'The later 119-geometry model makes that distinction visible.')
    train = train.replace('STATIC_APPLICABILITY_FAIL remains.', 'The coverage criterion still fails.')
    fragments['train119'] = train
    off = fragments['offpath']
    off = off.replace('It does not certify reactive dynamics, PES topology, an untouched global holdout or Blind12 performance.',
                      'It tests local transfer around known anchors; it does not establish reactive dynamics or independent global accuracy.')
    off = off.replace('<p><span class="badge">SEED_SENSITIVE</span> <span class="badge">STATIC_APPLICABILITY_FAIL</span></p>', '')
    off = off.replace('The interrupted historical T02m job and its separately authorized recovery remain disclosed.',
                      'The verifier checks the saved reference/prediction mapping before computing errors.')
    off = off.replace('Atom IDs and the original renderer are unchanged.', 'O1 and O8 are oxygens; H2* is the transferred proton.')
    if 'ed-sensitivity' in off:
        block = fragment(off, cls='ed-sensitivity')
        off = change(off, details('Sensitivity to alternative weights · exploratory analysis', block), cls='ed-sensitivity')
    fragments['offpath'] = off
    # The essay and its download share one source; a short reading scope replaces
    # the former archive inventory, without implying a new physical experiment.
    essay_note = fragment(fragments['longread'], cls='ed-essay-note')
    fragments['longread'] = fragments['longread'].replace(essay_note, '')
    a = min(a for a, _ in pages.values()); b = max(b for _, b in pages.values())
    document = document[:a] + ''.join(fragments[k] for k in pages) + document[b:]
    document = document.replace('A saved-data research exhibit by Mikhail Fofonov.', 'An explorable chemistry study by Mikhail Fofonov.')
    document = document.replace('Evidence, not a deployment claim.', 'Explore the molecule. Inspect the numbers.')
    document = document.replace('Science preserved at', 'Research snapshot')
    document = document.replace('</head>', '<link rel="stylesheet" href="popular.css"></head>', 1)
    (out / 'popular.css').write_bytes((Path(__file__).parent / 'popular.css').read_bytes())
    return document
