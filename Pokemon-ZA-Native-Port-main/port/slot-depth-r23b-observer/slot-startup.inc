/* Process-once startup preference. This does not bypass the runtime's checked
 * switch, and never performs I/O or a switch during an observer measurement. */
#ifndef ZA_SLOT_STARTUP_PATH
#define ZA_SLOT_STARTUP_PATH "/app0/slot-depth-options.txt"
#endif
#ifndef ZA_SLOT_STARTUP_FOPEN
#define ZA_SLOT_STARTUP_FOPEN fopen
#define ZA_SLOT_STARTUP_FREAD fread
#define ZA_SLOT_STARTUP_FERROR ferror
#define ZA_SLOT_STARTUP_FCLOSE fclose
#endif
static bool slot_startup_loaded, slot_startup_pending;
static unsigned slot_startup_requested=8;

static void slot_startup_init(void) {
    if (slot_startup_loaded) return;
    slot_startup_loaded=true; /* Never reset by observer reinitialization. */
    const char *source="missing";
    FILE *f=ZA_SLOT_STARTUP_FOPEN(ZA_SLOT_STARTUP_PATH,"rb");
    if (f) {
        unsigned char text[4];
        size_t n=ZA_SLOT_STARTUP_FREAD(text,1,sizeof text,f);
        unsigned char extra;
        size_t tail=ZA_SLOT_STARTUP_FREAD(&extra,1,1,f);
        bool io_ok=!ZA_SLOT_STARTUP_FERROR(f);
        if (ZA_SLOT_STARTUP_FCLOSE(f)) io_ok=false;
        source=io_ok ? "invalid" : "read_error";
        if (io_ok && tail==0 &&
            ((n==1 && !memcmp(text,"8",1)) || (n==2 && !memcmp(text,"8\n",2)))) {
            slot_startup_requested=8;source="file";
        } else if (io_ok && tail==0 &&
            ((n==2 && !memcmp(text,"16",2)) || (n==3 && !memcmp(text,"16\n",3)))) {
            slot_startup_requested=16;source="file";
        }
    } else if (errno!=ENOENT) source="read_error";
    slot_startup_pending=slot_startup_requested==16;
    char log[128];
    snprintf(log,sizeof log,"[za-r23b-startup] config requested=%u source=%s\n",slot_startup_requested,source);
    sceKernelDebugOutText(0,log);
}

/* Returns true only when this frame attempted the one startup switch. The
 * caller then skips mailbox polling/capture/measurement arming for that frame. */
static bool slot_startup_frame(uint64_t frame,bool submitted,bool represented,bool recording) {
    if (!slot_startup_pending || recording || !frame || !submitted || represented) return false;
    slot_startup_pending=false; /* Consume before the call, including rejection. */
    uint64_t before=plat_now_ns();
    int result=za_slot_depth_switch("16",frame);
    ZaSlotDepthStatus s={0};za_slot_depth_status(&s);
    uint64_t cost=plat_now_ns()-before;
    bool confirmed=slot_depth_status_valid(&s) && result==16 && s.result==result &&
        s.frame==frame && s.active_slots==16 && s.requested_slots==16 &&
        (s.previous_slots==8 || s.previous_slots==16) && s.completed_seq>=s.drained_seq &&
        s.budget_valid==1 && s.pool_bytes && s.pool_bytes<=ZA_SLOT_DEPTH_MAX_POOL_BYTES &&
        s.largest_free_extent && s.largest_free_extent<=s.pool_bytes && s.driver_bytes<=s.pool_bytes &&
        s.required_headroom_bytes>=ZA_SLOT_DEPTH_MIN_HEADROOM_BYTES &&
        s.largest_free_extent>=s.required_headroom_bytes;
    char log[1000];
    snprintf(log,sizeof log,
        "[za-r23b-startup] apply requested=16 result=%d confirmed=%u active=%u frame=%" PRIu64
        " status_frame=%" PRIu64 " status_result=%d cost_ns=%" PRIu64
        " budget_valid=%u pool=%" PRIu64 " largest_free_extent=%" PRIu64
        " driver=%" PRIu64 " required=%" PRIu64 "\n",
        result,confirmed?1u:0u,s.active_slots,frame,s.frame,s.result,cost,
        s.budget_valid,s.pool_bytes,s.largest_free_extent,s.driver_bytes,s.required_headroom_bytes);
    sceKernelDebugOutText(0,log);
    return true;
}
