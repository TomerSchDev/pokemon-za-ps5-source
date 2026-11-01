/* Public observer control/status APIs: same serialization as guest execution. */
int za_immutable_spans_switch(const char *mode, uint64_t frame) {
    exec_lock_take();
    int applied = backend_immutable_spans_switch(mode, frame);
    exec_lock_give();
    return applied;
}
uint32_t za_immutable_spans_flags(void) {
    exec_lock_take();
    uint32_t flags = backend_immutable_spans_flags();
    exec_lock_give();
    return flags;
}
