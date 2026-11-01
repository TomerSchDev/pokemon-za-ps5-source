/* ui-v2 PC proof: POSIX bits the randomizer sources use that the Windows CRT spells differently. Force-included
 * (-include) when compiling the title-side C/C++ sources for the Windows runtime; never part of the PS5 build. */
#pragma once
#ifdef _WIN32
#include <direct.h>
#include <io.h>
#include <stdio.h>
#include <sys/stat.h>
#ifdef __cplusplus
extern "C" {
#endif
int za_pc_rename(const char *from, const char *to);  /* replaces an existing destination, as POSIX rename does */
int za_pc_mkdir(const char *path);
int za_pc_fsync(int fd);
#ifdef __cplusplus
}
#endif
#define rename(a, b) za_pc_rename((a), (b))
#define mkdir(p, m) za_pc_mkdir((p))
#define fsync(fd) za_pc_fsync((fd))
#ifndef O_NOFOLLOW
#define O_NOFOLLOW 0
#endif
#ifndef S_ISDIR
#define S_ISDIR(m) (((m) & S_IFMT) == S_IFDIR)
#endif
#ifndef S_ISREG
#define S_ISREG(m) (((m) & S_IFMT) == S_IFREG)
#endif
#endif
