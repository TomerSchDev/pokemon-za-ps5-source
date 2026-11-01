"""Patch only the isolated build snapshot; preserve pre-r3 sources."""
from pathlib import Path
root = Path('/home/tomer/ps5-za-native/title-r1-20261027/source')

def replace(path, changes):
    p=root/path
    text=p.read_text()
    backup=p.with_name(p.name+'.before-r3')
    if not backup.exists(): backup.write_text(text)
    for old,new in changes:
        if new in text: continue
        if text.count(old)!=1: raise RuntimeError(f'Ambiguous source: {path}: {old[:80]}')
        text=text.replace(old,new)
    p.write_text(text)

replace(Path('runtime/paths.c'), [
('    if (!getcwd(g_start, sizeof g_start)) g_start[0] = 0;', '''#ifdef ZA_PS5
    // Native titles start with packaged resources at /app0. getcwd's import
    // faults on FW13.60 (r2); all data-root inputs below are absolute.
    snprintf(g_start, sizeof g_start, "/app0");
#else
    if (!getcwd(g_start, sizeof g_start)) g_start[0] = 0;
#endif'''),
('    mkdirs(root);\n    char msg[1400];', '''#ifdef ZA_PS5
    if (root[0] != '/') fail("PS5 data root must be an absolute sandbox path");
#endif
    mkdirs(root);
    char msg[1400];'''),
('    if (!getcwd(g_root, sizeof g_root)) snprintf(g_root, sizeof g_root, "%s", root);', '''#ifdef ZA_PS5
    snprintf(g_root, sizeof g_root, "%s", root);
#else
    if (!getcwd(g_root, sizeof g_root)) snprintf(g_root, sizeof g_root, "%s", root);
#endif''')])
replace(Path('runtime/platform/ps5.c'), [
('    if ((sig == SIGSEGV || sig == SIGBUS) && lazy_fault(fa)) return;', '''    if ((sig == SIGSEGV || sig == SIGBUS) && lazy_fault(fa)) return;
    // stderr-to-klog is asynchronous and can lose the last lines at abort.
    char diagnostic[240];
    snprintf(diagnostic, sizeof diagnostic, "[za-native-fault] sig=%d fa=%llx pc=%llx sp=%llx\\n",
             sig, (unsigned long long)fa, (unsigned long long)pc, (unsigned long long)sp);
    sceKernelDebugOutText(0, diagnostic);''')])
print('Applied r3 path/diagnostic patches to isolated snapshot')
