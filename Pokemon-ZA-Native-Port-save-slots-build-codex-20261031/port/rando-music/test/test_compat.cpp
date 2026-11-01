// Backward compatibility: built with the UNCHANGED port/randomizer/run_store.cpp (what r27b/r28 link), it must still
// list a run published by the r29-music store with a music bank (native_tables stays at 3/4 entries).
//   test_compat RUNS_ROOT RUN_ID [RUN_ID...]
#include "run_store.hpp"
#include <cstdio>
#include <set>
#include <string>
int main(int argc, char** argv) {
    if (argc < 3) return 2;
    std::set<std::string> ids;
    for (const auto& r : za::native::listRuns(argv[1])) ids.insert(r.id);
    int missing = 0;
    for (int i = 2; i < argc; i++)
        if (!ids.count(argv[i])) {
            fprintf(stderr, "FAIL: the r27b/r28 run store does not list %s\n", argv[i]);
            missing++;
        }
    if (!missing) printf("PASS: the unchanged r27b/r28 run store lists %d r29 runs (with and without music)\n", argc - 2);
    return missing ? 1 : 0;
}
