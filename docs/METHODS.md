# Methods summary

## Equal-budget design

Two Moment Tensor Potentials used identical architecture, hyperparameters, and
total DFT budget. Each used 36 shared configurations and 24 strategy-specific
additions: basin-focused or transition-focused.

## Primary frozen-path audit

Both models were evaluated on the same independent nine-image PBE NEB path.
Primary metrics were lower-endpoint barrier error and transition-region force
component RMSE.

## Secondary relaxed-path audit

The basin-focused path underwent a geometric collapse. The transition-focused
path remained close to PBE but had very large applicability grades and is
therefore secondary evidence only.

## Deployment applicability audit

Six endpoint-to-first-update tests were attempted at 100, 300, and 500 K for
the left and right minima. All six exceeded the predefined applicability
threshold after the first update.

## Frozen-path quantum-level audit

A one-dimensional stationary Schrödinger equation was solved using PBE,
basin-MTP, and transition-MTP energies on the same frozen PBE path.
