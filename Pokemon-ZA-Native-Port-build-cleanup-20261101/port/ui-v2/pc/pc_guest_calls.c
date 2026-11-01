// pc_guest_calls.c - port/cheats-r28/za_items.c calls five recompiled game functions by name (f_<guest address>).
// Inside lasgame.dll (the r28 proof: za_items.o linked into the DLL) they resolve to the DLL's own hidden units. In the
// exe (this build: the DLL imports za_items_pump & co. from the exe) they can't be linked - the DLL is loaded at run
// time - so each is a forwarder through the runtime's guest address -> host function table (dispatch_lookup,
// runtime/dispatch.c; filled by dispatch_init after gamelib_load), resolved on first use. Same call, same Cpu, same
// thread as the direct call: only the lookup is added.
#include "cpu.h"
#include "rt.h"

#define GUEST_FWD(addr)                                                                               \
    void f_##addr(Cpu *c) {                                                                           \
        static GuestFn fn;                                                                            \
        if (!fn) {                                                                                    \
            fn = dispatch_lookup(0x##addr##ull);                                                      \
            if (!fn) FATAL("pc_guest_calls: no game function at %llx\n", (unsigned long long)0x##addr##ull); \
        }                                                                                             \
        fn(c);                                                                                        \
    }

GUEST_FWD(70002bc8ec)  // item count getter (za_items.c get_count)
GUEST_FWD(70002bc9d0)  // item table lookup (game_item)
GUEST_FWD(700099e47c)  // item pocket (game_item)
GUEST_FWD(7000a5a228)  // item cap (game_item)
GUEST_FWD(700048963c)  // the original add-item path (za_items_pump)
