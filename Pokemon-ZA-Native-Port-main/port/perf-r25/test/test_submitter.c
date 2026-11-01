/* Host tests for za_submitter.h (the submitter thread's core): order, back-pressure, wait-submitted, drain, quiesce,
 * stop, payload ownership, statistics, and a producer holding its own lock (as exec.c holds za_sq_lock). */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

#include "../za_submitter.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)

static uint64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
}

typedef struct {
    uint64_t n;            /* items run */
    uint64_t last_seq;     /* timeline seq of the last SUBMIT run */
    uint64_t last_index;   /* payload index of the last item run */
    int order_errors, payload_errors;
    unsigned sleep_us;     /* slow worker */
    int running;           /* (__atomic) an item is running now */
} Log;

typedef struct { uint64_t index; uint64_t pattern[8]; } Payload;

static void exec_log(void *ctx, ZaSubqItem *item) {
    Log *l = ctx;
    __atomic_store_n(&l->running, 1, __ATOMIC_RELEASE);
    Payload *p = (Payload *)item->payload;
    if (item->size != sizeof *p) l->payload_errors++;
    for (int i = 0; i < 8; i++) if (p->pattern[i] != p->index * 8 + (uint64_t)i) l->payload_errors++;
    if (l->n && p->index != l->last_index + 1) l->order_errors++;
    if (item->kind == ZA_SUBQ_SUBMIT) {
        if (item->seq <= l->last_seq) l->order_errors++;
        l->last_seq = item->seq;
    }
    p->pattern[0] = ~0ull;  /* the worker may modify its own item */
    l->last_index = p->index;
    if (l->sleep_us) usleep(l->sleep_us);
    __atomic_add_fetch(&l->n, 1, __ATOMIC_RELEASE);
    __atomic_store_n(&l->running, 0, __ATOMIC_RELEASE);
}

static Payload make(uint64_t index) {
    Payload p = {index, {0}};
    for (int i = 0; i < 8; i++) p.pattern[i] = index * 8 + (uint64_t)i;
    return p;
}

static void test_order_and_payload(void) {
    ZaSubq q;
    Log l = {0};
    CHECK(za_subq_init(&q, 16, exec_log, &l, now_ns) == 0);
    uint64_t seq = 0;
    for (uint64_t i = 0; i < 20000; i++) {
        Payload p = make(i);
        int present = i % 23 == 22;
        CHECK(za_subq_push(&q, present ? ZA_SUBQ_PRESENT : ZA_SUBQ_SUBMIT, present ? 0 : ++seq, &p, sizeof p) == 0);
    }
    za_subq_drain(&q);
    CHECK(__atomic_load_n(&l.n, __ATOMIC_ACQUIRE) == 20000);
    CHECK(l.order_errors == 0 && l.payload_errors == 0);
    CHECK(za_subq_submitted(&q) == seq);
    ZaSubqStats st;
    za_subq_take_stats(&q, &st);
    CHECK(st.items == 20000 && st.pushes == 20000 && st.presents == 20000 / 23);
    CHECK(st.depth_max <= 16 && st.depth_max >= 1);
    za_subq_take_stats(&q, &st);
    CHECK(st.items == 0 && st.pushes == 0);  /* (window statistics reset) */
    za_subq_stop(&q);
    printf("PASS order, payload copies, submitted_seq, statistics (20000 items, presents interleaved)\n");
}

static void test_backpressure(void) {
    ZaSubq q;
    Log l = {.sleep_us = 300};
    CHECK(za_subq_init(&q, 4, exec_log, &l, now_ns) == 0);
    for (uint64_t i = 0; i < 60; i++) {
        Payload p = make(i);
        CHECK(za_subq_push(&q, ZA_SUBQ_SUBMIT, i + 1, &p, sizeof p) == 0);
    }
    ZaSubqStats st;
    za_subq_take_stats(&q, &st);
    CHECK(st.push_waits > 0 && st.push_wait_ns > 0 && st.depth_max == 4);
    za_subq_drain(&q);
    CHECK(__atomic_load_n(&l.n, __ATOMIC_ACQUIRE) == 60 && l.order_errors == 0 && l.payload_errors == 0);
    za_subq_stop(&q);
    printf("PASS back-pressure: capacity 4, slow worker, %llu pushes waited, nothing dropped, order kept\n",
           (unsigned long long)st.push_waits);
}

typedef struct { ZaSubq *q; Log *l; uint64_t seq; int ok; } Waiter;
static void *waiter(void *arg) {
    Waiter *w = arg;
    za_subq_wait_submitted(w->q, w->seq);
    /* everything with a seq <= w->seq has run: items are seq == index + 1 here */
    w->ok = __atomic_load_n(&w->l->n, __ATOMIC_ACQUIRE) >= w->seq && za_subq_submitted(w->q) >= w->seq;
    return NULL;
}

static void test_wait_submitted(void) {
    ZaSubq q;
    Log l = {.sleep_us = 200};
    CHECK(za_subq_init(&q, 64, exec_log, &l, now_ns) == 0);
    for (uint64_t i = 0; i < 100; i++) {
        Payload p = make(i);
        CHECK(za_subq_push(&q, ZA_SUBQ_SUBMIT, i + 1, &p, sizeof p) == 0);
    }
    Waiter w[3] = {{&q, &l, 50, 0}, {&q, &l, 100, 0}, {&q, &l, 1000000, 0}};  /* the last: beyond anything pushed */
    pthread_t t[3];
    for (int i = 0; i < 3; i++) CHECK(pthread_create(&t[i], NULL, waiter, &w[i]) == 0);
    for (int i = 0; i < 3; i++) pthread_join(t[i], NULL);
    CHECK(w[0].ok && w[1].ok);
    CHECK(za_subq_submitted(&q) == 100);  /* the beyond-pushed waiter returned once all pushed items ran */
    za_subq_wait_submitted(&q, 0);         /* (0: nothing to wait for) */
    za_subq_stop(&q);
    printf("PASS wait_submitted: waits for that value only, beyond-pushed waits for what was pushed\n");
}

static void test_out_of_order(void) {
    ZaSubq q;
    Log l = {0};
    CHECK(za_subq_init(&q, 8, exec_log, &l, now_ns) == 0);
    Payload p = make(0);
    CHECK(za_subq_push(&q, ZA_SUBQ_SUBMIT, 10, &p, sizeof p) == 0);
    p = make(1);
    CHECK(za_subq_push(&q, ZA_SUBQ_SUBMIT, 10, &p, sizeof p) == -1);  /* not above the last pushed */
    CHECK(za_subq_push(&q, ZA_SUBQ_SUBMIT, 9, &p, sizeof p) == -1);
    CHECK(za_subq_push(&q, ZA_SUBQ_PRESENT, 0, &p, sizeof p) == 0);   /* a present carries none */
    unsigned char big[ZA_SUBQ_PAYLOAD + 1] = {0};
    CHECK(za_subq_push(&q, ZA_SUBQ_OTHER, 0, big, sizeof big) == -2);
    za_subq_drain(&q);
    CHECK(__atomic_load_n(&l.n, __ATOMIC_ACQUIRE) == 2);
    za_subq_stop(&q);
    printf("PASS rejected: a timeline value not above the last, an oversized payload (nothing queued)\n");
}

typedef struct { ZaSubq *q; uint64_t from, count; } Pusher;
static void *pusher(void *arg) {
    Pusher *p = arg;
    for (uint64_t i = 0; i < p->count; i++) {
        Payload pl = make(p->from + i);
        CHECK(za_subq_push(p->q, ZA_SUBQ_OTHER, 0, &pl, sizeof pl) == 0);
    }
    return NULL;
}

static void test_quiesce(void) {
    ZaSubq q;
    Log l = {0};
    CHECK(za_subq_init(&q, 32, exec_log, &l, now_ns) == 0);
    for (uint64_t i = 0; i < 10; i++) {
        Payload p = make(i);
        CHECK(za_subq_push(&q, ZA_SUBQ_SUBMIT, i + 1, &p, sizeof p) == 0);
    }
    za_subq_quiesce_begin(&q);
    CHECK(__atomic_load_n(&l.n, __ATOMIC_ACQUIRE) == 10);  /* drained before holding */
    Pusher p = {&q, 10, 5};
    pthread_t t;
    CHECK(pthread_create(&t, NULL, pusher, &p) == 0);
    pthread_join(t, NULL);
    usleep(20000);
    CHECK(__atomic_load_n(&l.n, __ATOMIC_ACQUIRE) == 10);  /* held out while quiesced */
    CHECK(!__atomic_load_n(&l.running, __ATOMIC_ACQUIRE));
    za_subq_quiesce_end(&q);
    za_subq_drain(&q);
    CHECK(__atomic_load_n(&l.n, __ATOMIC_ACQUIRE) == 15 && l.order_errors == 0);
    za_subq_stop(&q);
    printf("PASS quiesce: drained first, the worker held out (5 items pushed meanwhile ran after quiesce_end)\n");
}

typedef struct { ZaSubq *q; pthread_mutex_t *lock; uint64_t *seq; uint64_t count; } LockedPusher;
static void *locked_pusher(void *arg) {
    LockedPusher *p = arg;
    for (uint64_t i = 0; i < p->count; i++) {
        pthread_mutex_lock(p->lock);  /* as exec.c: za_sq_lock held while the driver submission is queued */
        Payload pl = make(*p->seq);
        CHECK(za_subq_push(p->q, ZA_SUBQ_SUBMIT, ++*p->seq, &pl, sizeof pl) == 0);
        pthread_mutex_unlock(p->lock);
    }
    return NULL;
}

static void test_locked_producers(void) {
    ZaSubq q;
    Log l = {.sleep_us = 20};
    CHECK(za_subq_init(&q, 4, exec_log, &l, now_ns) == 0);
    pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
    uint64_t seq = 0;
    LockedPusher a = {&q, &lock, &seq, 400}, b = {&q, &lock, &seq, 400};
    pthread_t ta, tb;
    CHECK(pthread_create(&ta, NULL, locked_pusher, &a) == 0);
    CHECK(pthread_create(&tb, NULL, locked_pusher, &b) == 0);
    pthread_join(ta, NULL);
    pthread_join(tb, NULL);
    za_subq_wait_submitted(&q, seq);
    CHECK(__atomic_load_n(&l.n, __ATOMIC_ACQUIRE) == 800 && l.order_errors == 0 && za_subq_submitted(&q) == 800);
    za_subq_stop(&q);
    printf("PASS two producers holding their own lock while queueing into a full queue: no deadlock, order kept\n");
}

static void test_stop(void) {
    ZaSubq q;
    Log l = {.sleep_us = 100};
    CHECK(za_subq_init(&q, 64, exec_log, &l, now_ns) == 0);
    for (uint64_t i = 0; i < 40; i++) {
        Payload p = make(i);
        CHECK(za_subq_push(&q, ZA_SUBQ_SUBMIT, i + 1, &p, sizeof p) == 0);
    }
    za_subq_stop(&q);  /* runs what is queued, then joins */
    CHECK(__atomic_load_n(&l.n, __ATOMIC_ACQUIRE) == 40);
    za_subq_stop(&q);  /* (twice: no-op) */
    ZaSubq bad;
    CHECK(za_subq_init(&bad, 0, exec_log, &l, now_ns) != 0);
    CHECK(za_subq_init(&bad, ZA_SUBQ_CAP_MAX + 1, exec_log, &l, now_ns) != 0);
    printf("PASS stop: the queued items run, the worker joins; invalid capacities refused\n");
}

int main(void) {
    test_order_and_payload();
    test_backpressure();
    test_wait_submitted();
    test_out_of_order();
    test_quiesce();
    test_locked_producers();
    test_stop();
    printf("PASS za_submitter.h\n");
    return 0;
}
