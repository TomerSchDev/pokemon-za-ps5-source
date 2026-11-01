/* Host stand-in for FreeBSD's <sys/cpuset.h> (test_clock_radv.c): glibc's cpu_set_t and CPU_* under _GNU_SOURCE. */
#pragma once
#include <sched.h>
typedef cpu_set_t cpuset_t;
