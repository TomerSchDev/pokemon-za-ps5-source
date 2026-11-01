/* Synthetic PIE for test_symbolize.py: a translated-game-like function, the anchor, and callers. */
int exec_fake_draw(int x);
int radv_fake_submit(int x);
__attribute__((noinline, used)) void za_prof_anchor(void) { __asm__ volatile(""); }
__attribute__((noinline)) int f_7100001000(int x) { return exec_fake_draw(x) + radv_fake_submit(x) + 1; }
int main(int argc, char **argv) { (void)argv; za_prof_anchor(); return f_7100001000(argc) & 1; }
