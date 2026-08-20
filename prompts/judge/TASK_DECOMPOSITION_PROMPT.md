# Dynamic task-question decomposition prompt

You are compiling a frozen HBQ-RS task contract from a creative-generation request.

Inputs:
- user brief;
- supplied source material and project constraints;
- selected artifact/form/scope profiles;
- list of already active criterion keys.

Procedure:
1. Separate background/context, preferences, revision priorities, weighted goals, and genuinely binding requirements.
2. Decompose weighted goals and binding requirements into the smallest independently answerable positive binary questions.
3. Phrase every question so YES means pass; reject conjunctions and catch-all questions such as “does it satisfy every inclusion?”
4. Put subjective author goals, taste, tone, voice, and desired effect in `weighted_goals`. They affect score, never eligibility.
5. Put an item in `binding_requirements` only when the source makes it explicit, objective, non-negotiable, and verifiable. Set `objective` and `non_negotiable` to true and provide the verification method.
6. Give every item an exact source excerpt, source reference, and applicable work/unit scope.
7. Do not invent generic craft standards; those come from the registry.
8. Remove overlap with supplied active criterion keys and reject any question that the planned evidence packet cannot answer.
9. Return one JSON object conforming exactly to `schema/hbq_task_contract.schema.json`, with no prose outside the object.

Do not inspect candidate outputs while creating criteria. The criteria must derive from the brief and sources, not from whichever candidate the judge happens to prefer.
