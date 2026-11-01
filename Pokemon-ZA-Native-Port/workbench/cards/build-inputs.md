# Card: mandatory build input and research source checks

Applies NOW to every Z-A project, worktree and delegated agent, including completed projects.
Stop forward build work at a safe checkpoint; no next build stage until inputs are checked.
Read canonical AGENTS.md in full and docs/testing/CURRENT_BUILD_INPUT_RULES.md.
Before EVERY native/tool compile, relink, reproduce, mod/data generation or package:
1. Read docs/testing/BUILD_DEPENDENCY_MAP.json and BUILD_DEPENDENCY_AUDIT.md.
2. Refresh current MAIN/locks/baseline/component locations; the map is a dated snapshot.
3. Resolve all direct/transitive source/tool/SDK/object/data inputs and their actual hashes.
4. Record current approved counterparts and why these inputs are current/compatible.
5. Missing/unmapped/stale/ad-hoc old inputs BLOCK the build; resolve and update mapping first.
6. Write a local per-job input check, then follow existing resource readiness/test/install rules.
Do not mutate frozen locks, repin queued jobs or lose installed fixes; mtime is not approval.
Migration/control builds use reviewed current candidate inputs plus baseline controls.
Research may use old material with exact path/version/hash/read time/map node and current location.
Track superseded_by and refresh affected conclusions; unknown current locations remain gaps.
Templates: docs/testing/build-input-check.example.json and research-source-record.example.json.
Propagate this rule to subagents. Never terminate another agent or waive queue/console safety.
This is a binding agent workflow rule; no automatic universal build blocker is claimed.

End-of-build cleanup is mandatory: plan retention and follow docs/testing/BUILD_CLEANUP_RULES.md; successful final validation precedes removal of reviewed generated intermediates. Record deleted/kept/errors; retain proof-required PIE/BIN, inputs and rollback.
