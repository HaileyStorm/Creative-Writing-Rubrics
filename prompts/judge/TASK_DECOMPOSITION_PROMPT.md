# Dynamic task-question decomposition prompt

You are compiling an ephemeral HBQ-RS task module from a creative-generation request.

Inputs:
- user brief;
- supplied source material and project constraints;
- selected artifact/form/scope profiles;
- list of already active criterion keys.

Procedure:
1. Summarize explicit required operations, inclusions, exclusions, transformations, preservation rules, length/format constraints, and conditional requirements.
2. Decompose them into the smallest independently answerable positive binary questions that remain useful.
3. Phrase every leaf so YES means pass.
4. Mark exact requirements as hard_gate; mark preferences as scored; mark context-only checks as diagnostic.
5. Add an explicit applies_when condition for conditional requirements.
6. Do not invent generic craft standards; those come from the registry.
7. Remove overlap with supplied active criterion keys.
8. Reject any question that cannot be answered from the planned evidence packet.
9. Return a valid HBQ-RS module JSON object and a validation report listing source trace, duplicates removed, ambiguities, and unresolved conflicts.

Do not inspect candidate outputs while creating criteria. The criteria must derive from the brief and sources, not from whichever candidate the judge happens to prefer.
