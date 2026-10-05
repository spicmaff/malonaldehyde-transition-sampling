# Canonical ledger reconciliation (v1.1.2)

The current source-bound ledger is [V005](../provenance/PROJECT_CANONICAL_LEDGER_V005.tsv), identified by [CURRENT_CANONICAL_LEDGER.json](../provenance/CURRENT_CANONICAL_LEDGER.json). V003 and V004 remain historical snapshots. Their presence does not make their old classifications current.

Seven record classes were corrected after reading the verdict sources: the interrupted v024 NEB process is a technical failure; Stage76E is a successful read-only postmortem; Stage89T-R1 and Stage89U are successful review/closure of an earlier technical failure; Stage90J and Stage90K are successful recovery review/closure of Stage90I; Stage90Q is a recorded serialization failure. Successful reviews are marked AUTHORITATIVE_WITH_CAVEAT, without promoting the reviewed model or erasing the previous failure.

The old classifier matched FAIL inside FAILURE and in labels referring to earlier stages. A version-specific adjudication now separates stage_own_status from preserved_scientific_outcome. PASS is not a universal scientific acceptance: Stage89I preserves a negative applicability interpretation and Stage89W records NOT_READY_FOR_GATE1. Stage91J remains TECHNICAL_FAIL and Stage91L remains SCIENTIFIC_FAIL with STATIC_APPLICABILITY_FAIL. All twelve genuine scientific-negative records remain negative. Original Stage85B remains superseded by corrected energy-row R1.

Twenty-one authority bindings were repaired, including the ten post-completion placeholder authorities. The ledger has 290 unique stage/attempt identities; 235 have authenticated compact source documents and 55 remain inventory-only without located terminal sources. UNKNOWN accounting values are preserved.

The separate private source review passed 313 checks. Public selftests check source excerpts, source identities, accepted classes and stage/outcome separation, and reject twenty mutations of actual ledger records. They do not independently rerun all historical scientific calculations. Compact excerpts identify raw source hashes; full late-stage provenance remains in the private project tree.

No DFT, training, MTP selector/inference, dynamics or Blind12 disclosure was performed for this reconciliation. The original locked v028 numbers, five-seed SEED_SENSITIVE result and negative Train119 terminal status are unchanged. The historical RNG evaluation-order deviation and its completed evaluation-only repair remain explicit.
