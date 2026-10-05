# Visual story v1.2.0

This presentation release adds three new 1080p/60 fps chapters (34, 46, 40 seconds), a 20-second teaser, a separately composed 1080×1920/60 fps clip, posters, Russian full/compact longreads and a portable responsive HTML story. It uses saved scientific data. No new DFT, model training, inference, selector or dynamics calls are part of this release.

Download `MALONALDEHYDE_VISUAL_STORY_20261005_v001.zip` from [v1.2.0 assets](https://github.com/spicmaff/malonaldehyde-transition-sampling/releases/tag/v1.2.0), extract it and open `index.html`. If local video is restricted, run `python -m http.server 8000` in the extracted folder. No CDN, login or private project tree is needed. Video controls include native Play/Pause and a Restart button; reduced motion disables smooth page scrolling.

The repository copy is `presentation/visual-story/v001/`. It includes posters, HTML, text and source documentation. Large final MP4 files are release assets. To populate the repository copy locally:

```bash
python scripts/visual_story/render_visual_story.py --data data/visual_story/v001 --out presentation/visual-story/v001/media --kind all
```

To rebuild the editorial page into a new directory:

```bash
python scripts/visual_story/build_story.py --data data/visual_story/v001 --baseline data/visual_story/v001/editorial_baseline --out render-output/visual-story
python scripts/visual_story/render_visual_story.py --data data/visual_story/v001 --out render-output/visual-story/media --kind all
```

Dependencies: `requirements.txt`, ffmpeg with libx264 and DejaVu Sans system fonts. The first command performs publication rendering only; saved data and display interpolation are kept distinct. Source/hash/scene roles are in `sources/MEDIA_SOURCE_MANIFEST.tsv`. License notes are in `sources/THIRD_PARTY_NOTICES.md`.

The scientific boundary remains v1.1.2. Original v030r numbers are unchanged; targeted wins in 4/5 barrier, 3/5 force, 3/5 both seed pairs, with SEED_SENSITIVE status. Two NEB endpoint overlaps remain disclosed. Train119 remains STATIC_APPLICABILITY_FAIL, five Replay228 crossings at143–147, raw Validation11 errors below A2 with independence and serialization caveats. Force-accuracy failure and deployment readiness are not established. Blind12 remains unrevealed. Historical scientific assets and old media/tags are preserved.

Visual QA includes real frame/transition inspection, full decoding, actual 60 fps frame counts, changing consecutive motion frames and browser testing at1440×1000 and390×844, Play/Restart, relative file loading and reduced motion. CI includes actual short video encoding and editorial generation in addition to the existing scientific-asset tests. CI does not rerun physical science or certify subjective aesthetic quality.
