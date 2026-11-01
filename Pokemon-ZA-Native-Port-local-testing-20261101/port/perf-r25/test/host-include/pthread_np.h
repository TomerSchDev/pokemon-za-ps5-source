/* Host stand-in for FreeBSD's <pthread_np.h> (test_clock_radv.c): glibc declares pthread_{get,set}affinity_np in
 * <pthread.h> under _GNU_SOURCE. */
#pragma once
#include <pthread.h>
