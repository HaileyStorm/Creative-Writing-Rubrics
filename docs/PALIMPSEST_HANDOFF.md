# Palimpsest integration handoff

## Completed integration record

The CWR submodule integration is recorded at Palimpsest commit
`76db589ae0c6f0369d409023f6caa9f67498d78a`. Its exact mount is
`Palimpsest/Rubric Book`, pinned to CWR commit
`5e4723fb85e0378d9b55f3d4eec6c8dac968571a`.

The prior integration gates were green at that checkpoint. The tested
compatibility boundary preserved the HBQ-RS identity, stable IDs, control
states, deterministic aggregation, and the CWR source/generated distinction.
This record does not claim that every historical saved project, every future
rubric revision, or every untested desktop/build path is automatically
compatible; those remain explicit Palimpsest responsibilities.

## Authority and boundary

Palimpsest's project specification remains authoritative for product behavior,
persistence, local-first disclosure, the built-in package mount, projects,
canon, manuscript/publication state, desktop RPC, and promotion decisions.
Creative-Writing-Rubrics (CWR) remains authoritative for its published HBQ-RS
1.2.1 source, schemas, tooling, and documentation. As described in [Using
HBQ-RS inside another application](apps.md), CWR supplies rubric data and
deterministic scoring; Palimpsest owns application state and decisions.

The submodule must remain an exact gitlink to the selected CWR commit. Never
track a branch, tag, `main`, or another floating update in the integration.

## Pinned source and compatibility boundary

The pre-upstream CWR registry had 277 modules, 2,139 leaves, and 85 bundles.
The pinned CWR registry has 278 modules, 2,145 leaves, and 85 bundles,
including `modifier.style.authored_content_treatment_fidelity`. Treat the
change as a schema/API migration boundary, not as a file copy. Do not remove,
rename, or reinterpret Palimpsest stable IDs or historical verdicts merely to
match CWR.

Expose the integration through `palimpsest.hbq`, not CWR internals. The adapter
loads the pinned book, compiles and scores through a stable Palimpsest-facing
API, and translates only through an explicit, tested compatibility map. It
preserves control states, deterministic aggregation, stable IDs, and
source-traceable dynamic questions.

## Source, build, and provenance rules

Treat CWR authored inputs as source and its packed registries, manifests, and
rendered documentation as generated outputs. Change generated aggregates only
through their source and generator; retain source-vs-generated status and
reconstruction provenance. The [HBQ-RS standard](HBQ_RS_STANDARD.md) and
[Rubric Book](RUBRIC_BOOK.md) remain the catalog and scoring references rather
than being duplicated here.

The embedded book ships and runs locally with Palimpsest. It cannot create an
undeclared network dependency, and any later remote judging destination still
requires Palimpsest's local-first disclosure.

Every evaluation/run and saved-project manifest should retain immutable rubric
identity: the submodule commit, registry/manifest hash, compiled bundle hash,
selected stable IDs and versions, adapter version, and compatibility-map
version. The completed checkpoint confirms those identity obligations only for
the paths exercised by its tests. Exact replay must resolve the recorded
revision or expose the specifically unavailable operation and prerequisite;
it must never silently substitute a newer book or rewrite prior verdict
provenance.

## Subsequent update acceptance

For every deliberately selected future CWR revision, make one reviewable
Palimpsest commit that changes the gitlink and its compatibility evidence
together. Inspect the selected revision and gitlink from the Palimpsest root:

```powershell
git submodule update --init --recursive
git diff --submodule=log -- .gitmodules "Rubric Book"
```

Use [Local acceptance](LOCAL_VALIDATION.md) for the CWR behavior changed by the
selected revision. CWR has no routine unit or integration suite; an update does
not require a blanket pytest run, inventory/parity matrix or new test count.
When registry or packaging inputs change, follow the corresponding production
validation or build described there.

For a changed Palimpsest adapter or saved-project path, exercise the affected
application journey under Palimpsest's current policy. Verify the recorded
revision and compatibility behavior for that path, including an existing saved
project when replay or upgrade behavior changes. Preserve immutable identities,
native execution and privacy controls. Historical checkpoint tests remain
evidence for their recorded revision and scope.

## Rollback and bounded obligations

Rollback is a normal Git revert of the Palimpsest integration commit, including
`.gitmodules` and the gitlink, followed by:

```powershell
git submodule update --init --recursive --checkout
```

Exercise the affected rollback/replay journey after rollback. Preserve recorded
project manifests, prior adapter compatibility code, and the pinned CWR commits they
name so existing evidence remains inspectable; do not mutate run history during
rollback.

Palimpsest remains responsible for deciding and testing saved-project manifest
versioning, upgrade/replay behavior, release/build inclusion, and rollback
acceptance for any future change. The completed integration record establishes
the tested current boundary; it is not a blanket claim for arbitrary historical
or future saved-project compatibility.
