# Proton / Potential: English cinematic research exhibit

Live site: https://spicmaff.github.io/malonaldehyde-transition-sampling/

## Scope

The English exhibit presents saved scientific evidence through a molecular renderer, linked numerical views, a directed research sequence and an edited research essay. The original scientific result snapshot remains `f44d28cc0b13defb747f625376b083055b577629`; the original `science.json` source links retain baseline `3d430af343cf726d94ef8d2143fe7c24fa053c2b`. Later additive studies have their own source revisions. The optimization review identifies its existing public inputs at verified baseline `f5f4784d7cc186ae9cfcacbd97117b5dabbffb30`.

The initial equal-budget comparison, its five-seed robustness audit, and the later adaptive Train119 diagnosis are distinct studies. `SEED_SENSITIVE` and `STATIC_APPLICABILITY_FAIL` remain visible. No Train119 deployment promotion, prospective independent test, experimental accuracy or general gamma/error calibration is claimed.

The published exhibit includes `#offpath`. This branch adds a review version of
`#optimization`; its local or packaged preview must be identified separately from
the production URL above. [Optimization methods and evidence tiers](OPTIMIZATION_STORY.md)
· [Public/private boundary](PUBLIC_PRIVATE_BOUNDARY.md).

## Architecture

`tools/build_research_site.py` uses the unchanged scientific CFG parser and Train119 verifier. It derives the site JSON from public CFG, TSV, JSON, Quantum ESPRESSO `pw.out` and XML files. The force viewer's 297 reference components are parsed afresh from the eleven official QE blocks and matched to the preserved MTP outputs. XML agreement, atomic identity and existing RMSE results are checked during every build.

`site/pages.py` renders the English document, essay, numerical tables, evidence panels and reference list before JavaScript runs. `site/core.mjs` contains the pure coordinate, force and routing functions. `site/molecule.mjs` supplies a locally vendored Three.js renderer with a Canvas fallback. `site/charts.mjs` creates SVG graphics from the generated data. `site/app.mjs` synchronizes selections and finite animation sequences. No runtime CDN, remote API or account is required.

The original ten addressable sections retain their routes: overview, molecular path, training data, original profiles, five seeds, two diagnostic verdicts, atomic forces, directed story, essay and evidence. The published `#offpath` chapter is the eleventh; the additive review `#optimization` is the twelfth. The old `#applicability` route resolves to the two-verdict view. Essay deep links expose the full essay. Unknown routes return to the overview.

## Scientific display rules

The nine true NEB supports are distinguished from interpolated display frames. Coordinate interpolation is linear between neighboring saved Cartesian images; displayed distances are recomputed from the interpolated geometry and displayed energy is explicitly interpolated between the saved values. Neither a physical clock nor a tunneling trajectory is inferred.

The camera is orthographic. The same rigid transform is applied to coordinates and force arrows; x and y are not independently rescaled. Sphere radii, materials, shadows and connectivity rods are illustrative. Dashed O–H segments are distance guides, not evaluated bond orders.

The force table remains in the original laboratory frame. Arrow length is proportional to force magnitude using one user-selected global scale: at 1×, 1 eV/Å is represented by one model-space Å. Arrows are not displacements. PBE, MTP and their difference are not normalized independently. H2* and C3/y remain distinct.

Energy profiles use each series' own lower endpoint as zero. The original-model view never silently substitutes Train119 for one of the equal-budget branches. Train119 has its own development-only profile and residual panel. The latter exposes the difference between a 0.122996 meV barrier error and approximately 0.504072 meV maximum relative-profile error.

The coverage view shows `(gamma - stop) * 1000`, with the rescaling stated on the axis. Force RMSE uses a separate panel and eV/Å units, retaining A2 = 0.09. The two recorded trajectory segments are selected independently in the interface and are never joined into a fictitious continuous trajectory. The numerical stop is not altered.

All five paired seeds remain visible after their reveal. Their 64-bit identities are strings. No inferred distributions or confidence bands are added.

## English-only migration and historical media

There is no active Russian localization, language switch or Russian essay in the new build. The legacy `ru.html` is only a minimal English redirect, preserving its hash. Historical Russian source materials and the v1.2.0 release remain unchanged in their original locations.

The former active `site/media` copies and Russian-captioned posters are no longer embedded or copied into the Pages artifact. New English cinematic editions live under `site/cinema/`, with frame rate, duration, frame count, source snapshots and SHA-256 recorded in their manifest. The silent historical films remain accessible only through an explicitly labelled archive link.

## Rebuilding

The scientific build needs Python 3.11 or later and the standard library:

```bash
python3 tools/build_research_site.py --out _site
python3 -m http.server 8000 --directory _site
```

Open `http://localhost:8000/`. The output must be empty or carry this builder's ownership marker. Rebuilding removes only previously manifested generated files from that output, preventing stale Russian pages or obsolete media from persisting. The builder refuses repository or scientific-source destinations.

The essay download contains real source and literature links rather than internal annotation tokens. `data/science.json` records immutable source URLs and hashes. `data/literature.json` records bibliographic identifiers, relevance, reading scope and limitations. The 21 selected references include original methods, nuclear calculations, uncertainty approaches and visualization research. They are not described as 21 completely read full texts: the access scope is explicit per record.

## Re-rendering the English films

Install the locked browser-test dependencies separately from the site:

```bash
npm ci --prefix tools/site --ignore-scripts
BROWSER_DEPS="$PWD/tools/site" SITE_URL=http://localhost:8000/ \
  CINEMA_OUT=/path/to/new-empty-render-directory \
  node tools/site/render_cinema.mjs
```

Chrome and ffmpeg with libx264 must already be installed. The renderer captures deterministic scene positions at 1920×1080 and encodes 60 frames per second. The 12-second molecular edition and 30-second six-scene story are presentation exports, not recorded molecular simulations. Existing render destinations are not overwritten. The manifest contains checksums and the expected 720/1800 frame counts; ffprobe and full decoding are part of the renderer's acceptance.

Encoded frame rate is not a promise that every device renders the interactive WebGL scene at a sustained 60 fps. Browser reports state the measured environment and timing distributions instead.

## Tests and deployment

```bash
python3 tools/site/test_site.py
python3 -O tools/site/test_site.py
node --test tools/site/test_core.mjs
python3 tools/run_public_selftests.py .
```

The browser runner uses `BROWSER_DEPS`, `SITE_URL`, `QA_OUT` and optional `CHROME_BIN`. Set `REQUIRE_FILMS=1` for complete acceptance. It tests 100 route/theme/viewport combinations at widths 1920, 1440, 768, 390 and 320, scientific controls, atom/frame selection, exact and interpolated states, both English films, the legacy redirect, reduced motion, Canvas fallback, no-JavaScript reading and a failed-data-request fallback. WCAG-tagged axe checks run in the documented scope; they are not a complete accessibility certification.

The complete review matrix also requires the off-path and optimization runners,
each covering five widths and two themes. Together the three route sets cover
120 distinct route/theme/viewport combinations. The optimization-specific runner
must exercise its finite sequence, keyboard controls, focus, reduced motion,
no-JavaScript reading and failed-payload fallback. Test commands and the boundary
between required checks and completed evidence are recorded in
[the optimization guide](OPTIMIZATION_STORY.md#review-preview-and-reproduction).

The `research-site` workflow uploads browser evidence, publishes the tested Pages artifact only from `main`, and keeps existing scientific workflows separate. Branch and pull-request jobs do not deploy. The usual science manifests and byte-preserving Git attributes remain in force.

## Third-party and research provenance

The small-molecule renderer vendors the unmodified Three.js 0.180.0 `three.module.js`, `three.core.js` and MIT license. `site/vendor/three/manifest.json` binds these to the npm distribution and hashes. No font files, QE/MLIP executables, pseudopotentials or third-party molecular artwork are redistributed. System fonts are used for interface and film rendering.

The visual family is informed by the owner's Memory / Geometry research site. MolViewStories and visualization literature inform the evidence-linked storytelling approach; their scientific scenes are not copied. External-paper results are labelled as context, never silently mixed with this project's numerical results.

The site build reads saved evidence and performs no new physical experiment.
Public sources support the original and completed-study numerical reconstruction.
The optimization review additionally presents private native evidence through
explicitly selected public aggregates; a private-source checksum does not make
its full underlying experiment publicly reproducible.


## Additive completed-study chapter

The `#offpath` route has its own `proton-offpath-v1` payload and independent builder
`tools/build_offpath.py`. It never substitutes PBE14 for the eleven Train119 force
frames or changes the original `science.json` numerical arrays. A compact extension
adds the page and navigation link after rendering the existing ten pages. That
extension retains the original molecular presentation and both films; its separate
payload does not replace the original scientific arrays. The new optimization
review follows the same additive arrangement, with its own assets and route.

`site/offpath_page.py` renders static charts, definitions, geometry roles and all280
case values before JavaScript. `site/offpath.mjs` supplies the shared molecular stage,
a finite five-pair reveal, labeled fixed-axis contrasts, two-region budget comparisons
and source-derived filters. No PBE14 interpolation or forces-as-displacements is shown.
The filters cannot remove pairs from the primary chart. `offpath.css` is additive and
uses the original palette and typography. Raw data hashes and source revision accompany
the separate payload. Exports are based on actual saved arrays, not copied UI constants.

The old browser runner now waits for route activation before clicking. This fixes an
observed test race; scientific assertions and original route checks are not weakened.
The additional `tools/site/browser_offpath_test.mjs` covers ten responsive/theme views,
24 direction filter combinations, all14 actual geometries, finite reveal and keyboard,
no-JS, request failure, reduced-motion, Canvas and real TSV download content.

## Additive optimization review chapter

`tools/build_optimizer_story.py` validates the committed
[`data/optimization_story/v001`](../data/optimization_story/v001/README.md) boundary
and supplies the same canonical payload to `site/optimization_page.py` and
`site/optimization.mjs`. The Python page renders definitions, charts, state values,
scope notes and tables before JavaScript. The module adds finite manual or played
state selection; `site/optimization.css` scopes the chapter's presentation. The
full-site builder integrates the chapter after the original exhibit and off-path
extension. Runtime network services and private-file access are unnecessary.

Native J, fixed-D row objective Q and external force RMSE have different
definitions and appear separately. The main4500 display uses a declared log scale
for positive native J values; the large S1 value cannot silently set a clipped or
moving scale. S1c and S2q are diagnostic branches, and S3 has no independently
measured objective. Missing values remain missing in static HTML, charts and
downloads. The short main50 control reports a decrease, preventing the selected
long-run example from becoming a claim that every refit is harmful.

The chapter's six modules connect the 248-parameter representation, one periodic
interruption, checkpoint selection, a constrained COV candidate, T0/T1/T2 evidence
and the existing seed/off-path/Train119/reproduction views. The essay's original
thirteen section headings and anchors remain; section fourteen extends the
discussion through `@study: optimization`. It does not introduce new literature
records or change the two English film assets.

The proposed COV saved-row decrease is separated from both physical model
evaluation and historical synthetic engineering. Historical T1 remains
`T1_PASS_ENGINEERING_SYNTHETIC_ONLY`. Necessary diagnostic recovery used one real
training and six detached replays; its count is separate from T1's zero real-data
fits. The old XI missing-journal and P1 runtime-snapshot failures remain visible,
and TERMINAL PBE14 has a saved-error-table reaggregation tier. T2 and independent
external validation remain unexecuted. The
[claim map](../data/optimization_story/v001/CLAIM_DATA_MAP.tsv) and
[provenance registry](../data/optimization_story/v001/PROVENANCE.json) identify the
support and limits for every class of result.

Review acceptance must preserve the original Python/Node/scientific assertions,
the old route interactions and both media files, while adding meaningful
optimization checks. Browser automation should wait for actual route and scroll
stability before clicking a moving target; synchronization repairs must retain
the existing behavioral assertions. A successful build alone is not a browser
or scientific acceptance receipt. Final review evidence belongs to the actual
tested branch revision and its CI/browser artifacts.
