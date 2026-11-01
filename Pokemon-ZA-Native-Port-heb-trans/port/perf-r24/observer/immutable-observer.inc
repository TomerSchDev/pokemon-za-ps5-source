static int immutable_mode(const char *mode) {
    return !mode ? -1 : !strcmp(mode,"off") ? 0 : !strcmp(mode,"on") ? 1 : -1;
}
/* Actual executor-owned status, never the requested string, determines success. */
static void ack_immutable(const Command *c,const char *result,int applied,uint64_t frame,uint64_t cost) {
    uint32_t flags = za_immutable_spans_flags();
    bool coherent = flags <= 1;
    if (!coherent || (!strcmp(result,"applied") &&
        (applied != (int)flags + 1 || (int)flags != immutable_mode(c->arg)))) result = "receipt_mismatch";
    const char *actual = coherent ? (flags ? "on" : "off") : "";
    char path[320],text[800];
    snprintf(path,sizeof path,"%s/ack_%" PRIu64 ".json",session_dir,c->seq);
    snprintf(text,sizeof text,
        "{\"session\":\"%016" PRIx64 "\",\"seq\":%" PRIu64 ",\"op\":\"immutable_spans\",\"result\":\"%s\","
        "\"file\":\"\",\"cost_ns\":%" PRIu64 ",\"requested_mode\":\"%s\",\"mode\":\"%s\",\"flags\":%d,\"frame\":%" PRIu64 ",\"runtime_result\":%d}\n",
        session,c->seq,result,cost,c->arg,actual,coherent ? (int)flags : -1,frame,applied);
    if (!write_text(path,text)) sceKernelDebugOutText(0,"[za-observer] immutable spans ack write failed\n");
}
