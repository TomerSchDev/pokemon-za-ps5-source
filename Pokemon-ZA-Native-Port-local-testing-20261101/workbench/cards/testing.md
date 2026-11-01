# Card: local structured game tests

Read canonical AGENTS.md and resource-queues.md first. Details: docs/testing/AGENT_TESTING_RULES.md.
Use `zw test prepare|submit|work|status|results|cancel|list|recover|selftest`.
Use `zw test capacity` for the existing disk/commit preflight; never lower its thresholds.
Initialize shared config once with `zw test init`; all checkouts use the same outside-Git state.
Worker takes its own canonical PC turn and retains the existing Windows game mutex.
One game at a time. No console or cloud. Do not supply a private production PC queue.
Full uses unchanged `zw pc run`; Render is a shorter normal-runtime capture workflow.
Logic L1/L2/L3 are UNSUPPORTED until typed state/tick adapters are verified; submit explicit Full fallback.
Every job needs a timeout and assertions. Missing evidence, crashes and unsupported modes never pass.
Capture-only has visual.status=NOT_EVALUATED. A capture is not visual approval.
Inspect results, logs, images and metric limitations. Never auto-replace a failed baseline.
Cancellation needs a terminal result plus zero-process cleanup. Interrupted worker: `zw test recover`.
No stale lease/mutex takeover, no other agents' process termination, no real-save writes.
Keep assets/saves/tokens/generated captures out of source archives and Git.
Verification/measurements: docs/testing/PERFORMANCE_BASELINE.md (only executed rows are evidence).
Verified: real short/120s Full, single/multi Render, timeout, running cancel and native exit-7 FAIL.
Capture texture was 1920x1080 for a 1280x720 window; do not equate window size with capture size.
