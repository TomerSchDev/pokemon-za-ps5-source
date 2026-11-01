# Card: build dependency audit and migration

Read canonical AGENTS.md, main.md and resource-queues.md first.
Audit: docs/testing/BUILD_DEPENDENCY_AUDIT.md; machine-readable map: BUILD_DEPENDENCY_MAP.json.
Only external-model import and story randomization are active by Tomer's lifecycle instruction.
Other projects are expected console-ready; package presence is separate from rebuild closure/live verification.
Tomer's priority: ad-hoc old-worktree/evidence/bytecode dependencies are migration blockers, not permanent clutter.
Use approved current semantic inputs; copying old files into a newly named folder is not sufficient.
Review migrations before progress/promotion; do not kill another agent's process or mutate enrolled jobs.
Fact: story review/probe reads canonical r3 summary; model prepared r4 manifest still declares r1/r2/r4 helpers.
Fact: installed-local JSON fix reconstruction references a 1,487-byte uncommitted wrapper in an old worktree.
Preserve the exact known fix/rollback temporarily until current source/recipe and replacement are verified.
main-1.1.0 has 125 own frozen inputs plus shared tools; frozen_from is provenance, not a live link edge.
The map is bounded metadata/source evidence, not full content verification or a deletion list.
No artifact store, migration guard, transfer, cleanup, build or console action was implemented by this audit.
No new production commands exist for this plan. Keep assets/saves/keys and game-derived content restricted.

Binding policy now: `build-inputs.md` and canonical `docs/testing/CURRENT_BUILD_INPUT_RULES.md`; the earlier audit's no-guard statement remains historical. Every build needs a current-input check; historical research needs a current-location/supersession record.

Fact: current za check-proof requires PIE+BIN; stripped/converted ELF intermediates can be cleaned after final validation. Mandatory lifecycle policy: docs/testing/BUILD_CLEANUP_RULES.md.
