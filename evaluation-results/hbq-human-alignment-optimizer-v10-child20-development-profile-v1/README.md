# Child20 opt-in development profile

This package exposes the confirmed child20 instruction and profile as a literal
development input. It is never activated automatically.

From the repository root, inspect and verify it without provider activity:

```powershell
python evaluation-results/hbq-human-alignment-optimizer-v10-child20-development-profile-v1/verify.py
```

Copy the exact `instruction` and `profile` values from `profile.json` only when
an explicitly opted-in development experiment needs them. This grants
`development_recommendation_only` authority: no runtime, selection,
promotion, generalization, endpoint pooling, or Linux claim. The child13
predecessor remains retained as lineage; this package does not replace it.
