# Publication metadata cleanup

Published source: `51c96a7034567006b803a92124b67e2333ba7b4e`.
Tree: `f872b16d606d65edf7ca5c6447e4417ddb86adcf`.
Public site: https://spicmaff.github.io/malonaldehyde-transition-sampling/.
Workflow: https://github.com/spicmaff/malonaldehyde-transition-sampling/actions/runs/39871765043.

The source removes service-specific referral values, former private preview
addresses and deployment paths from the current public copies. Scientific
arrays and the earlier provenance manifests are unchanged. The report exports
explicitly identify their editorial changes and retain source/export hashes.
Original snapshots remain accessible through Git history.

All 201 Python tests passed on this exact source commit. The final workflow
passed all 35 JavaScript tests and all four browser runners: editorial,
cinematic, off-path and optimization acceptance. Both the site-check and
deployment jobs completed successfully. This is a publication and presentation
check; the research limitations described on the site remain applicable.

`PUBLISHED_RESOURCE_PARITY.json` binds all 53 deployed runtime resources to the
clean source build. `CANONICAL_URL.json` separately checks the ordinary public
address and its build identity without a version query. `CONTINUITY.json`
confirms that rendered content and scientific payloads are unchanged after
normalizing the source commit labels and source links.

CI logs are exact decoded job logs with public runner home paths normalized to
`/home/USER/`. The local JavaScript log predates creation of the final commit
object; its input bytes are identical, and the final CI log records the fresh
run on the published source. Statuses are specific to the named jobs and do not
assert completion of unrelated reproduction jobs.
