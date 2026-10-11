# Contributing

Edit per-file YAML, not the aggregates:

- Modules: `registry/modules/<module_id>.yaml`
- Bundles: `bundles/<bundle_id>.yaml`

For registry edits, rebuild the production aggregates and validate once.
For other code changes, exercise only the affected shipped command when actual
acceptance evidence is needed; see [local acceptance](docs/LOCAL_VALIDATION.md).

```bash
cwr pack
cwr validate
```

Ordinary pytest discovery is disabled. There are no routine unit/integration,
registry-count, publication-hash or broad historical test gates. Retained
historical sources are reproduced only for a named evidence obligation at their
recorded revision. Runtime safeguards and prospective research requirements
remain in force.

Keep stable IDs (`module_id`, `question_id`, `bundle_id`, `criterion_key`) unless you are adding a new record. New leaves need a new `criterion_key` that no other module owns.

Phrase every leaf so `YES` is a pass. Hard requirements are `hard_gate`. Genuinely gestalt judgments stay on the holistic ladder; do not atomize taste into fake objectivity.

Do not add an application-level creative-content permission taxonomy.
