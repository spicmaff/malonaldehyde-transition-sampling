# Visual and factual acceptance

Status: PASS for the local presentation package. Public release and delivery are recorded separately in CURRENT_VISUAL_STORY.json.

Actual visual review: full-size proof frames A16, B3/B15/B29/B41, C7/C20/C33 and vertical11; final decoded contact sheets at the listed sample times for all five clips; consecutive motion strips; old/new comparison; Edge screenshots of the hero, chapters, metrics, seed charts and video controls. Inspection covers starts, intermediate movement, transitions and endings, not just ffprobe output. B/C intentionally hold static charts for reading. No real-time human viewing at full playback speed is claimed; motion was assessed from short preview and sequential decoded frames.

Defects corrected before acceptance:

1. Prototype molecule overlapped the heading: adjusted scene scale/center and checked both horizontal and vertical layouts.
2. Metric values overlapped bar fills: moved values above bars.
3. Long headings risked right-edge clipping: fit type to 1748 px width.
4. Direct crossfade produced doubled text: changed to a 0.55 s dip through the common background.
5. Narrow first screen exceeded the intended phone composition: responsive minmax columns and headline sizing, then actual 390 px CDP emulation.
6. Teaser inherited incompatible chapter progress bars: its own continuous 20 s progress and chapter label now replace them.

Technical review: all five MP4s fully decode, H.264 yuv420p with faststart. Four horizontal exports 1920×1080 and one vertical 1080×1920. Each is 60/1 fps with exact frame counts and durations:34/46/40/20/22 s, 9720 frames total. Motion intervals have 29/29 different adjacent decoded pairs at1/60 s cadence for both horizontal and vertical molecules. The renderer computes a new camera/geometry state at every frame; it does not duplicate an old 30 fps clip. Numerical geometry review checks 2001 display samples, monotonic qPT, unchanged atom order and no pair-distance collapse.

Factual review: a separate verification module reads saved source files directly, checks their hashes, recomputes the original barrier errors and all five seed win counts, confirms Replay228 crossings/max/stop, all11 raw force errors and retained guard FAIL. Original primary forces are also checked by the repository's saved-CFG arithmetic tests. Forty-six individual claim records retain scope/caveats; accepted science is unchanged. The review does not add independent DFT validation or a third-party scientific reviewer.

Browser: actual dedicated headless Edge, file://, desktop1440×1000 and emulated390×844. All5 videos load their metadata/frames (readyState4), native controls are present, no autoplay, Restart seeks to0 and plays. scrollWidth equals clientWidth; checked heading/chart/control bounds fit. Body text is20 px desktop/19 px mobile. Reduced-motion matches=true and scrolling becomes auto. Actual screenshots were inspected, including mobile numbers, seed charts and controls. Other browsers/physical phones were not individually tested. Horizontal graphs are best expanded or viewed landscape; the phone has a separately composed vertical episode.

Aesthetic assessment: the accepted design has readable editorial hierarchy, consistent color roles and calm motion. This is a design judgment, separate from measured numerical correctness and media integrity. No 4K or generative geometry is used. The files are silent by design.

Scientific boundaries: interpolated NEB display time is not physical time; γ indices are not time and γ is not force error. Endpoint overlap, pool24/K24, seed sensitivity, Validation11 independence/near cases, serialization FAIL and terminal Train119 STATIC_APPLICABILITY_FAIL remain disclosed. Blind12 stays closed, Gate1/dynamics are not invented, historical FAILs are retained. No scientific execution was performed for this presentation.
