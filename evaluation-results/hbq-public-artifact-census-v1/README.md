# Public evaluation-artifact census

This is a reproducible index of files tracked under `evaluation-results/` at
Git commit `989d75434c82d157e33913823c63a486467dd236`. Each line of
[`manifest.jsonl`](manifest.jsonl) records a path, its enclosing result
directory, Git blob identity and byte size. [`summary.json`](summary.json)
counts paths and distinct blobs separately. Identical blobs at different paths
are preserved as separate path records, not assumed to be separate judgments.

From a clone containing that commit, run:

```sh
python evaluation-results/hbq-public-artifact-census-v1/census.py --repo . --verify
```

The generator reads Git's NUL-separated tree metadata, not file contents or a
working directory. For a new export, pass `--repo <clone> --output-dir <fresh
existing directory>` instead of `--verify`; files are created exclusively.
The manifest cannot include itself because it indexes the earlier commit.
It does not change with later commits unless a separately versioned census is
made. The pinned snapshot has 2,332 paths in 455 result directories and 2,294
distinct Git blob IDs.

This is one part of the research census, not the complete artifact/request/leaf
census. It excludes untracked and ignored files, private evidence, files deleted
before the pinned commit, external sources, and later files. File names, paths,
sizes and matching Git blobs do not establish actual attempts, provider contact,
admission, scorer compatibility, independent observations, or human labels.
An artifact's inclusion does not establish its quality or rights. Historical
snapshots may overlap and must not be summed as independent observations.
