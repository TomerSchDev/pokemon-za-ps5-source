/* One deliberately narrow housekeeping operation. The caller supplies only a
 * canonical observer SID and snapshot sequence, never a path or filename.
 * The parent must first read twice, hash and retain the capture locally.
 * Ack files remain as the audit trail. No recursion or save paths exist here. */
static bool retire_decimal(const char *text, uint64_t *out, bool zero_ok) {
    if (!decimal(text,out) || (!zero_ok && !*out)) return false;
    return text[0] != '0' || text[1] == 0;
}
static bool retire_target(const char *text, char sid[17], uint64_t *seq) {
    size_t n = strlen(text);
    if (n < 18 || n > 37 || text[16] != ':') return false;
    for (unsigned i=0;i<16;i++)
        if (!((text[i]>='0'&&text[i]<='9')||(text[i]>='a'&&text[i]<='f'))) return false;
    memcpy(sid,text,16);sid[16]=0;
    return retire_decimal(text+17,seq,false);
}
static void ack_retire(const Command *c, const char *sid, uint64_t target, const char *result,
                       const char *name, uint64_t bytes, int error_number, uint64_t cost) {
    char path[320],text[900];
    snprintf(path,sizeof path,"%s/ack_%" PRIu64 ".json",session_dir,c->seq);
    snprintf(text,sizeof text,
        "{\"session\":\"%016" PRIx64 "\",\"seq\":%" PRIu64 ",\"op\":\"retire_capture\",\"result\":\"%s\","
        "\"file\":\"\",\"cost_ns\":%" PRIu64 ",\"target_session\":\"%s\",\"target_seq\":%" PRIu64 ","
        "\"retired_file\":\"%s\",\"removed\":%s,\"bytes\":%" PRIu64 ",\"error_number\":%d}\n",
        session,c->seq,result,cost,sid,target,name,!strcmp(result,"retired")?"true":"false",bytes,error_number);
    if(!write_text(path,text))sceKernelDebugOutText(0,"[za-observer] retire_capture ack write failed\n");
}
static bool retire_snapshot_name(const char *name, uint64_t target) {
    char frame_text[21]={0},seq_text[21]={0},canonical[100];
    uint64_t frame,seq;
    int used=0;
    if(sscanf(name,"frame_%20[0-9]_%20[0-9].png%n",frame_text,seq_text,&used)!=2 ||
       used<=0 || (size_t)used!=strlen(name) || !retire_decimal(frame_text,&frame,false) ||
       !retire_decimal(seq_text,&seq,false) || seq!=target) return false;
    snprintf(canonical,sizeof canonical,"frame_%" PRIu64 "_%" PRIu64 ".png",frame,seq);
    return !strcmp(name,canonical);
}
/* Require the exact native snapshot receipt representation, including no extra
 * keys, escaped names, duplicate keys, embedded NUL, traversal or trailing data. */
static bool retire_snapshot_ack(const char *text, size_t n, const char *wanted_sid,
                                 uint64_t target, char name[100]) {
    char sid[17]={0},seq_text[21]={0},cost_text[21]={0};
    uint64_t seq,cost;
    int used=0;
    if(memchr(text,0,n))return false;
    int fields=sscanf(text,
        "{\"session\":\"%16[0-9a-f]\",\"seq\":%20[0-9],\"op\":\"snapshot\",\"result\":\"saved\",\"file\":\"%99[^\"]\",\"cost_ns\":%20[0-9]}%n",
        sid,seq_text,name,cost_text,&used);
    if(fields!=4 || used<=0 || strcmp(sid,wanted_sid) || !retire_decimal(seq_text,&seq,false) ||
       seq!=target || !retire_decimal(cost_text,&cost,true))return false;
    if((size_t)used!=n && !((size_t)used+1==n && text[used]=='\n'))return false;
    return retire_snapshot_name(name,target);
}
static void retire_capture(const Command *c) {
    uint64_t before=plat_now_ns(),target=0,bytes=0;
    char sid[17]={0},current[17],dir[256],path[384],name[100]={0},text[1024];
    const char *result="rejected_target";
    int error_number=0;
    if(!retire_target(c->arg,sid,&target))return; /* parser already validated it */
    snprintf(current,sizeof current,"%016" PRIx64,session);
    if(!strcmp(sid,current)&&target>=c->seq)goto done;
    snprintf(dir,sizeof dir,ZA_OBSERVER_ROOT "/session_%s",sid);
    struct stat st;
    if(lstat(dir,&st)||!S_ISDIR(st.st_mode)) {result="invalid_session_directory";goto done;}
    snprintf(path,sizeof path,"%s/ack_%" PRIu64 ".json",dir,target);
    if(lstat(path,&st)) {error_number=errno;result="missing_snapshot_ack";goto done;}
    if(!S_ISREG(st.st_mode)||st.st_size<=0||st.st_size>=(off_t)sizeof text) {result="invalid_snapshot_ack";goto done;}
    FILE *f=fopen(path,"rb");
    if(!f) {error_number=errno;result="missing_snapshot_ack";goto done;}
    size_t n=fread(text,1,sizeof text-1,f);
    bool ok=!ferror(f)&&n==(size_t)st.st_size;
    if(fclose(f))ok=false;
    text[n]=0;
    if(!ok||!retire_snapshot_ack(text,n,sid,target,name)) {name[0]=0;result="invalid_snapshot_ack";goto done;}
    snprintf(path,sizeof path,"%s/%s",dir,name);
    if(lstat(path,&st)) {
        error_number=errno;
        result=error_number==ENOENT?"already_absent":"capture_stat_failed";
        goto done;
    }
    if(!S_ISREG(st.st_mode)||st.st_size<=32) {result="invalid_capture_file";goto done;}
    bytes=(uint64_t)st.st_size;
    if(unlink(path)) {error_number=errno;result="unlink_failed";goto done;}
    result="retired";
done:
    ack_retire(c,sid,target,result,name,bytes,error_number,plat_now_ns()-before);
}
