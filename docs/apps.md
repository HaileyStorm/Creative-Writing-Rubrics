# Using HBQ-RS inside another application

The registry is data. The scorer is a pure function. Your app supplies artifacts, a model (or a human), and stored verdicts.

## Minimum loop

1. Ship or fetch this repository (or `pip install` it).
2. Choose one bundle ID. Load only that bundle plus the modules it names. `cwr compile BUNDLE_ID` is the judge packet.
3. Show the judge prefix and one leaf at a time. Persist a verdict object matching `schema/hbq_verdict.schema.json`.
4. Call `score_bundle`. Treat `INELIGIBLE` / `PROVISIONAL` / `UNRESOLVED` as control states, not as a 0–100 quality number.
5. Optionally run an open-review family from `prompts/review/` and store findings against `schema/open_review.schema.json`. Open review may *read* a score report. It must not rewrite scores.

## Caching

The shared prefix (`JUDGE_PREFIX.md` + compiled packet) is large and stable. Cache it per bundle. Only the current leaf, artifact excerpt, and evidence packet should vary.

## Custom modules

Add a YAML file under `registry/modules/`, then `cwr pack` to rebuild aggregates. Validate with `cwr validate`. A criterion has one scoring owner: do not add a second leaf for the same proposition.

User overlays may change activation, interpretation, evidence scope, or weight. They must not create a second score for the same `criterion_key`.

## Two-role drafting funnel (optional)

IDs such as `default.model_b_scene_draft` and `default.model_a_finalist_adjudication` keep historical names. In this package they mean:

- **Fast generator/screener** — many candidates, cheap first-pass bundle.
- **High-context critic/editor** — few finalists, full stack, then pairwise comparison with order swap.

You can point both roles at the same model.

## What not to embed

Do not depend on any host application's project graph, canon promotion rules, or desktop RPC. This package does not establish manuscript or publication state.
