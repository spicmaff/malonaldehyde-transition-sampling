# Interactive research exhibit: Proton / Potential

The English-only exhibit is published at https://spicmaff.github.io/malonaldehyde-transition-sampling/. The legacy `ru.html` URL redirects to the English section; it is not a second edition. Its scientific snapshot is commit `f44d28cc0b13defb747f625376b083055b577629`, including the bounded Train119 diagnostic merged in PR #7. A later website commit does not change that scientific authority.

## Editorial and visual design

The exhibit has ten independently addressable sections: overview, molecule, sampling, energy landscape, five seeds, applicability, Train119, films, full longread, and reproduction. The ten-chapter English narrative is a revised account of the earlier v1.2.0 longread. It includes the October-5 diagnosis published on October 9. Each chapter has source links pinned to the scientific commit. The old longread and release remain unchanged.

The visual reference is [Memory / Geometry](https://spicmaff.github.io/rendezvous-grid-mazes/): warm paper, academic serif headings, teal/rust accents, understated panels and a matching dark theme. This site has its own molecular SVG renderer and source-derived plots. It does not copy the reference's automaton simulator or claim to perform a molecular simulation. System fonts are used; no font files, CDN libraries, analytics or external runtime services are shipped.

## Source layout and repeatable build

- `site/pages.py`: static English-only page renderer, including readable no-JavaScript content.
- `site/longread.en.md`: editorial source. `@sources:` directives become pinned links in both HTML and downloadable Markdown.
- `site/style.css`: light/dark, responsive and print presentation.
- `site/app.mjs`: route navigation, theme controls, SVG viewers and visual interactions.
- `site/core.mjs`: pure, independently tested coordinate/interpolation/display utilities.
- `site/assets/`: English-remastered video posters.
- `site/media/`: five English-title remasters of v1.2.0 MP4 assets, plus source-renderer SHA-256, English language and derivative manifest.
- `tools/build_research_site.py`: standard-library build and scientific extraction.
- `tools/site/test_site.py`, `test_core.mjs`, `browser_test.mjs`: offline, numerical and browser checks.
- `.github/workflows/research-site.yml`: checked build, browser evidence and Pages deployment from main only.

From a fresh checkout with Python 3.11+:

```bash
python3 -B tools/build_research_site.py --out _site
python3 -m http.server 8000 --directory _site
```

Open `http://localhost:8000/`. The build uses saved CFG/TSV/JSON and the existing Train119 verifier; it makes no network or scientific executable calls. Outputs include deterministic `data/science.json`, an evidence map with input SHA-256 values, one English HTML page plus a legacy-URL redirect, all runtime media, a downloadable English longread, and `build-manifest.json`. Two builds from identical sources must have identical manifests. Direct `file://` viewing preserves static content but browsers may block module/data loading; the small HTTP server resolves that restriction.

```bash
python3 -B tools/site/test_site.py
python3 -O -B tools/site/test_site.py
node --test tools/site/test_core.mjs
python3 tools/run_public_selftests.py .
```

The browser dependencies are pinned in `tools/site/package-lock.json`. Install them in a separate temporary directory, not the scientific repository:

```bash
QA_DEPS=$(mktemp -d)
cp tools/site/package.json tools/site/package-lock.json "$QA_DEPS/"
npm ci --prefix "$QA_DEPS" --ignore-scripts
BROWSER_DEPS="$QA_DEPS" SITE_URL=http://localhost:8000/ QA_OUT=site-qa-output \
  node tools/site/browser_test.mjs
```

The test uses system Google Chrome (`CHROME_PATH` overrides its location). Browser acceptance covers ten English sections × two themes × three widths (1440, 390, 320), keyboard controls, play/pause/reset, source values, legacy-URL redirect preserving the hash, deep links, reduced motion, all five videos playing and advancing, JavaScript failures, no-JavaScript reading, and WCAG-tagged axe checks. Automated accessibility checks do not replace manual usability review. CI retains screenshots and JSON reports.

## Data and plotting contracts

The NEB geometry and original pair metrics come from `data/frozen_models_v028/`. All 120 training records are projected using distances computed from their actual coordinates; exact candidate IDs establish 36 shared configurations. The visual axes are qPT and the O–O distance, not a learned free-energy surface. All 24 additional transition candidates were selected; no competitive subset-ranking advantage is claimed.

The two original models appear together with PBE in the energy panel. Each nine-point series is zeroed against its own lower endpoint. Connecting segments are display guides, not additional electronic-structure evaluations. Central force-component RMSE uses the three images with |qPT| ≤ 0.15 Å. Train119's larger adaptive model is shown in a separate diagnostic, never as a third equal-budget branch.

Five paired seeds are read from the authoritative robustness TSV. Their 64-bit identities remain strings in browser JSON, so JavaScript number rounding cannot corrupt them. All five pairs remain visible when a pair is highlighted. The descriptive counts are 4/5 barrier, 3/5 force and 3/5 both; no future win probability is estimated.

Replay228 gamma comes from the saved visual source and is cross-checked against the eleven later local records. Crossings are decided using the unrounded stop `1.0000012996964838`, never using formatted display values. Archive index is not a continuous physical time axis. The local force plot uses eV/Å on its own scale; A2 = 0.09 applies to each configuration's 27-component RMSE, not its maximum component. Separate segments and the development dependence are explicit.

The nine-atom display uses fixed O1/H2/O8 identity, a selectable display rotation and optional linear interpolation. Integer slider positions preserve exact saved geometry; intermediate coordinates/energies are visibly labelled as display interpolation. No physical clock, learned prediction or new force is implied. Reduced motion turns the continuous Play control into a discrete next-image step.

## Historical media and licensing

All five active films are English-title derivatives of the original v1.2.0 release. `tools/site/remaster_english_films.py` verifies the frozen renderer SHA-256, replaces its 70 Russian text constants with reviewed English titles, and switches decimal punctuation to English. Geometry, paths, timing, reference numbers and scientific scope are unchanged. The build is presentation rendering only. Original release files and historical `presentation/visual-story/v001` remain untouched.

To rebuild into a new directory (NumPy, Pillow and ffmpeg required):

```bash
python3 tools/site/remaster_english_films.py --out remaster-output
```

The English derivatives and posters were visually inspected across sixteen keyframes, fully decoded, and checked for original durations and 60 fps. Their hashes and source-renderer identity are in `site/media/manifest.json`. These are translated historical films, not the proposed future cinematic redesign. The Stage91J film retains its historical closure scope; later local diagnosis is explained separately. Native playback controls, preload=none and same-origin delivery remain.


Project-owned code is covered by the repository MIT license. Project-owned data and media follow its CC BY 4.0 declaration; retain attribution to Mikhail Fofonov. New styling/rendering code is project-owned; the Memory / Geometry design reference is acknowledged above. Node dependencies are development/CI tools only, not shipped site runtime. The existing MLIP patch retains its own separate third-party notice in the scientific package. No QE/MLIP binaries, UPF files or font files are included.

## Scientific boundaries

`SEED_SENSITIVE`, `STATIC_APPLICABILITY_FAIL`, endpoint overlaps, adaptive benchmark reuse and the historical serialization nonconformance remain visible. The diagnostic verifies local PBE-relative accuracy on selected development frames, not prospective independent generalization or deployment-ready reactive MD. PBE is an internal reference, not experimental truth. No Gate1/Gate2 result is invented; Blind12 is neither read nor distributed. The optional 1D H/D context remains a bounded spectral diagnostic, not an experimental rate model.

The repository's scientific arrays, frozen models, canonical ledgers, earlier presentation, release assets and tags are unchanged by this presentation layer. Pages uses a separate checked deployment artifact. A green site build means the exhibit and its saved-data contracts passed the documented checks; it does not mean a new physical experiment or a global scientific PASS.
