# CWR and Palimpsest project boundary

CWR owns its repository, rubric registry, package releases, research results,
source provenance, and collection/judging receipts. Its existing remote remains
`https://github.com/HaileyStorm/Creative-Writing-Rubrics.git`. Local app projects
must point to the existing CWR checkout rather than to the Palimpsest checkout.
Changing an app association does not move files, transfer claims, or reset a Goal.

Preserve existing checkout and external research/control paths during the owner
rollover. Frozen invocations and receipts retain the original absolute paths and
executor identity. Future jobs use their actual successor identity and fresh
claims. Never rewrite old provenance to resemble the new owner or remove a STOP
marker to resume an old invocation.

## Palimpsest integration decision

Defer adding a submodule. The current separation needs no nested clone, checkout
move, or new download. Palimpsest can continue consuming the existing package
through its current interface while CWR collection and prospective evaluation
finish. This avoids binding a consumer update to unfinished research or carrying
private results into the consumer repository.

When a Palimpsest milestone requires a vendored CWR source revision, make that a
separate integration change: select a supported released revision, add the
existing remote at one documented relative consumer path, pin its exact commit,
and verify package/registry compatibility through the actual consumer call path.
Keep CWR's research workspace, ignored inputs, native jobs, and tracker history
outside that submodule. Do not substitute the live dirty research checkout for a
versioned consumer dependency.

## Tracker and memory continuity

The existing alignment issue and native history remain in their current
canonical tracker during rollover; this document does not initialize or migrate
a tracker. The successor records the canonical location in its private handoff.
Use the existing CWR Shared Memory work-project identity with a reviewed local
checkout/app alias; an app project ID is not a new shared work-project identity.
Verify authenticated recall and actual use from the successor. Keep predecessor
and successor retained until workspace, Goal, tools, ownership, and required
runtime evidence are acknowledged.
