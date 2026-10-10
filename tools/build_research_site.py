#!/usr/bin/env python3
"""Deterministic English research exhibit built from frozen public evidence.

Reads saved calculations only. No DFT, inference, training, selectors or dynamics.
Python 3.11+, standard library. The source scientific verifier is not modified.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import json
import math
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from verify_train119_diagnostic import (
    parse_cfg, verify, force_metrics, terminal_pw, xml_reference, maxdelta, STOP, A2,
)
BASE = '3d430af343cf726d94ef8d2143fe7c24fa053c2b'
SCIENCE_COMMIT = 'f44d28cc0b13defb747f625376b083055b577629'
REPO = 'https://github.com/spicmaff/malonaldehyde-transition-sampling'
DROOT = 'data/post_publication/train119_diagnostic_v001'
SOURCES = {
    'path': 'data/frozen_models_v028/frozen_audit21_labels_v029.cfg',
    'basin': 'data/frozen_models_v028/audit21_predictions_basin_v029.cfg',
    'targeted': 'data/frozen_models_v028/audit21_predictions_targeted_v029.cfg',
    'train_basin': 'data/frozen_models_v028/train_basin60_v028.cfg',
    'train_targeted': 'data/frozen_models_v028/train_targeted60_v028.cfg',
    'seeds': 'data/robustness/v028_seed_robustness_v001/ALL_METRICS.tsv',
    'replay': 'data/visual_story/v001/replay228_gamma.tsv',
    'train119': DROOT + '/OFFLINE_VERIFICATION.json',
    'train119_prediction': DROOT + '/predictions/AUDIT21_STATIC.cfg',
    'train119_manifest': DROOT + '/SOURCE_MANIFEST.json',
    'science': 'data/post_publication/FINAL_SCIENCE_STATUS.json',
    'methods': 'docs/METHODS.md', 'limits': 'docs/LIMITATIONS.md',
    'corrections': 'docs/TRAIN119_CORRECTIONS.md',
    'diagnostic': 'docs/TRAIN119_LOCAL_DIAGNOSTIC.md',
    'roles': 'provenance/TRAIN119_DATASET_ROLES.tsv',
    'geometry': 'provenance/TRAIN119_GEOMETRY_RELATIONS.tsv',
    'randomness': 'docs/TRAINING_RANDOMNESS.md',
    'continuation': 'docs/POST_PUBLICATION_CONTINUATION.md',
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def rows(path: str) -> list[dict]:
    with (ROOT / path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def cfg(path: str, labels: bool = True):
    return parse_cfg((ROOT / path).read_text(encoding='utf-8'), labels=labels)


def coords(c) -> dict:
    x = c.xyz
    left, right = math.dist(x[0], x[1]), math.dist(x[7], x[1])
    return {'q': left - right, 'roo': math.dist(x[0], x[7]), 'left': left, 'right': right}


def scientific_data() -> dict:
    verified = verify(ROOT / DROOT)
    check(verified['status'] == 'PASS_SAVED_PAYLOAD_NUMERICS_AND_MAPPING', 'Diagnostic verification failed')
    sources = dict(SOURCES)
    ref = cfg(sources['path'])
    ii = [i for i, c in enumerate(ref) if c.features.get('audit_subset') == 'neb9']
    check(len(ii) == 9, 'NEB membership')
    mol = [{'image': j + 1, 'xyz': ref[i].xyz, **coords(ref[i])} for j, i in enumerate(ii)]
    profiles, metrics = {}, {}
    for key in ('path', 'basin', 'targeted', 'train119_prediction'):
        name = {'path': 'PBE', 'basin': 'Basin60', 'targeted': 'Targeted60', 'train119_prediction': 'Train119'}[key]
        cc = cfg(sources[key])
        check(len(cc) == 21, 'Audit prediction cardinality')
        energies = [cc[i].energy for i in ii]
        zero = min(energies[0], energies[-1])
        profiles[name] = [1000 * (e - zero) for e in energies]
        ctr = [i for i in ii if abs(coords(ref[i])['q']) <= .15]
        check(len(ctr) == 3, 'Central-three membership')
        fr = math.sqrt(math.fsum(force_metrics(ref[i].forces, cc[i].forces)['force_component_RMSE_eV_A'] ** 2 for i in ctr) / 3)
        metrics[name] = {'barrier': max(profiles[name]), 'force_rmse': fr}
    residuals = {}
    for key, value in metrics.items():
        value['barrier_error'] = abs(value['barrier'] - metrics['PBE']['barrier'])
        residuals[key] = [m - p for m, p in zip(profiles[key], profiles['PBE'])]
        value['profile_max_abs_error'] = max(map(abs, residuals[key]))
    check(abs(metrics['Basin60']['barrier_error'] - 35.245734070031176) < 1e-8, 'Basin primary metric')
    check(abs(metrics['Targeted60']['force_rmse'] - .07868490481909636) < 1e-12, 'Targeted primary metric')
    check(abs(metrics['Train119']['profile_max_abs_error'] - .5040717796) < 1e-7, 'Profile residual')
    sets = {key: cfg(sources['train_' + key]) for key in ('basin', 'targeted')}
    ids = {key: {c.features.get('candidate_id') for c in values} for key, values in sets.items()}
    common = ids['basin'] & ids['targeted']
    check(len(common) == 36 and None not in common, 'Shared set identity')
    sampling = {}
    for key, values in sets.items():
        check(len(values) == 60 and len(ids[key]) == 60, 'Train60 identities')
        sampling[key] = [{'id': c.features['candidate_id'], 'shared': c.features['candidate_id'] in common, **coords(c)} for c in values]
    seeds = [{'index': int(r['seed_index']), 'seed': r['seed_u64'], 'model': r['branch'],
              'barrier': float(r['lower_endpoint_barrier_abs_error_meV']),
              'force': float(r['transition_region_force_component_RMSE_eV_A'])} for r in rows(sources['seeds'])]
    check(len(seeds) == 10 and {r['index'] for r in seeds} == set(range(5)), 'Seed membership')
    for i in range(5):
        pair = [r for r in seeds if r['index'] == i]
        check(len(pair) == 2 and len({r['seed'] for r in pair}) == 1, 'Paired seed identity')
    replay = [{'index': int(r['replay_index']), 'gamma': float(r['gamma'])} for r in rows(sources['replay'])]
    check([r['index'] for r in replay if r['gamma'] > STOP] == [143, 144, 145, 146, 147], 'Gamma crossings')
    local = verified['local_results']
    force_frames = []
    for group, indexes, input_name in [
        ('CHALLENGE4', list(range(93, 97)), 'LOCAL_CHALLENGE4_REPLAY93_96_EXACT.cfg'),
        ('CROSSING7', list(range(142, 149)), 'CROSSING7_EXACT.cfg'),
    ]:
        input_path = DROOT + '/inputs/' + input_name
        pred_path = DROOT + '/predictions/' + group + '.cfg'
        sources['geometry_' + group.lower()] = input_path
        sources['prediction_' + group.lower()] = pred_path
        inputs, predictions = cfg(input_path, False), cfg(pred_path)
        check(len(inputs) == len(predictions) == len(indexes), 'Force-viewer cardinality')
        for index, conf, prediction in zip(indexes, inputs, predictions):
            stem = DROOT + f'/references/replay{index:03d}/'
            output_path, xml_path = stem + 'pw.out', stem + 'data-file-schema.xml'
            sources[f'forces_{index}'] = output_path
            sources[f'xml_{index}'] = xml_path
            epbe, fpbe, _ = terminal_pw((ROOT / output_path).read_text())
            xe, xf = xml_reference((ROOT / xml_path).read_text(), conf)
            check(abs(epbe - xe) < 7e-8 and maxdelta(fpbe, xf) < 1.3e-7, 'XML/stdout agreement')
            fm = force_metrics(fpbe, prediction.forces)
            saved = next(r for r in local if r['replay_index'] == index)
            check(abs(fm['force_component_RMSE_eV_A'] - saved['force_component_RMSE_eV_A']) < 1e-12, 'Force-viewer RMSE')
            check(abs(replay[index - 1]['gamma'] - saved['gamma_saved']) < 1e-12, 'Saved gamma identity')
            force_frames.append({'index': index, 'group': group, 'xyz': conf.xyz,
                'ids': list(conf.ids), 'elements': ['O','H','C','H','C','H','C','O','H'],
                'pbe': fpbe, 'mtp': prediction.forces,
                'error': [[b - a for a, b in zip(ra, rb)] for ra, rb in zip(fpbe, prediction.forces)],
                'gamma': saved['gamma_saved'], 'rmse': fm['force_component_RMSE_eV_A'],
                'max_component': fm['max_abs_component_eV_A'], 'source_key': f'forces_{index}', **coords(conf)})
    evidence = {k: {'path': p, 'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest(),
                    'url': f'{REPO}/blob/{BASE}/{p}', 'commit': BASE} for k, p in sources.items()}
    contraction = mol[0]['roo'] - mol[4]['roo']
    return {'schema': 'proton-potential-cinematic-v2', 'science_commit': SCIENCE_COMMIT, 'source_commit': BASE,
        'molecule': mol, 'profiles': profiles, 'residuals': residuals, 'metrics': metrics,
        'sampling': sampling, 'seeds': seeds, 'replay': replay, 'local': local, 'forces': force_frames,
        'stop': STOP, 'a2': A2, 'static': verified['static'], 'overlaps': verified['audit_train_overlap'],
        'contraction_A': contraction, 'contraction_percent': 100 * contraction / mol[0]['roo'],
        'evidence': evidence, 'boundaries': {'MD': False, 'independent_Train119_test': False,
            'seed_status': 'SEED_SENSITIVE', 'Train119_status': 'STATIC_APPLICABILITY_FAIL', 'new_scientific_calls': 0}}


def literature() -> list[dict]:
    records = json.loads((ROOT / 'site/literature.json').read_text())
    ids = [r['id'] for r in records]
    check(len(ids) == len(set(ids)), 'Duplicate literature identity')
    for record in records:
        check(record['url'].startswith('https://') and all(record.get(k) for k in ('title','authors','year','scope','access')), 'Incomplete reference')
    return records


def article_html(text: str, data: dict, refs: list[dict]) -> str:
    out, paragraph = [], []
    papers = {p['id']: p for p in refs}
    def inline(s):
        escaped = html.escape(s)
        return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    def flush():
        if paragraph:
            out.append('<p>' + inline(' '.join(paragraph)) + '</p>')
            paragraph.clear()
    for line in text.splitlines():
        if line.startswith('## '):
            flush(); title = line[3:]; slug = re.sub('[^a-z0-9]+', '-', title.lower()).strip('-')
            out.append(f'<h2 id="read-{slug}">{html.escape(title)}</h2>')
        elif line.startswith('# '):
            flush()
        elif line.startswith('@sources:'):
            flush(); keys = line.split(':', 1)[1].split(); check(all(k in data['evidence'] for k in keys), 'Unknown source')
            out.append('<p class="chapter-source">Project evidence: ' + ' · '.join(f'<a href="{data["evidence"][k]["url"]}">{html.escape(k.replace("_"," "))}</a>' for k in keys) + '</p>')
        elif line.startswith('@papers:'):
            flush(); keys = line.split(':', 1)[1].split(); check(all(k in papers for k in keys), 'Unknown literature citation')
            out.append('<p class="chapter-source">Literature: ' + ' · '.join(f'<a href="{papers[k]["url"]}">{html.escape(papers[k]["short"])}</a>' for k in keys) + '</p>')
        elif line.strip():
            paragraph.append(line.strip())
        else:
            flush()
    flush()
    return '\n'.join(out)


def build(out: Path) -> dict:
    out = out.resolve()
    check(out != ROOT and out != ROOT.parent and not ROOT.is_relative_to(out), 'Unsafe output root')
    check(not out.is_relative_to(ROOT / 'site') and not out.is_relative_to(ROOT / 'data'), 'Refuse source overwrite')
    marker = out / '.proton-generated'
    check(not out.exists() or not any(out.iterdir()) or marker.is_file(), 'Output must be empty or owned by this builder')
    data, refs = scientific_data(), literature()
    cinema = ROOT / 'site/cinema/manifest.json'
    if cinema.is_file():
        manifest = json.loads(cinema.read_text())
        check(manifest.get('new_physical_calls') == 0, 'Cinema scope mismatch')
        films = manifest['films']
        for film in films:
            for key, hashkey in [('file', 'sha256'), ('poster', 'poster_sha256'), ('captions', 'captions_sha256')]:
                relative = Path(film[key])
                check(not relative.is_absolute() and '..' not in relative.parts and relative.parts[0] == 'cinema', 'Unsafe cinema path')
                check(hashlib.sha256((ROOT / 'site' / relative).read_bytes()).hexdigest() == film[hashkey], 'Cinema checksum mismatch')
            check(film['fps'] == 60 and film['width'] == 1920 and film['height'] == 1080 and film['frames'] == film['duration_seconds'] * 60, 'Cinema format mismatch')
        data['films'] = films
    out.mkdir(parents=True, exist_ok=True); marker.write_text('proton-potential-v2\n')
    # Only this explicitly generated directory may be rebuilt. No scientific inputs are modified.
    old = out / 'build-manifest.json'
    if old.is_file():
        for relative in json.loads(old.read_text()):
            p = (out / relative).resolve()
            check(p.is_relative_to(out) and p != marker, 'Unsafe old build manifest')
            if p.is_file():
                p.unlink()
    (out / 'data').mkdir(exist_ok=True)
    (out / 'data/science.json').write_text(json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
    (out / 'data/literature.json').write_text(json.dumps(refs, ensure_ascii=True, sort_keys=True, indent=2) + '\n')
    sys.path.insert(0, str(ROOT / 'site'))
    from pages import render
    article = (ROOT / 'site/longread.en.md').read_text()
    (out / 'index.html').write_text(render(data, article_html(article, data, refs), refs), encoding='utf-8')
    download = []
    refmap = {r['id']: r for r in refs}
    for line in article.splitlines():
        if line.startswith('@sources:'):
            line = 'Project sources: ' + ' · '.join('[' + key + '](' + data['evidence'][key]['url'] + ')' for key in line.split(':', 1)[1].split())
        elif line.startswith('@papers:'):
            line = 'Literature: ' + ' · '.join('[' + refmap[key]['short'] + '](' + refmap[key]['url'] + ')' for key in line.split(':', 1)[1].split())
        download.append(line)
    (out / 'longread.en.md').write_text('\n'.join(download) + '\n', encoding='utf-8')
    for name in ('style.css', 'app.mjs', 'core.mjs', 'molecule.mjs', 'charts.mjs', 'favicon.svg', 'social-preview.svg'):
        shutil.copyfile(ROOT / 'site' / name, out / name)
    for dirname in ('vendor', 'cinema'):
        source = ROOT / 'site' / dirname
        if source.is_dir():
            shutil.copytree(source, out / dirname, dirs_exist_ok=True)
    (out / 'ru.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="robots" content="noindex"><title>Proton / Potential has moved</title><p>This exhibit is now in English. <a href="./">Continue to the research story</a>.</p><script>location.replace("./"+location.hash)</script></html>')
    (out / '404.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Page not found</title><h1>Page not found</h1><p><a href="./">Return to Proton / Potential</a></p></html>')
    (out / '.nojekyll').write_text('')
    (out / 'README.txt').write_text('Proton / Potential — English research exhibit.\nServe this folder: python3 -m http.server 8000\nOpen http://localhost:8000/ . No remote runtime/CDN is required.\nAll molecular motion is display interpolation, never physical dynamics.\nDocumentation: ' + REPO + '/blob/main/docs/RESEARCH_SITE.md\n')
    (out / 'build-manifest.json').write_text(json.dumps({p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('build-manifest.json', '.proton-generated')}, sort_keys=True, indent=2) + '\n')
    return data


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / '_site')
    args = ap.parse_args()
    d = build(args.out)
    print(json.dumps({'status': 'PASS_ENGLISH_CINEMATIC_BUILD', 'science_commit': SCIENCE_COMMIT,
        'NEB_images': len(d['molecule']), 'force_frames_from_primary_data': len(d['forces']),
        'force_components': len(d['forces']) * 27, 'paired_seeds': 5, 'new_physical_calls': 0}))
