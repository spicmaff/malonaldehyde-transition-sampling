# Reproduce the visual presentation

Requires Python 3.11+, numpy, Pillow, ffmpeg (libx264), and system DejaVu Sans fonts. No MLIP, QE, selector, training or dynamics calls. From this package root:

```bash
python sources/render_visual_story.py --data sources/inputs --out rerendered --kind all
```

For the repository use `python scripts/visual_story/render_visual_story.py --data data/visual_story/v001 --out render-output/visual-story --kind all`. `--validate-only` checks saved scientific inputs and 2001 display-interpolation samples; `--proof` renders a four-second excerpt and review frames.

Frames stream directly to ffmpeg, without a frame-directory storage requirement. All charts use compact saved values. Renderer parameters and display interpolation are described in VISUAL_SYSTEM.md / STORYBOARD.md. Static pauses are intended for reading; changing NEB/camera frames are genuinely sampled at 60 fps.
