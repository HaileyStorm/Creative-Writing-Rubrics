# Contributing

Edit per-file YAML, not the aggregates:

- Modules: `registry/modules/<module_id>.yaml`
- Bundles: `bundles/<bundle_id>.yaml`

Then rebuild and check:

```bash
cwr pack
cwr validate
pytest
```

Keep stable IDs (`module_id`, `question_id`, `bundle_id`, `criterion_key`) unless you are adding a new record. New leaves need a new `criterion_key` that no other module owns.

Phrase every leaf so `YES` is a pass. Hard requirements are `hard_gate`. Genuinely gestalt judgments stay on the holistic ladder; do not atomize taste into fake objectivity.

Do not add an application-level creative-content permission taxonomy.
