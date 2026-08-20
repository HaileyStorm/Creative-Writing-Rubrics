# Examples

- `verdicts_example.jsonl` — illustrative `prose.scene` verdicts. Not a literary judgment.
- `sample_scene.md` — tiny artifact for `cwr render-judge`.
- `compiled_scene_bundle.yaml` / `compiled_strict_haiku_bundle.yaml` — bundle definitions used as worked examples.
- `dynamic_task_module_example.yaml` — sample ephemeral task module generated from a brief.

```bash
cwr score prose.scene examples/verdicts_example.jsonl
cwr render-judge --bundle prose.scene --artifact examples/sample_scene.md
```
