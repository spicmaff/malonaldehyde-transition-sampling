"""Source-derived editorial diagrams. No model calls, invented states or new data."""
from __future__ import annotations
import math
import re
from pathlib import Path
from html import escape


def replace_one(document: str, pattern: str, replacement: str) -> str:
    result, count = re.subn(pattern, lambda _: replacement, document, flags=re.S)
    if count != 1:
        raise ValueError('Cinematic extension point must occur once: ' + pattern)
    return result


def fmt(value: float | None) -> str:
    return 'Not measured' if value is None else f'{value:.6g}'.replace('-', '−')


def snapshots(episode: dict) -> str:
    states = {s['id']: s for s in episode['states']}
    rows = []
    for key, label in [('S0', 'Before'), ('S2', 'Refit'), ('S4', 'Next step')]:
        value = states[key]['native_J']
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 1e-5 <= value <= 1e-3:
            raise ValueError('Snapshot outside its declared fixed logarithmic axis')
        left = (math.log10(value) + 5) / 2 * 100
        rows.append(f'<div class="cin-snapshot-row"><span><b>{key}</b> {label}</span>'
                    f'<div class="cin-snapshot-track" aria-hidden="true"><i data-cin-j="{value}" '
                    f'data-cin-snapshot="{key}" style="left:{left:.12f}%"></i></div>'
                    f'<strong title="{value}">{format(value, ".3e").replace("e-0", "e−")}</strong></div>')
    return ('<figure class="cin-snapshot" aria-labelledby="cin-snapshot-title">'
            '<figcaption id="cin-snapshot-title">Three saved native-J snapshots</figcaption>'
            '<div class="cin-snapshot-axis" aria-hidden="true"><span>10⁻⁵</span><span>10⁻⁴</span><span>10⁻³</span></div>'
            + ''.join(rows) + '<p>Fixed log₁₀ axis · lower is better. S1 and the diagnostic branches are inspected below; S3 has no measured J.</p></figure>')


def atlas(architecture: dict) -> str:
    blocks = architecture['parameter_blocks']
    if [b['id'] for b in blocks] != ['radial', 'invariant', 'offset'] or sum(b['count'] for b in blocks) != architecture['nominal_parameters']:
        raise ValueError('Unexpected coefficient partition')
    controls = [f'<button type="button" data-cin-group-select="all" aria-pressed="true" aria-controls="cin-atlas-inspector" disabled>All {architecture["nominal_parameters"]}</button>']
    cells = []
    for block in blocks:
        key, count, label = block['id'], block['count'], escape(block['label'])
        detail = escape(block.get('factorization', block.get('definition', '')))
        controls.append(f'<button type="button" data-cin-group-select="{key}" aria-pressed="false" aria-controls="cin-atlas-inspector" disabled>{label} <b>{count}</b></button>')
        marks = ''.join(f'<i data-cin-cell="{key}"></i>' for _ in range(count))
        cells.append(f'<div class="cin-cell-block cin-cells-{key}" data-cin-group="{key}" data-cin-label="{label}" data-cin-count="{count}" data-cin-detail="{detail}"><span class="cin-cell-label">{label} · {count}</span><div class="cin-cells" aria-hidden="true">{marks}</div></div>')
    return ('<figure id="opt-coefficient-atlas" class="cin-atlas" data-selection="all" aria-labelledby="cin-atlas-title">'
            '<div class="cin-atlas-heading"><div><p class="micro">A map of the stored coefficients</p><h3 id="cin-atlas-title">Every square has a role.</h3></div><span class="cin-atlas-key">1 square = 1 nominal coefficient</span></div>'
            '<div class="cin-atlas-controls" role="group" aria-label="Highlight a coefficient family">' + ''.join(controls) + '</div>'
            '<div class="cin-atlas-body"><div class="cin-cell-map">' + ''.join(cells) + '</div>'
            f'<div id="cin-atlas-inspector" class="cin-atlas-inspector" aria-live="polite" aria-atomic="true"><strong id="cin-atlas-count">{architecture["nominal_parameters"]}</strong><h4 id="cin-atlas-label">Nominal parameters</h4><p id="cin-atlas-detail">Select a family to trace its role. With the radial block fixed, the invariant coefficients and species offsets form the {architecture["linear_parameters"]}-coefficient linear problem.</p></div></div>'
            '<figcaption>Schematic grouping, not a parameter landscape, coefficient magnitude or physical-rank measurement. The definitions and public template are linked below.</figcaption></figure>')


def native_rail(episode: dict) -> str:
    states = {s['id']: s for s in episode['states']}
    items = []
    for key in episode['native_order']:
        s = states[key]
        items.append(f'<li><button type="button" data-cin-step="{key}" aria-pressed="{str(key == "S0").lower()}" aria-controls="opt-selection" disabled><span>{key}</span><b>{escape(s["label"])}</b><small>{fmt(s["native_J"])}</small></button></li>')
    return ('<div class="opt-native-path"><span class="micro">Native sequence · inspect a saved state</span>'
            '<ol class="cin-native-rail" aria-label="Five native states in event order">' + ''.join(items) + '</ol>'
            '<p>Separate diagnostic copies: S1 → S1c · S2 → S2q. Select them in the full chart below. This rail shows event order, not elapsed time or a loss scale.</p></div>')


def transaction() -> str:
    return ('<div class="opt-transaction" role="group" aria-label="Conceptual future runtime transaction, not an executing optimizer"><div class="cin-flow">'
            '<div class="cin-flow-step"><span class="micro">01 / Propose</span><h4>Change the coefficients.<br>Keep the reference.</h4><p>Construct an increment around the compensated incumbent, in the fixed feasible space.</p></div>'
            '<div class="cin-flow-step cin-flow-check"><span class="micro">02 / Check</span><h4>Does native J<br>qualify?</h4><p>A separate evaluation of the original objective and its fixed acceptance tolerance.</p><span class="cin-fork-label">Two alternative outcomes →</span></div>'
            '<div class="cin-flow-outcomes"><div class="cin-flow-accept"><span class="micro">If qualified</span><h4>Accept the candidate</h4><p>Use the same locked checkpoint policy.</p></div><div class="cin-flow-rollback"><span class="micro">Otherwise</span><h4>Complete rollback</h4><p>Restore the required optimizer state.</p></div></div></div></div>')


def append_to_page(document: str, route: str, content: str) -> str:
    start = document.index(f'<section id="{route}" data-page')
    next_page = re.search(r'<section id="[^"]+" data-page', document[start + 1:])
    end = start + 1 + next_page.start() if next_page else document.index('</main>', start)
    pos = document.rfind('</section>', start, end)
    if pos < 0:
        raise ValueError('Missing page boundary: ' + route)
    return document[:pos] + content + document[pos:]


def refine_document(document: str, data: dict) -> str:
    if 'cinematic.css' in document:
        raise ValueError('Cinematic extension already applied')
    theory = data['theory']
    document = replace_one(document, r'<div class="opt-before-after">.*?</div></div>', snapshots(theory['main4500']))
    # State the ratio as after / before; "times higher" is needlessly ambiguous.
    document = replace_one(document,
        r'higher native training <i>J</i> <span class="review-ratio-context">from S0 to S2</span>',
        'Ratio S2 / S0 · native training <i>J</i> <span class="review-ratio-context">from S0 to S2</span>')
    document = replace_one(document,
        r'<div class="opt-page-index" role="navigation" aria-label="Optimization chapter contents">',
        '<div class="cin-chapter-map"><div class="cin-map-caption">'
        '<span class="micro">Chapter guide</span><span id="cin-reading-position">Six connected questions</span>'
        '</div><div class="opt-page-index" role="navigation" aria-label="Optimization chapter contents">')
    document = replace_one(document, r'</div>\n<p id="opt-load-status"',
        '</div></div>\n<p id="opt-load-status"')
    document = replace_one(document, r'<div class="opt-parameter-grid">', atlas(theory['architecture']) + '<div class="opt-parameter-grid">')
    document = replace_one(document, r'<div class="opt-native-path">.*?</p></div>', native_rail(theory['main4500']))
    document = replace_one(document, r'<div class="opt-transaction" role="group" aria-label="Conceptual future runtime transaction, not an executing optimizer">.*?</div></div>', transaction())
    bridge = ('<div class="cin-reading-path" aria-label="Three connected questions" role="navigation">'
              '<a href="#molecule"><span>01 / The geometry</span><strong>What moves?</strong><small>Inspect the saved molecular path →</small></a>'
              '<a href="#offpath"><span>02 / The evidence</span><strong>Where does it hold?</strong><small>Leave the reference path →</small></a>'
              '<a href="#optimization"><span>03 / The mechanism</span><strong>What is being optimized?</strong><small>Follow one periodic refit →</small></a></div>')
    document = append_to_page(document, 'overview', bridge)
    document = append_to_page(document, 'offpath', '<aside class="cin-next"><div><p class="eyebrow">The next question is inside the fit</p><h2>Data placement is not<br><em>the whole story.</em></h2><p>A finite training run also depends on its optimization and checkpoint choices. Follow one measured refit, and distinguish a diagnosed problem from a candidate still awaiting a real-data test.</p></div><a class="button primary" href="#optimization">Inside the optimization <span aria-hidden="true">→</span></a></aside>')
    return replace_one(document, '</head>', '<link rel="stylesheet" href="cinematic.css"><script type="module" src="cinematic.mjs"></script></head>')


def copy_assets(out: Path) -> None:
    for suffix in ('.css', '.mjs'):
        src = Path(__file__).with_suffix(suffix)
        (out / src.name).write_bytes(src.read_bytes())
