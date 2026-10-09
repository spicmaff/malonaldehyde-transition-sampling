# Proton / Potential — English cinematic research exhibit

Public site: https://spicmaff.github.io/malonaldehyde-transition-sampling/

The exhibit is an English-only, progressively enhanced static research story. Its scientific authority is pinned to commit `f44d28cc0b13defb747f625376b083055b577629`; the later presentation does not rerun or amend the physical experiments. Original v028 models, reference CFGs, the Train119 evidence package, historical ledgers and release assets are unchanged.

## Architecture

`tools/build_research_site.py` reconstructs browser data from public CFG, TSV and JSON inputs, calls the existing Train119 verifier, and renders `site/pages.py` plus the edited English longread. `site/core.mjs` contains testable numerical display operations; `molecule.mjs` implements a uniform orthographic 3-D camera with shaded Canvas2D atoms and bonds; `charts.mjs` implements dependency-free SVG plots; `app.mjs` links the state, scenes and manual controls. No frontend framework, CDN, tracking service, web font or backend is required at runtime.

The eleven routes are overview, molecule, sampling, landscape, seeds, applicability, train119, forces, story, longread and reproduce. Original hashes remain supported. The former `ru.html` is only an English `noindex` redirect preserving the hash; it is not a second edition. No Russian longread, localization runtime or Russian-title film is included in the built site.

## Rebuild and test

From a clean clone, with Python 3.11 or later and Node 22:

```bash
python3 tools/run_public_selftests.py .
python3 -B tools/site/test_site.py
python3 -O -B tools/site/test_site.py
node --test tools/site/test_core.mjs
python3 tools/build_research_site.py --out _site
python3 -m http.server 8000 --directory _site
```

The builder has no network or subprocess dependency. It rejects repository/source output paths, and refuses to clear an unrelated existing directory. A known generated directory can be rebuilt without retaining stale translated pages or obsolete media. Full source SHA-256 identifiers and pinned URLs are in `data/science.json`; `build-manifest.json` identifies the output bytes.

For browser QA, install the locked development-only dependencies outside the repository:

```bash
mkdir -p /tmp/proton-browser
cp tools/site/package.json tools/site/package-lock.json /tmp/proton-browser/
npm ci --prefix /tmp/proton-browser --ignore-scripts --no-audit --no-fund
BROWSER_DEPS=/tmp/proton-browser SITE_URL=http://127.0.0.1:8000/ \
  QA_OUT=/tmp/proton-qa node tools/site/browser_test.mjs
```

A system Chrome/Chromium executable is needed; `CHROME_PATH` overrides the default. The CI workflow performs this check on an HTTP-served build, not injected HTML. It retains the QA JSON and screenshots and deploys the same tested artifact to Pages only from `main`.

## Motion with an explicit scientific boundary

Eight guided sequences share the same state as their manual tools:

| Sequence | Duration | What changes |
|---|---:|---|
| Molecular hero | 18 s | Camera, molecular structure and synchronized PBE profile |
| Proton and scaffold | 16 s | Saved-image position, distances and oxygen contraction |
| Learning locations | 10 s | Staged visibility of actual common36 and two sets of 24 |
| Original energy comparison | 12 s | Selected saved image and its profile residual |
| Five paired seeds | 14 s | Sequential reveal, ending with every pair visible |
| Two diagnostic verdicts | 10.5 s | Discrete saved frames, separate gamma and force-error axes |
| Inside the force error | 9 s | PBE vector, MTP vector, then their difference |
| Scientific journey | 48 s | Six source-backed narrative acts |

These are presentation durations, not reaction times. Interpolated molecular states are labeled as display interpolation. Only the nine exact NEB images are calculated structures. Energy interpolation is not a new energy evaluation. Bonds are connectivity/distance guides, not computed bond orders. Statistical plots do not fabricate uncertainty bands or additional seeds. Playback stops on route changes and when the tab becomes hidden. Reduced motion retains manual inspection without continuous playback.

The renderer rotates atoms and force vectors using the same orthonormal matrix. It never scales the spatial axes independently. Reported force components remain in the source coordinate frame, while a selected vector is rotated for viewing. Arrow magnification is a stated display parameter; the 3-D norm does not depend on camera angle.

## Force-vector provenance

All eleven local PBE force arrays are reparsed from each public `pw.out` official total-force block and checked against its XML. Frozen prediction CFGs supply MTP values. Component differences and the 27-component RMSE are recomputed and checked against the accepted diagnostic. H2 and C3 are separate atoms. These operations read stored arrays; they do not invoke MLIP or Quantum ESPRESSO.

## English motion previews and historical media

`site/cinema` contains the new English presentation clips, their posters and a SHA-256 manifest. They are exported through the same deterministic seek API as the website. Reproduce the clips with system ffmpeg and Chrome using `tools/site/render_previews.mjs`; set `BROWSER_DEPS`, `SITE_URL` and a new `CINEMA_OUT` directory. The exporter refuses to overwrite existing clip files. It emits 1920×1080, 60 fps H.264 files. Discrete diagnostic selections intentionally hold their saved values; the encoding rate is not a physical sampling frequency.

The original v1.2.0 movies have Russian text embedded in their frames. They are not part of the active English exhibition. Their original release assets and historical presentation sources remain preserved. The new clips do not overwrite those releases. A direct archival link makes this distinction explicit.

## Literature, interpretation and licensing

`site/literature.json` contains the curated scholarly context, DOI links, access depth and a specific limitation for each entry. The research narrative distinguishes full-dimensional quantum results, reduced Hamiltonians, experimental observables and internal PBE-reference accuracy. It does not transfer benchmark precision from a published PES onto this project's potential. Publisher figures and prose are not reproduced; the molecular scenes and charts are generated from project-owned data.

Source code is covered by the repository's own license. Project-owned data and newly rendered media follow the repository's stated data/media license. Existing third-party notices, including the narrow MLIP patch notice, remain separate. Only system fonts are used; no font files or external scientific executables are distributed. Puppeteer and axe are locked QA-only dependencies, not shipped browser libraries.

## Nonclaims

`SEED_SENSITIVE` and `STATIC_APPLICABILITY_FAIL` are retained. The known endpoint overlaps and correlated development segments remain explicit. Train119 is not a third equal-budget branch. PBE agreement is not experimental validation. No new inference, model training, DFT, selector/grading, MD, Gate1/Gate2 or Blind12 access is performed by the build or the exhibit.

Automated accessibility checks and timing measurements cover the tested browsers and screens; they are not a complete accessibility certification or a universal guarantee of 60 fps on all devices. GitHub Actions verify saved-data reproduction and site behavior, not the complete historical physical workflow.
