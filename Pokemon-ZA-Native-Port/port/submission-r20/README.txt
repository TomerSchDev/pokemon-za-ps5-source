Pokémon Legends: Z-A Randomizer — submission candidate r20
2026-10-28

This is a submission A/B candidate. It does not change the game's 30/60 FPS
mode, time step, dynamic resolution, shaders, randomization, saves or driver.
No hardware performance gain or graphics correctness is established by this
build alone. The parent task owns installation and measurement.

Mechanism
---------
The r19a renderer submitted every NVN command list separately. r20 preserves
the recording/finalization of every list: its upload buffer followed by its
main buffer, XFB copyback, transient allocations, descriptor pools, ring-slot
rotation and logical sequence. Up to eight completed lists are given to one
vkQueueSubmit2 as ONE VkSubmitInfo2, retaining that buffer order. The timeline
semaphore is signaled once, at the last logical sequence. This delays earlier
retirements conservatively; no resource is retired before its old sequence.

This is intentionally narrower than newer upstream's shared recording-buffer
batching. In our older renderer, uploads are discovered inside a draw after a
render pass begins. Merging recording buffers would reorder a later list's
uploads ahead of an earlier list's draws. r20 retains distinct ordered buffers
instead, without rewriting rendering or upload code.

Boundaries
----------
Batching stays within one nvnQueueSubmitCommands API call and existing recursive
execution lock. A fence found in any nested recorded list ends its containing
top-level list's batch. A host GPU wait flushes queued work before waiting.
CPU readbacks retain their existing flush/wait. Binary semaphore presentation
submits are separate, preserving acquire/signal placement. Empty nonfinal fence
lists and empty final lists flush already queued work too.

Limits checked at completed-list boundaries: eight lists, 400 draws, 32,768
recorded commands, or two milliseconds since the first list began. An individual
large/slow list may exceed these limits, just as in r19a; the two-millisecond
value is NOT an interrupt or a strict within-list latency bound. An internal
flush re-arms the oldest pending-batch timestamp when work resumes.

Profile (same eboot.bin)
-----------------------
/app0/submission-options.txt contains exactly one word, with optional whitespace:
  batch  — enable bounded batching (the packaged candidate includes this)
  each   — submit each logical list, as the baseline
Read once on startup. Missing, oversized or invalid configuration uses each.
ZA_SUBMISSION_PROFILE overrides the file for development. The existing
LARECOMP_VK_SUBMIT_EACH and LARECOMP_SYNC_SUBMIT overrides still disable batching.
Close and reopen the title after changing a profile. No installer is provided
here; use the parent-owned hardware helper.

Measurement
-----------
New cumulative [za-r20-submit] lines report:
  logical: completed per-list submissions (existing stats keep this meaning)
  vk_calls: actual vkQueueSubmit2 calls
  merged: logical submissions saved by combining buffers
  cbs: command buffers submitted
  nvn_calls / nvn_lists / max_nvn
  nvn_hist: calls with 0, 1, 2–4, 5–8, or 9+ handles
  batch_hist: actual submissions containing 1 through 8 logical lists
  each/end/fence/draws/lists/commands/age/wait/internal/present/capacity reasons
Use differences over a steady-state interval, not cumulative startup totals.
If nvn_hist is mostly one handle, batching cannot remove those call boundaries.

RADV's radv_queue_submit_normal chains command buffers within one Vulkan submit
before winsys cs_submit; its PS5 winsys may still split large streams. Compare
the existing driver [radv/ps5] submission count to vk_calls before claiming a
matching reduction in hardware DCB submissions. sceAgcSuspendPoint and its kick
thread were not modified. Existing CPU and GPU timing categories overlap and
must not be added together.

Validation
----------
test.sh compiles the EXACT queue.inc and executor.inc used by exec.c against a
mock Vulkan driver, with -Wall -Wextra -Werror and ASan/UBSan. It checks actual
captured CB order and signal descriptors, ring-slot reuse, baseline vs batch,
fence boundaries, empty fences/end, internal readback, age rearming, draw/list/
command limits, binary presentation boundaries, standalone timeline signals,
wait flushing, strict profile parsing and handle-count distribution.

The mock supplies command-list effects, including a fence flag. It does not
execute the full CMD_CALL parser, rasterize, validate GPU barriers, or reproduce
every guest CPU write/read dependency. Preservation audit verifies the existing
recording, upload, transient, fence, copyback and timing helper bodies unchanged,
and all extra objects other than title_entry unchanged. Registration sizes,
dynamic imports, full PS5 linkage and packaged image preservation are checked.
The nvn.h declaration triggers recompilation of all 64 runtime objects in the
new directory. Their debug metadata differs; after --strip-debug, 61/64 objects
are byte-identical to r19a. VMA's instructions and relocations also match, and
its allocated data differs only in its assertion source-file directory string.
Only nvn/objects.o and nvn/vulkan/exec.o have intended code changes.
Existing SDK/VMA warnings mean the entire legacy runtime is not claimed Werror
clean; the new shared-code host test and title entry are Werror clean.

Hardware follow-up
------------------
Compare each/batch/each on the same save, position, camera and warm cache. Check
images, movement/animation speed, captures, audio and shader activity as well as
FPS. Record actual queue/driver calls and CPU submit time. The one final timeline
signal preserves safety by waiting longer for earlier logical sequences, but
the possible effect on guest host-visible waits and throughput needs hardware
measurement. Revert to each in the same binary if graphics or timing regress.

Reproduction
------------
Run prepare.py once in WSL to create the isolated batch-r20-20261028 tree from
the pinned compiler-r19-20261028 baseline; then test.sh, build.sh and audit.py.
Build links TITLE_OBJS plus the immutable cheats-r12/liblasgame-r12.a INPUT.
Never invoke the original offline-title target with that archive as a make
prerequisite. Source/preparation/test/build/audit evidence is stored under
evidence/submission-r20; packaged title under artifacts/randomizer-r20-batch.
