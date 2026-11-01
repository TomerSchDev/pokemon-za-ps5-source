# r24 observer: r23c's observer with slot depths 8/16/32/64

Copy of `port/slot-depth-r23c-observer`. The protocol (protocol 17: continue / input / snapshot / measure / fps /
submission / preparation / immutable_spans / slot_depth / retire_capture / close) and every file not listed below
are byte-identical to r23c (checked by `test.sh`).

Changed for r24:
- `slot-depth-control.h` — capacity 64; applied values 8/16/32/64 (shared with the runtime's copy).
- `slot-depth-observer.inc` — `slot_depth` accepts 32 and 64; receipts for any depth above 8 carry the same
  budget/headroom validation that 16 had.
- `slot-startup.inc` — `/app0/slot-depth-options.txt` accepts `32`/`64` (with optional LF); a depth above 8 is
  applied once at startup through the same checked runtime call. The log tag stays `[za-r23c-startup]`.
- `observer-r24.c` — `observer-r23c.c` renamed; content unchanged.
- `client.py`, `slot-depth-client.inc` — depths (8, 16, 32, 64), capacity 64, budget checks for every depth above 8.
- Tests (`test-*.c/.inc`, `test-client.py`, `test.sh`) — the same suites against the r24 copy, plus 32/64 startup
  and live-command cases. Evidence: `evidence/perf-r24/observer-tests/`.
