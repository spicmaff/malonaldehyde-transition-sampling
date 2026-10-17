# Engineering corrections retained in review history

No new scientific programs were run. The raw reference/prediction/log arrays and
metric definitions did not change during these corrections.

1. The historical browser test changed routes and clicked immediately. A reproduced
baseline timing failure was corrected by waiting for route activation (including
query-string routes). No assertion or route was removed.
2. Git text normalization affected a CRLF-containing source table during initial
staging. The completed-study subtree now uses explicit byte-preserving attributes;
a fresh archive/checkout reproduces original/public hash contracts. No input was
rounded or rewritten to make a comparison pass.
3. Python3.11 and3.12 use different built-in floating summation details. The first
remote CI rejected the last decimal places of a figure4 SVG coordinate, while all
280 scientific metrics matched. Explicit math.fsum in the plotting aggregation
fixes cross-version serialization. Exact figure-rebuild assertions remain enabled.
4. Browser navigation to a downloadable TSV triggers attachment handling rather
than a document navigation. The test now fetches the actual HTTP response and
checks status200 plus exactly280 data rows; it does not skip download verification.

Earlier failed engineering runs remain in Git/CI and local evidence. Subsequent
passing results must be bound to their actual candidate commit, not the baseline.
