# PBE14 / MTP20 v001

Fourteen accepted raw PBE references and twenty saved model prediction CFGs.
Model bytes are not redistributed by this extension; the SHA registry binds each
prediction to its fixed model and paired seed. `INPUT_MANIFEST.json` authenticates
inputs. `SOURCE_TO_PUBLIC_MANIFEST.tsv` describes every imported file and any path-
prefix sanitization; derived result tables can be rebuilt with
`python3 tools/verify_pbe14_offpath.py --out <new-directory>`.

Eight direction/region blocks; three ± pairs and one singleton per region. Full
methods and caveats: `docs/COMPLETED_STUDIES.md`. Data are project-owned and covered
by LICENSE-DATA. No new scientific process is performed by reading or verifying.
