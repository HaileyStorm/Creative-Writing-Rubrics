# Recommended HANNA development profile

This package publishes the exact `broader-nextwave-13-missing_evidence_not_no` instruction and profile bytes used in the broader development and held-out confirmation studies. It is a practical development candidate for future endpoint-separated HANNA experiments, not a runtime default.

The pinned evidence is directionally consistent: Grok development selected the descendant, Grok confirmation reduced group-weighted MAE from 1.2569 to 0.9375, and Sol confirmation reduced it from 1.4267 to 1.2439. These are separate endpoint results; they are not pooled and do not establish general literary generalization.

`verify.py` reconstructs the descendant using the pinned broader-freeze constructor, checks the literal public bytes, and binds each result pin. DSPy and Optuna are not imported or used at runtime.

Authority is strictly `development_recommendation_only`: no runtime, selection, promotion, or generalization authority is granted.
