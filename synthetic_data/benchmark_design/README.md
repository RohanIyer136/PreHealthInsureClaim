# Design-Only Synthetic Inputs

`cases.json` contains 36 synthetic scenario specifications; `policies.json`
contains six project-authored fictional product designs. Neither file contains
golden answers. These records are not production authorization/member-policy
instances and are not loaded by the application or demo endpoints.

All scenarios are DESIGN_ONLY. Only the lumbar examples reference an existing
implemented clinical vertical; other domains require future authoritative
knowledge and explicit implementation. No production clinical coverage is implied.
All patients are synthetic and have only age/sex demographics, without personal
identifiers. Fictional products are not real contracts or clinical guidelines.

See [the design and matrix](../../evaluation/MULTIDOMAIN.md) for policy details,
controlled comparisons, emergency/negative/adversarial cases, support limitations,
and the separate evaluation contract. Golden specifications live under
`evaluation/`, never in these source inputs or production model context.
