# Proton / Potential — English cinematic exhibit

The active site is English-only. Build it from the repository root:

```bash
python3 tools/build_research_site.py --out _site
python3 -m http.server 8000 --directory _site
```

Open http://localhost:8000/ . No npm dependency is needed for the site itself.
Three.js is locally vendored with its MIT notice; browser test dependencies are
separate under `tools/site`. The complete essay and numerical tables are rendered
as static HTML before JavaScript enhancement.

The `cinema` directory contains new English 1080p/60 fps presentation captures.
The previous Russian-captioned media and article remain in the historical
presentation directory and release, not in this active build.

See [the full reconstruction and scientific boundary](../docs/RESEARCH_SITE.md).
