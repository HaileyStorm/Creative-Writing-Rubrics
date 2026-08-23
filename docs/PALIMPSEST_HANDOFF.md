# Palimpsest integration handoff

This is a future-integration handoff, not an instruction to migrate either repository now.

## Authority and boundary

Palimpsest's project specification remains authoritative for product behavior, persistence, local-first disclosure, and the built-in `Rubric Book/` package. Creative-Writing-Rubrics (CWR) remains authoritative for its own published HBQ-RS source, schemas, tooling, and documentation. Keep the application boundary described in [Using HBQ-RS inside another application](apps.md): CWR supplies rubric data and deterministic scoring; Palimpsest owns projects, canon, manuscript/publication state, desktop RPC, and promotion decisions.

The proposed mount is a Git submodule at `Palimpsest/Rubric Book`. It must be an exact gitlink to an owner-approved CWR commit. Never track a branch, tag, `main`, or any other floating update. The CWR SHA observed while this handoff was written was `57c62fabcfc18f92bb92beb7697003f7a6ebdce7`; it is a discovery snapshot only, not a future pin.

## Why it is not drop-in

The observed CWR registry has 277 modules, 2,139 leaves, and 85 bundles. Palimpsest currently requires 278 modules, 2,145 leaves, and 85 bundles, including `modifier.style.authored_content_treatment_fidelity`. Treat that as a schema/API migration, not a copy or replacement. Do not remove, rename, or reinterpret Palimpsest stable IDs or historical verdicts merely to match CWR.

Expose the integration through `palimpsest.hbq`, not CWR internals. The adapter should load the pinned book, compile and score through a stable Palimpsest-facing API, and translate only through an explicit, tested compatibility map. It must preserve control states, deterministic aggregation, stable IDs, and source-traceable dynamic questions. An owner-approved migration contract decides how a CWR revision relates to Palimpsest's additional criterion; the adapter implements and enforces that decision.

## Source, build, and provenance rules

Treat CWR authored inputs as source and its packed registries, manifests, and rendered documentation as generated outputs. Change generated aggregates only through their source and generator; retain source-vs-generated status and reconstruction provenance. The existing [HBQ-RS standard](HBQ_RS_STANDARD.md) and [Rubric Book](RUBRIC_BOOK.md) remain the catalog and scoring references rather than being duplicated here.

The embedded book must ship and run locally with Palimpsest. It cannot create an undeclared network dependency, and any later remote judging destination still requires Palimpsest's local-first disclosure.

Each evaluation/run and saved-project manifest needs immutable rubric identity: the submodule commit, registry/manifest hash, compiled bundle hash, selected stable IDs and versions, adapter version, and compatibility-map version. Existing projects must remain openable. Exact rubric replay must resolve the recorded revision or expose the specifically unavailable rubric operation and prerequisite with a recoverable migration path; it must never silently substitute a newer book or rewrite prior verdict provenance.

## Proposed update gate

For every deliberately selected CWR revision, make one reviewable commit that changes the gitlink and its compatibility evidence together. From the Palimpsest root, the minimum gate is:

```powershell
git submodule update --init --recursive
python -m hbqrs validate
python -m pytest "Rubric Book/tests"
uv run --locked --extra test --extra prompt-optimizer python scripts/validate_bootstrap.py
uv run --locked --extra test --extra prompt-optimizer python -m pytest python/tests/test_m5_hbq_review.py python/tests/test_m5_custom_rubric_service.py python/tests/test_m5_application_service.py
git diff --submodule=log -- .gitmodules "Rubric Book"
```

Run the CWR commands from a development environment in which the pinned `Rubric Book` submodule is installed, for example with `python -m pip install -e "Rubric Book[dev]"` during environment setup. Revalidate the exact commands when the adapter and build workflow are implemented.

Add focused `palimpsest.hbq` adapter and saved-project compatibility tests for the selected revision. Confirm the expected module/leaf/bundle counts, stable-ID ownership, JSON/YAML/JSONL parity, manifest reconstruction state, and an old-project open/replay path. Run the narrowest relevant checks before the full Palimpsest bootstrap validator. A green source-package test is not proof that saved projects or the desktop integration remain compatible.

## Rollback and entry criteria

Rollback is a normal Git revert of the integration commit (including `.gitmodules` and the gitlink), followed by `git submodule update --init --recursive --checkout` and the same validation gates. Preserve recorded project manifests, prior adapter compatibility code, and the pinned CWR commits they name so existing projects remain inspectable; do not mutate their run history during rollback.

Begin an implementation migration only after an owner has approved all of the following:

1. The exact CWR commit and licensing/distribution treatment.
2. A deterministic inventory diff and explicit disposition for `modifier.style.authored_content_treatment_fidelity` and every other ID/count mismatch.
3. The `palimpsest.hbq` adapter contract, generated-output workflow, and fixture-backed compatibility map.
4. The saved-project manifest versioning, upgrade/replay behavior, release/build inclusion, and rollback acceptance tests.

Deferred decisions include the exact pin, whether the added Palimpsest criterion is upstreamed, adapted, or retained locally, the long-term ownership of any compatibility map, and the project-manifest upgrade policy. Resolve them in the migration issue before adding the submodule.
