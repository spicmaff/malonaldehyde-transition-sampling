# Scientific editorial edition

Baseline: `76e0e22967f408480b5a713d8f94f6c9e9981105` (the complete public site, including Optimization).
Branch: `scientific-editorial-redesign`. The existing Pages deployment is not changed by this branch.

## Changes and evidence

| Change | Source and reason | Acceptance criterion |
| --- | --- | --- |
| Show training and PBE path together | Train60 CFG coordinates, saved NEB supports and `generate_tube`; an endpoint-linear tube misses the contracted O–O region | Both panels retain 60 training marks and nine reference supports, use identical domains and show the training floor; seven internal supports are below it |
| Link saved geometry and energy | The nine original coordinates and relative energy arrays | Keyboard image selection updates the molecule, marker and distances without generating intermediate physical states |
| Explain PBE14 budget dependence | 14 reference blocks, 20 prediction CFGs, 280 case errors, 160 physical-block means and raw stop logs | Reproduce the predeclared primary contrast; show both absolute errors at both caps; keep arithmetic decomposition distinct from causal diagnosis |
| Add block-weight sensitivity | Same arrays, new descriptive aggregation | Leave-one-block-out and equal-geometry means are explicitly exploratory and do not replace the primary endpoint |
| Separate optimization quantities | Public main4500/ROW_EXACT_FIXED_D aggregates, COV theorem and evidence-availability declaration | Q identity holds; saved-row loss increase is visible beside penalty reduction; missing matrices/native E/F are disclosed near the claim |
| Correct bibliography | Brezina, Beck and Marsalek, primary arXiv:2303.15521 / DOI 10.1021/acs.jctc.3c00391 | Hubert Beck replaces Harald Beck; publication scope is preserved |
| Reorganize the narrative | Five distinct experiment identities | All twelve historical routes, source anchors, static essay and original metric definitions still work |
| Improve reading and interaction | Warm paper/forest/teal/terracotta palette, editorial spacing, round ticks, shapes/dashes, manual controls | Desktop/mobile and both themes have no page overflow; controls work with keyboard; reduced motion and data/WebGL fallbacks retain the result |

## Architecture and scientific identity

`site/editorial.py` is the final fail-closed refinement in the existing Python builder. It adds static scientific scenes, methods and scope disclosures, reorders the existing page sections and copies `editorial.css`. Every build independently reruns `tools/verify_editorial_findings.py` and compares it with `docs/editorial-findings.json`; the identical payload is published as `data/editorial.json`. Historical scientific arrays, models, films, identifiers and the original payload schema are untouched.

`site/app.mjs` connects the two new molecular inspectors to the existing renderer. Sampling overlays use the actual path descriptors. Energy comparison limits remain fixed when a branch is hidden. `niceTicks` supplies round ticks without moving the fixed domain. All animations start by explicit user action. The complete data remain visible before playback and after it. Molecular arrow scaling is unchanged.

`provenance/EDITORIAL_REDESIGN_DELTA.tsv` is a third explicit provenance layer. It validates each preceding hash against the original manifest plus the earlier review layer. Its fixed path allowlist excludes historical scientific arrays. Neither older manifest is rewritten.

## Verification

```sh
python3 tools/verify_editorial_findings.py --check
python3 -m unittest discover -s tests -p test_editorial.py
python3 tools/site/test_site.py
python3 -m unittest discover -s tests
node --test tools/site/test_core.mjs tools/site/test_editorial.mjs
python3 tools/run_public_selftests.py
python3 tools/build_research_site.py --out _site
```

The existing GitHub browser runner includes `tools/site/browser_editorial_test.mjs`: linked selection, molecular keyboard rotation, stable energy axes, 42 width/theme/chapter accessibility checks and controlled before/after screenshots against the baseline above. Existing browser suites additionally cover all routes, 320–1920 px widths, both themes, animations, fallback, source failures and original science contracts. CI screenshots are evidence of a headless browser, not a real-device or hardware-GPU certification.

The session's managed preview supervisor was unavailable. No substitute local server or browser infrastructure was introduced. Offline checks can be executed here; runtime-browser results must come from the actual GitHub run or the separately hosted review version. The Russian scientific report is [EDITORIAL_RESEARCH_REVIEW_RU.md](EDITORIAL_RESEARCH_REVIEW_RU.md).

## Open research work

An independent comparison should place fresh labels along a contracted relaxed path, vary allocation seeds as well as optimizer seeds, lock the cost/checkpoint policy and reserve genuinely unused physical tests. PBE numerical convergence needs a dedicated cutoff/cell/path study with its own identity. The native optimizer archive must be recovered before making a native reproduction claim; an exported COV candidate needs native energy/force parity and external accuracy tests. None of these new physical experiments is claimed by the website redesign.
