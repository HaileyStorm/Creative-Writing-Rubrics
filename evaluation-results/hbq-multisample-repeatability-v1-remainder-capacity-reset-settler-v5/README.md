# V4 offline settler

V5 is offline-only. It freezes the failed v4 root against a predeclared manifest hash, validates its one accepted 179-leaf HBQ run and six accepted batches, then writes one recovered completion in a fresh recovery root. It never calls a provider or retries sequence 178. The earlier V5 settlement output is non-promotable lineage; only a newly created repaired-V5 root may be considered.
