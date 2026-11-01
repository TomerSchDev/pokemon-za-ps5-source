// SPDX-License-Identifier: GPL-3.0-or-later
// Cleanup for an owned title that failed before its observer. No file writes.
// KillApp ABI: ps5-payload-dev/websrv src/ps5/hbldr.c; Lnc ABI: pldmgr.
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/sysctl.h>
#include <sys/user.h>
#include <stdlib.h>
int sceLncUtilInitialize(void);
int sceLncUtilGetAppIdOfRunningBigApp(void);
int sceLncUtilGetAppTitleId(uint32_t, char *);
int sceLncUtilKillApp(uint32_t);
int sceLncUtilForceKillApp(uint32_t);
int sceSystemServiceKillApp(int, int, int, int);
#ifndef ZA_EXPECTED_TITLE
#define ZA_EXPECTED_TITLE "PPSA91990"
#endif
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    unsigned long expected_app, expected_pid;
#if defined(ZA_EXPECTED_APP_ID) && defined(ZA_EXPECTED_PID)
    expected_app = ZA_EXPECTED_APP_ID; expected_pid = ZA_EXPECTED_PID;
#else
    char *end_app = NULL, *end_pid = NULL;
    if (argc != 3) { puts("REFUSED: exact app ID and PID arguments required"); return 1; }
    expected_app = strtoul(argv[1], &end_app, 0);
    expected_pid = strtoul(argv[2], &end_pid, 0);
    if (!argv[1][0] || !argv[2][0] || *end_app || *end_pid ||
        !expected_app || expected_app >= 0x80000000 || expected_pid <= 1 || expected_pid > 0x7fffffff) {
        puts("REFUSED: invalid owned identity"); return 1;
    }
#endif
    int init = sceLncUtilInitialize();
    int app = sceLncUtilGetAppIdOfRunningBigApp();
    char title[32] = {0};
    int title_rc = app == -1 ? -1 : sceLncUtilGetAppTitleId((uint32_t)app, title);
    printf("init=%d app=0x%08x expected=0x%08x title_rc=%d title=%s\n",
           init, app, (unsigned)expected_app, title_rc, title);
    if (app != -1 && (app != (int)expected_app || title_rc != 0 || strcmp(title, ZA_EXPECTED_TITLE))) {
        puts("REFUSED: current app is not the exact owned side launch");
        return 1;
    }
    struct kinfo_proc info = {0};
    size_t size = 0;
    int mib[4] = {CTL_KERN, KERN_PROC, KERN_PROC_PROC, 0};
    int query = sysctl(mib, 4, NULL, &size, NULL, 0);
    void *buffer = query == 0 && size > 0 && size < 16 * 1024 * 1024 ? malloc(size) : NULL;
    if (buffer && sysctl(mib, 4, buffer, &size, NULL, 0) == 0) {
        for (size_t offset = 0; offset + sizeof(struct kinfo_proc) <= size;) {
            struct kinfo_proc *entry = (struct kinfo_proc *)((char *)buffer + offset);
            if (entry->ki_structsize < sizeof(*entry) || entry->ki_structsize > size - offset) break;
            if (entry->ki_pid == (int)expected_pid) { info = *entry; break; }
            offset += entry->ki_structsize;
        }
    }
    free(buffer);
    printf("process query=%d errno=%d bytes=%zu observed pid=%d name=%s\n", query, errno, size, info.ki_pid, info.ki_comm);
    if (info.ki_pid != (int)expected_pid || strcmp(info.ki_comm, "eboot.bin")) {
        puts("REFUSED: original failed eboot PID is no longer present");
        return 1;
    }
    printf("owned pid=%d stat=%d flags=0x%lx wait=%s threads=%d parent=%d tracer=%d\n",
           info.ki_pid, info.ki_stat, (unsigned long)info.ki_flag, info.ki_wmesg, info.ki_numthreads, info.ki_ppid, info.ki_tracer);
    int sent = kill((int)expected_pid, SIGKILL);
    printf("owned SIGKILL rc=%d errno=%d\n", sent, errno);
    sent = kill((int)expected_pid, SIGCONT);
    printf("owned SIGCONT rc=%d errno=%d\n", sent, errno);
    if (app == -1) {
        int rc = sceLncUtilForceKillApp((uint32_t)expected_app);
        printf("sceLncUtilForceKillApp(original)=0x%08x\n", rc);
        return rc != 0;
    }
    int rc = sceSystemServiceKillApp(app, -1, 0, 0);
    printf("sceSystemServiceKillApp=0x%08x\n", rc);
    if (rc != 0) {
        rc = sceLncUtilKillApp((uint32_t)app);
        printf("sceLncUtilKillApp=0x%08x\n", rc);
    }
    if (rc != 0) {
        rc = sceLncUtilForceKillApp((uint32_t)app);
        printf("sceLncUtilForceKillApp=0x%08x\n", rc);
    }
    return rc != 0;
}
