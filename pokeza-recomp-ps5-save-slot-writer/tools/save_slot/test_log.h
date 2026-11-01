// tools/save_slot/test.sh: save_slot.c's log goes to the test's capture
#pragma once
void test_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
