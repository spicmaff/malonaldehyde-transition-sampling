# Abstract — draft for author review

Training-data placement is only one determinant of the accuracy of a fitted molecular
potential. We examine a small-data moment tensor potential case study for proton
transfer in malonaldehyde using two fixed60-configuration allocations:36 shared
configurations and24 additions near either the minima or the transition region.
Five matched initialization seeds and main optimization caps of2000 and8000 steps
produce twenty saved model endpoints, all terminated by the step limit. Their forces
are compared with completed PBE references on fourteen prespecified local transverse
geometries arranged into four physical blocks near each of two previously known
path anchors. The primary endpoint averages component force RMSE within each block,
then equally across the four transition-region blocks at cap8000. Targeted minus
Basin is negative for 4 of five seeds, with mean
-0.146135 and median -0.140839 eV/Å. The larger transition advantage at8000
coexists with worsening Basin error and a basin-region disadvantage for Targeted.
Independent saved-data reconstruction reproduces all280 model–geometry errors.
These observations support a conditional relationship between fixed data placement,
initialization and finite optimization budget, rather than a universal superiority
of one sampling policy. The local correlated geometry design, single PBE reference
and step-limited endpoints do not establish global potential-surface accuracy or
reactive-dynamics reliability.

No new electronic-structure or model-training calculations were performed during
repository/publication preparation. This is an author-editable draft, not a journal submission.
