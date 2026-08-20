# Gray Blood chapters 1-6: draft comparison

This is a real long-form HBQ-RS evaluation of two versions of the same work-in-progress novel. The manuscript is private and is not included here. The published package keeps all 778 accepted binary verdicts, 14 deterministic score reports, two long-form maps, the comparative synthesis, sanitized provider attestations, and checkpoint/hash commitments. Evidence quotations, local paths, run IDs, session IDs, and prompt bodies were removed.

## What was run

- The complete `prose.novel` bundle: 221 leaves per six-chapter draft, judged with GPT-5.6 Luna at Max.
- The same frozen 28-leaf `prose.chapter` subset on each corresponding chapter, judged with GPT-5.6 Sol at Medium.
- Whole-work maps and the final open comparison, judged with GPT-5.6 Sol at High.
- Rubric and runner revision: `448c461c74d7a612db12ef7ac9b9236b54123980`.

The evaluation followed `LONG_FORM_PROTOCOL.md`: maps and state ledgers came first, chapter-local questions stayed local, and chapter scores were never averaged into a manuscript score. Open review did not change the deterministic results.

## Result in brief

The rewrite was a mixed revision, not a clear replacement. It improved diction, syntax, dialogue mechanics, and Chapter 3's local pacing. The original remained the stronger structural base across these chapters, especially in continuity, exposition control, motive dramatization, tonal fit, and Chapter 6's ending. Both versions still needed a darker behavioral register for Amelia, firmer consequences for violence and coercion, less repetitive reassurance, and clearer high-stakes limits on blood magic.

| Six-chapter artifact | HBQ-RS state | Observed interval | Coverage |
| --- | --- | ---: | ---: |
| Original | `INELIGIBLE` | 78.08 `[75.00, 78.30]` | 96.70% |
| Rewrite | `UNRESOLVED` | 74.19 `[70.11, 74.85]` | 95.26% |

Those numbers are not ordinary grades. The original failed a required-inclusions hard gate; the rewrite left operation and inclusion gates unassessable. The intervals and domain breakdowns are still useful diagnostic evidence, but the control states take precedence.

One useful runner failure occurred during the rewrite's fifth batch: the model returned 31 of 32 requested leaves. The runner rejected the batch, retained the first 128 verdicts, and resumed from the exact checkpoint. The incomplete response is not included in these results.

## Files

- [`manifest.json`](manifest.json) records scope, routes, counts, privacy treatment, and top-level results.
- [`comparative-synthesis.json`](comparative-synthesis.json) contains the full open comparison and ranked revision priorities.
- [`whole/`](whole/) contains both complete 221-verdict runs and score breakdowns.
- [`chapters/`](chapters/) contains the twelve fixed-subset chapter runs. Their low bundle coverage is intentional; compare paired verdicts, not their observed totals.
- [`maps/`](maps/) contains quote-free unit maps, state ledgers, promises, motifs, and continuity conflicts for each draft.
- The `*-provenance.json` files retain requested/reported model settings, batch question IDs, exact published-verdict file hashes, and prompt/response/checkpoint commitments. Private pre-sanitization batch-verdict commitments are labeled separately; no private paths or session identifiers are retained.

The source text was not needed to publish the result. Every evidence object retains its chapter or criterion reference, but its verbatim quotation was removed.
