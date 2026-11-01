/* (stands for runtime/nvn/vulkan/exec.c in test_symbolize.py) */
__attribute__((noinline)) int exec_fake_draw(int x) { int s = 0; for (int i = 0; i < x; i++) s += i * x; return s; }
