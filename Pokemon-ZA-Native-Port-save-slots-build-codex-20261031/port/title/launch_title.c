// SPDX-License-Identifier: GPL-3.0-or-later
// Fixed-title development launcher. Public launch ABI cross-checked against:
// https://github.com/leolobato/playden-ps5/blob/main/tools/self-update-relaunch/main.c
#include <dirent.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#ifndef ZA_LAUNCH_ID
#define ZA_LAUNCH_ID "PPSA91761"
#endif
#ifndef ZA_LAUNCH_LOG
#define ZA_LAUNCH_LOG "/data/za-native-title-launch.log"
#endif

typedef struct {
    uint32_t size, user_id, app_opt, pad;
    uint64_t crash_report, check_flag;
} launch_params;
int sceUserServiceInitialize(void *);
int sceUserServiceGetForegroundUser(uint32_t *);
int sceLncUtilInitialize(void);
uint32_t sceLncUtilLaunchApp(const char *, const char **, launch_params *);
uint32_t sceSystemServiceLaunchApp(const char *, const char **, launch_params *);

int main(void) {
    FILE *log = fopen(ZA_LAUNCH_LOG, "w");
    if (!log) return 1;
    setvbuf(log, NULL, _IONBF, 0);
    DIR *sandbox = opendir("/mnt/sandbox");
    if (!sandbox) { fprintf(log, "cannot inspect running titles; refusing launch\n"); fclose(log); return 1; }
    struct dirent *entry;
    int active = 0;
    while ((entry = readdir(sandbox))) {
        const char *name = entry->d_name;
        if (strlen(name) >= 10 && name[9] == '_' &&
            (!strncmp(name, "PPSA", 4) || !strncmp(name, "CUSA", 4) || !strncmp(name, "FAKE", 4))) {
            fprintf(log, "title still active: %s; refusing launch\n", name);
            active = 1;
        }
    }
    closedir(sandbox);
    if (active) { fprintf(log, "active title preflight failed\n"); fclose(log); return 1; }
    FILE *registration = fopen("/user/app/" ZA_LAUNCH_ID "/mount.lnk", "rb");
    if (!registration) {
        fprintf(log, "registration open failed errno=%d uid=%d\n", errno, getuid());
        fclose(log); return 1;
    }
    fclose(registration);
    (void)sceUserServiceInitialize(NULL);
    uint32_t user = UINT32_MAX;
    int user_rc = sceUserServiceGetForegroundUser(&user);
    fprintf(log, "user_rc=%d user=%u lnc_init=%d\n", user_rc, user, sceLncUtilInitialize());
    if (user_rc != 0 || user == UINT32_MAX) { fclose(log); return 1; }
    launch_params params = {sizeof params, user, 0, 0, 0, 0};
    uint32_t rc = sceLncUtilLaunchApp(ZA_LAUNCH_ID, NULL, &params);
    fprintf(log, "sceLncUtilLaunchApp rc=0x%08x\n", rc);
    if (rc & 0x80000000u) {
        params.check_flag = 1;
        rc = sceSystemServiceLaunchApp(ZA_LAUNCH_ID, NULL, &params);
        fprintf(log, "sceSystemServiceLaunchApp rc=0x%08x\n", rc);
    }
    fclose(log);
    return (rc & 0x80000000u) ? 1 : 0;
}
