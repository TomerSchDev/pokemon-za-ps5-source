static unsigned immutable_calls,immutable_current,immutable_status_calls;
static int immutable_force=INT_MIN;
static bool immutable_bad_flags;
int za_immutable_spans_switch(const char *mode,uint64_t at_frame) {
    assert(at_frame>0);++immutable_calls;clock_ns+=NS/20;
    if(immutable_force!=INT_MIN)return immutable_force;
    int flags=immutable_mode(mode);assert(flags>=0);
    immutable_current=(unsigned)flags;return flags+1;
}
uint32_t za_immutable_spans_flags(void) {
    ++immutable_status_calls;return immutable_bad_flags ? 2u : immutable_current;
}
