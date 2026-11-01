/* Process-once startup preference. This does not bypass the runtime's checked
 * switch, and never performs I/O or a switch during an observer measurement. */
#ifndef ZA_SLOT_STARTUP_PATH
#define ZA_SLOT_STARTUP_PATH "/app0/slot-depth-options.txt"
#endif
#ifndef ZA_SLOT_STARTUP_OPEN
#define ZA_SLOT_STARTUP_OPEN open
#define ZA_SLOT_STARTUP_READ read
#define ZA_SLOT_STARTUP_CLOSE close
#endif
static bool slot_startup_loaded, slot_startup_pending;
static unsigned slot_startup_requested=8;

static void slot_startup_init(void) {
    if (slot_startup_loaded) return;
    slot_startup_loaded=true; /* Never reset by observer reinitialization. */
    const char *source="invalid";
    int open_errno=0,read_errno=0,close_result=-2,close_errno=0;
    ssize_t read_result=-2;
    unsigned read_calls=0;size_t n=0;bool eof=false;
    errno=0;
    int fd=ZA_SLOT_STARTUP_OPEN(ZA_SLOT_STARTUP_PATH,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);
    open_errno=errno;
    if (fd>=0) {
        unsigned char text[4];bool io_ok=true;
        /* The longest accepted value has three bytes. Four bytes are always
         * invalid. Partial reads advance; errors (including EINTR) fail closed
         * without retry. At most four calls, and four bytes, can be consumed. */
        while (n<sizeof text) {
            errno=0;
            read_result=ZA_SLOT_STARTUP_READ(fd,text+n,sizeof text-n);
            read_errno=errno;++read_calls;
            if (read_result<0 || (size_t)read_result>sizeof text-n) {io_ok=false;source="read_error";break;}
            if (!read_result) {eof=true;break;}
            n+=(size_t)read_result;
        }
        errno=0;
        close_result=ZA_SLOT_STARTUP_CLOSE(fd);
        close_errno=errno;
        if (close_result) {if(io_ok)source="close_error";io_ok=false;}
        if (io_ok && eof &&
            ((n==1 && !memcmp(text,"8",1)) || (n==2 && !memcmp(text,"8\n",2)))) {
            slot_startup_requested=8;source="file";
        } else if (io_ok && eof &&
            ((n==2 && !memcmp(text,"16",2)) || (n==3 && !memcmp(text,"16\n",3)))) {
            slot_startup_requested=16;source="file";
        } else if (io_ok && eof &&  /* r24: 32 and 64 too (still at most three bytes) */
            ((n==2 && !memcmp(text,"32",2)) || (n==3 && !memcmp(text,"32\n",3)))) {
            slot_startup_requested=32;source="file";
        } else if (io_ok && eof &&
            ((n==2 && !memcmp(text,"64",2)) || (n==3 && !memcmp(text,"64\n",3)))) {
            slot_startup_requested=64;source="file";
        }
    } else source=open_errno==ENOENT ? "missing" : "open_error";
    slot_startup_pending=slot_startup_requested>8;
    char log[640];
    snprintf(log,sizeof log,"[za-r23c-startup] config requested=%u source=%s open_result=%d open_errno=%d"
        " read_result=%" PRId64 " read_errno=%d read_calls=%u bytes=%zu eof=%u close_result=%d close_errno=%d\n",
        slot_startup_requested,source,fd,open_errno,(int64_t)read_result,read_errno,read_calls,n,eof?1u:0u,close_result,close_errno);
    sceKernelDebugOutText(0,log);
}

/* Returns true only when this frame attempted the one startup switch. The
 * caller then skips mailbox polling/capture/measurement arming for that frame. */
static bool slot_startup_frame(uint64_t frame,bool submitted,bool represented,bool recording) {
    if (!slot_startup_pending || recording || !frame || !submitted || represented) return false;
    slot_startup_pending=false; /* Consume before the call, including rejection. */
    uint64_t before=plat_now_ns();
    const unsigned want=slot_startup_requested;
    char depth[4];snprintf(depth,sizeof depth,"%u",want);
    int result=za_slot_depth_switch(depth,frame);
    ZaSlotDepthStatus s={0};za_slot_depth_status(&s);
    uint64_t cost=plat_now_ns()-before;
    bool confirmed=slot_depth_status_valid(&s) && result==(int)want && s.result==result &&
        s.frame==frame && s.active_slots==want && s.requested_slots==want &&
        slot_depth_is(s.previous_slots) && s.completed_seq>=s.drained_seq &&
        s.budget_valid==1 && s.pool_bytes && s.pool_bytes<=ZA_SLOT_DEPTH_MAX_POOL_BYTES &&
        s.largest_free_extent && s.largest_free_extent<=s.pool_bytes && s.driver_bytes<=s.pool_bytes &&
        s.required_headroom_bytes>=ZA_SLOT_DEPTH_MIN_HEADROOM_BYTES &&
        s.largest_free_extent>=s.required_headroom_bytes;
    char log[1000];
    snprintf(log,sizeof log,
        "[za-r23c-startup] apply requested=%u result=%d confirmed=%u active=%u frame=%" PRIu64
        " status_frame=%" PRIu64 " status_result=%d cost_ns=%" PRIu64
        " budget_valid=%u pool=%" PRIu64 " largest_free_extent=%" PRIu64
        " driver=%" PRIu64 " required=%" PRIu64 "\n",
        want,result,confirmed?1u:0u,s.active_slots,frame,s.frame,s.result,cost,
        s.budget_valid,s.pool_bytes,s.largest_free_extent,s.driver_bytes,s.required_headroom_bytes);
    sceKernelDebugOutText(0,log);
    return true;
}
