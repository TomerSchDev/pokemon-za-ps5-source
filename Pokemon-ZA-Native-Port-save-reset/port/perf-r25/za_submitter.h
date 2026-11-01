/* r25: the submitter thread's core - a bounded FIFO of opaque items that one worker thread runs in order.
 *
 * No Vulkan here. exec.c packs its vkQueueSubmit2 / vkQueuePresentKHR calls into items (za_submitter_vk.inc) and the
 * host test (test/test_submitter.c) drives this same code with fake work, so ordering, back-pressure, the waits and the
 * shutdown are tested without a GPU.
 *
 * Guarantees:
 *  - items run one at a time, in push order, on the worker thread;
 *  - an item's storage stays valid, and is not reused, until it has run (the worker may modify its own item);
 *  - push blocks while the queue is full (back-pressure); nothing is dropped;
 *  - submitted_seq is the largest seq among the items that have run; za_subq_wait_submitted(q, seq) returns once every
 *    item pushed with a seq <= seq has run (a seq beyond anything pushed waits for what has been pushed);
 *  - za_subq_drain waits for every item pushed so far, of any kind; za_subq_quiesce_begin drains and then keeps the
 *    worker out until za_subq_quiesce_end, so another thread can use what the worker uses (exec.c: the VkQueue,
 *    for vkDeviceWaitIdle) exclusively;
 *  - za_subq_stop runs what is queued and joins the worker.
 * The worker takes only q->lock and q->exclusive. Callers may hold their own locks while they push or wait, as long as
 * the worker's item code never takes those locks (exec.c: the worker never takes za_sq_lock, seq_lock or cq_lock).
 * Quiesce must not be held across a push or a wait: the worker cannot run then. */
#pragma once
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifndef ZA_SUBQ_PAYLOAD
#define ZA_SUBQ_PAYLOAD 1024u
#endif
#define ZA_SUBQ_CAP_MAX 256u

enum { ZA_SUBQ_SUBMIT = 1, ZA_SUBQ_PRESENT = 2, ZA_SUBQ_OTHER = 3 };

typedef struct {
    uint32_t kind, size;
    uint64_t seq;  /* the timeline value the item signals; 0: none (a present) */
    _Alignas(16) unsigned char payload[ZA_SUBQ_PAYLOAD];
} ZaSubqItem;

typedef uint64_t (*ZaSubqClock)(void);                    /* nanoseconds, for the statistics */
typedef void (*ZaSubqExec)(void *ctx, ZaSubqItem *item);  /* runs on the worker */

typedef struct {
    uint64_t items, presents, busy_ns;        /* run by the worker */
    uint64_t pushes, push_waits, push_wait_ns; /* pushes, those that found the queue full, their wait */
    uint64_t depth_sum, depth_max;             /* items queued (running one included) right after each push */
} ZaSubqStats;

typedef struct {
    pthread_mutex_t lock;
    pthread_cond_t not_empty, not_full, progress;
    pthread_mutex_t exclusive;  /* held by the worker while an item runs; quiesce holds it to keep the worker out */
    ZaSubqItem *items;
    unsigned cap, head, count;   /* count includes the item running (it is released after it ran) */
    uint64_t pushed, done;       /* FIFO positions */
    uint64_t pushed_seq, submitted_seq;
    bool stop, started;
    pthread_t thread;
    ZaSubqExec exec;
    void *ctx;
    ZaSubqClock clock;
    ZaSubqStats st;              /* window statistics (za_subq_take_stats) */
} ZaSubq;

static void *za_subq_worker(void *arg) {
    ZaSubq *q = arg;
    pthread_mutex_lock(&q->lock);
    for (;;) {
        while (!q->count && !q->stop) pthread_cond_wait(&q->not_empty, &q->lock);
        if (!q->count) break;  /* stop, and nothing left */
        ZaSubqItem *item = &q->items[q->head];
        pthread_mutex_unlock(&q->lock);
        pthread_mutex_lock(&q->exclusive);
        const uint64_t t0 = q->clock ? q->clock() : 0;
        q->exec(q->ctx, item);
        const uint64_t t1 = q->clock ? q->clock() : 0;
        pthread_mutex_unlock(&q->exclusive);
        pthread_mutex_lock(&q->lock);
        if (item->seq > q->submitted_seq) q->submitted_seq = item->seq;
        q->st.items++;
        if (item->kind == ZA_SUBQ_PRESENT) q->st.presents++;
        q->st.busy_ns += t1 - t0;
        q->head = (q->head + 1) % q->cap;
        q->count--;
        q->done++;
        pthread_cond_broadcast(&q->progress);
        pthread_cond_signal(&q->not_full);
    }
    pthread_mutex_unlock(&q->lock);
    return NULL;
}

/* 0, or an errno from the thread start (then nothing was started and the queue must not be used). */
static int za_subq_init(ZaSubq *q, unsigned cap, ZaSubqExec exec, void *ctx, ZaSubqClock clock) {
    memset(q, 0, sizeof *q);
    if (!cap || cap > ZA_SUBQ_CAP_MAX || !exec) return 22;  /* EINVAL */
    q->items = calloc(cap, sizeof *q->items);
    if (!q->items) return 12;  /* ENOMEM */
    q->cap = cap, q->exec = exec, q->ctx = ctx, q->clock = clock;
    pthread_mutex_init(&q->lock, NULL);
    pthread_mutex_init(&q->exclusive, NULL);
    pthread_cond_init(&q->not_empty, NULL);
    pthread_cond_init(&q->not_full, NULL);
    pthread_cond_init(&q->progress, NULL);
    int r = pthread_create(&q->thread, NULL, za_subq_worker, q);
    if (r) {
        free(q->items);
        q->items = NULL;
        return r;
    }
    q->started = true;
    return 0;
}

/* Queue an item (copied). Blocks while the queue is full. Returns 0, or -1 when a timeline item would go backwards
 * (its seq not above the last pushed one): an ordering bug in the caller, nothing is queued. */
static int za_subq_push(ZaSubq *q, uint32_t kind, uint64_t seq, const void *payload, uint32_t size) {
    if (size > ZA_SUBQ_PAYLOAD) return -2;
    pthread_mutex_lock(&q->lock);
    if (seq && seq <= q->pushed_seq) {
        pthread_mutex_unlock(&q->lock);
        return -1;
    }
    if (q->count == q->cap) {
        const uint64_t t0 = q->clock ? q->clock() : 0;
        while (q->count == q->cap) pthread_cond_wait(&q->not_full, &q->lock);
        q->st.push_waits++;
        q->st.push_wait_ns += (q->clock ? q->clock() : 0) - t0;
    }
    ZaSubqItem *item = &q->items[(q->head + q->count) % q->cap];
    item->kind = kind, item->size = size, item->seq = seq;
    if (size) memcpy(item->payload, payload, size);
    q->count++;
    q->pushed++;
    if (seq) q->pushed_seq = seq;
    q->st.pushes++;
    q->st.depth_sum += q->count;
    if (q->count > q->st.depth_max) q->st.depth_max = q->count;
    pthread_cond_signal(&q->not_empty);
    pthread_mutex_unlock(&q->lock);
    return 0;
}

static void za_subq_wait_submitted(ZaSubq *q, uint64_t seq) {
    pthread_mutex_lock(&q->lock);
    const uint64_t target = seq < q->pushed_seq ? seq : q->pushed_seq;
    while (q->submitted_seq < target) pthread_cond_wait(&q->progress, &q->lock);
    pthread_mutex_unlock(&q->lock);
}

static uint64_t za_subq_submitted(ZaSubq *q) {
    pthread_mutex_lock(&q->lock);
    const uint64_t v = q->submitted_seq;
    pthread_mutex_unlock(&q->lock);
    return v;
}

static void za_subq_drain(ZaSubq *q) {
    pthread_mutex_lock(&q->lock);
    const uint64_t target = q->pushed;
    while (q->done < target) pthread_cond_wait(&q->progress, &q->lock);
    pthread_mutex_unlock(&q->lock);
}

static void za_subq_quiesce_begin(ZaSubq *q) {
    za_subq_drain(q);
    pthread_mutex_lock(&q->exclusive);
}

static void za_subq_quiesce_end(ZaSubq *q) { pthread_mutex_unlock(&q->exclusive); }

static void za_subq_take_stats(ZaSubq *q, ZaSubqStats *out) {
    pthread_mutex_lock(&q->lock);
    *out = q->st;
    memset(&q->st, 0, sizeof q->st);
    pthread_mutex_unlock(&q->lock);
}

/* Runs what is queued, then joins the worker and frees the queue. */
static void za_subq_stop(ZaSubq *q) {
    if (!q->started) return;
    pthread_mutex_lock(&q->lock);
    q->stop = true;
    pthread_cond_broadcast(&q->not_empty);
    pthread_mutex_unlock(&q->lock);
    pthread_join(q->thread, NULL);
    q->started = false;
    pthread_cond_destroy(&q->progress);
    pthread_cond_destroy(&q->not_full);
    pthread_cond_destroy(&q->not_empty);
    pthread_mutex_destroy(&q->exclusive);
    pthread_mutex_destroy(&q->lock);
    free(q->items);
    q->items = NULL;
}
