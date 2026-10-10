# Proton / Potential: English cinematic research exhibit

Live site: https://spicmaff.github.io/malonaldehyde-transition-sampling/

## Scope

The English exhibit presents the existing scientific evidence through a new molecular renderer, linked numerical views, a directed research sequence and an edited research essay. It does not change the frozen scientific models, reference calculations, selectors or historical outcomes. The scientific result snapshot remains `f44d28cc0b13defb747f625376b083055b577629`; immutable source links refer to the public baseline `3d430af343cf726d94ef8d2143fe7c24fa053c2b`.

The initial equal-budget comparison, its five-seed robustness audit, and the later adaptive Train119 diagnosis are distinct studies. `SEED_SENSITIVE` and `STATIC_APPLICABILITY_FAIL` remain visible. No Train119 deployment promotion, prospective independent test, experimental accuracy or general gamma/error calibration is claimed.

## Architecture

`tools/build_research_site.py` uses the unchanged scientific CFG parser and Train119 verifier. It derives the site JSON from public CFG, TSV, JSON, Quantum ESPRESSO `pw.out` and XML files. The force viewer's 297 reference components are parsed afresh from the eleven official QE blocks and matched to the preserved MTP outputs. XML agreement, atomic identity and existing RMSE results are checked during every build.

`site/pages.py` renders the English document, essay, numerical tables, evidence panels and reference list before JavaScript runs. `site/core.mjs` contains the pure coordinate, force and routing functions. `site/molecule.mjs` supplies a locally vendored Three.js renderer with a Canvas fallback. `site/charts.mjs` creates SVG graphics from the generated data. `site/app.mjs` synchronizes selections and finite animation sequences. No runtime CDN, remote API or account is required.

Ten addressable sections retain a short route to every source: overview, molecular path, training data, original profiles, five seeds, two diagnostic verdicts, atomic forces, directed story, essay and evidence. The old `#applicability` route resolves to the two-verdict view. Essay deep links expose the full essay. Unknown routes return to the overview.

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

The essay download contains real source and literature links rather than internal annotation tokens. `data/science.json` records immutable source URLs and hashes. `data/literature.json` records bibliographic identifiers, relevance, reading scope and limitations. The 18 selected references include original methods, nuclear calculations, uncertainty approaches and visualization research. They are not described as 18 completely read full texts: the access scope is explicit per record.

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

The `research-site` workflow uploads browser evidence, publishes the tested Pages artifact only from `main`, and keeps existing scientific workflows separate. Branch and pull-request jobs do not deploy. The usual science manifests and byte-preserving Git attributes remain in force.

## Third-party and research provenance

The small-molecule renderer vendors the unmodified Three.js 0.180.0 `three.module.js`, `three.core.js` and MIT license. `site/vendor/three/manifest.json` binds these to the npm distribution and hashes. No font files, QE/MLIP executables, pseudopotentials or third-party molecular artwork are redistributed. System fonts are used for interface and film rendering.

The visual family is informed by the owner's Memory / Geometry research site. MolViewStories and visualization literature inform the evidence-linked storytelling approach; their scientific scenes are not copied. External-paper results are labelled as context, never silently mixed with this project's numerical results.

The important boundary is unchanged: the site is a reproducible presentation of saved evidence, not a new physical experiment.
