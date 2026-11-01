# r21 preparation observer extension

This private extension starts from the actual `port/submission-r20b` observer and client. It keeps protocol 17 and the existing submission, FPS, snapshot, bounded input, continue, and measurement paths. `observer.h` and `analyze.py` are copied from the established observer-r17 support files. The screenshot callback is unchanged, so this extension does not change the runtime's 4K capture path or its local compiler integration.

Copy `observer-r21.c` and `preparation-observer-api.h` into the runtime observer source directory, or add this directory to its include paths. The runtime integration owns the three APIs in the header, including the execution lock and GPU drain. This directory does not modify runtime execution, build or deployment policy.

## Profiles and switch contract

| Profile | Flags | Success return |
| --- | ---: | ---: |
| `baseline` | 0 | 1 |
| `plan-only` | 1 | 2 |
| `lazy-only` | 2 | 3 |
| `optimized` | 3 | 4 |

Startup is `baseline`. A profile command runs only after a successful, non-represented present with a positive frame number. The runtime serializes it using the established execution lock, drains prior work and applies the requested flags. Invalid profile returns `-1`; unsafe boundary/drain failure returns `-3`, leaving prior state unchanged.

The observer performs no preparation API calls without an explicit command. It does not poll the command mailbox during settling or measurement, including through the menu hook. A pending request remains unconsumed until a later safe post-measurement frame. A command consumed in a menu or on a failed/represented present is rejected and requires a new sequence number to retry.

## Commands and receipts

```text
client.py preparation --session SID --seq N optimized
client.py collect --session SID --seq N --out OUTPUT_DIR --preparation optimized
```

Python callers use `collect(ftp, session, seq, out, expected_preparation='optimized')`. The expected profile is required when collecting a preparation command and must equal the original intended request. Other commands keep their existing collection interface.

The preparation receipt contains `requested_profile`, actual `profile` and `flags`, `runtime_result`, `frame`, `cost_ns`, and `result`. `applied` requires all of the return value, actual profile, actual flags and original request to agree. A rejected receipt still reports the actual current profile. An incoherent runtime getter produces `receipt_mismatch` with an empty profile and `flags=-1`; it is never reported as applied. Preparation receipts cannot name downloadable output files.

Recognized results are `applied`, `rejected_boundary`, `rejected_in_menu`, `rejected_profile`, `drain_failed`, and `receipt_mismatch`. `cost_ns` measures only the switch API call. The client validates the session/sequence, expected operation/profile, exact integer types and bounds, result context, flags and return code before writing a receipt record.

## Tests

Run `bash test.sh` in Ubuntu with `clang-21` and Python 3. It builds and executes the actual observer source with ASan/UBSan and the runtime switch API stubbed. This exercises parsing, all profiles, actual receipt JSON, cost/frame, menu and boundary rejection, replay protection, deferred command execution throughout settling/measurement, drain failures, inconsistent runtime responses, and existing observer behavior. Offline client tests call the actual `collect` path and reject mismatched or malformed receipts before writing evidence.

The tests also parse every generated observer receipt independently and verify all profile/result categories. Test files and logs are stored in a fresh directory under `evidence/preparation-r21-observer`. These tests do not validate the runtime GPU drain itself, hardware rendering, or performance; those belong to the runtime integration and controlled hardware experiment.
