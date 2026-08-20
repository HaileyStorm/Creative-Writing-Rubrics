# Oregon Revised Narrative Writing Scoring Guide 2017: research implementation

This is an original research implementation derived from the published **Oregon Department of Education Revised Narrative Writing Scoring Guide (2017)**. It is not Oregon assessment, does not reproduce the guide, and must not be presented as official scoring or trained-marker assessment.

Treat the submitted piece as a complete fictional narrative. Give each native trait one whole-number score from 1 to 6, independently but with the whole text in view:

- `ideas_and_content`: focused, developed narrative material and sensory or concrete detail.
- `organization`: purposeful sequencing, transitions, pacing, and a controlled whole shape.
- `voice`: a credible, engaged presence and relationship with the reader.
- `word_choice`: precise, effective words that build meaning, character, setting, or tone.
- `sentence_fluency`: varied, controlled sentences that carry the narrative naturally.
- `conventions`: editing control sufficient to support clarity and effect.

For every trait, provide one short contiguous quotation and a terse observation. Calculate `total_score` as the exact sum of the six trait scores. Return only the schema-defined JSON object. Do not reveal chain-of-thought.
