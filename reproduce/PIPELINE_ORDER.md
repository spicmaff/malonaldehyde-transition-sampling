# Pipeline execution order

The original stage scripts are preserved with their accepted versioned names.
Run them only inside a compatible project checkout.

```text
v024  independent PBE NEB
  ↓
v025  PBE single points on NEB9
  ↓
v026  transition-tube selection
  ↓
v027  equal-budget DFT labels
  ↓
v028  equal-budget L12 MTP training
  ↓
v029  frozen audit21
  ↓
v030  primary analysis
  ↓
v030r repaired authoritative primary metrics
  ↓
v031  secondary relaxed MTP-NEB
  ↓
v032/v032d first-update and interface diagnostics
  ↓
v033  closeout
```

Do not replace `v030r` with the unrepaired `v030` metric protocol when
reproducing the final barrier-error and transition-force numbers.
