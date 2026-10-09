# Proton / Potential — English cinematic site

The active site is English-only. The old language URL redirects to the same English section. Historical Russian presentation assets remain in their original release/presentation locations; copies previously bundled under this active site directory have been removed.

Build: `python3 tools/build_research_site.py --out _site`

Serve: `python3 -m http.server 8000 --directory _site`

Read `docs/RESEARCH_SITE.md` for complete architecture, motion definitions, source/provenance boundaries and browser checks. The public entry point is generated from `pages.py`; `longread.en.md` and `brief.en.md` are the full and short editorial texts. Scientific inputs are pinned by the builder to the accepted scientific commit. Neither the site nor the exporter performs physical simulations.

The molecular renderer is original Canvas2D code with rigid 3-D camera transforms and shaded atoms, not a WebGL physics engine. No font files or runtime CDN libraries are bundled.
