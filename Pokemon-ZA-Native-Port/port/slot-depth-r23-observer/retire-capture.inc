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
typedef struct {
    const char *step;
    int result, lstat_result, lstat_errno;
    unsigned mode, lstat_mode;
} RetireFs;
#ifndef ZA_RETIRE_LSTAT
#define ZA_RETIRE_LSTAT lstat
#endif
#ifndef ZA_RETIRE_FSTAT
#define ZA_RETIRE_FSTAT fstat
#endif
#ifndef ZA_RETIRE_READ
#define ZA_RETIRE_READ read
#endif
static void ack_retire(const Command *c, const char *sid, uint64_t target, const char *result,
                       const char *name, uint64_t bytes, int error_number, uint64_t cost,
                       const RetireFs *fs) {
    char path[320],text[1200];
    snprintf(path,sizeof path,"%s/ack_%" PRIu64 ".json",session_dir,c->seq);
    snprintf(text,sizeof text,
        "{\"session\":\"%016" PRIx64 "\",\"seq\":%" PRIu64 ",\"op\":\"retire_capture\",\"result\":\"%s\","
        "\"file\":\"\",\"cost_ns\":%" PRIu64 ",\"target_session\":\"%s\",\"target_seq\":%" PRIu64 ","
        "\"retired_file\":\"%s\",\"removed\":%s,\"bytes\":%" PRIu64 ",\"error_number\":%d,"
        "\"fs_step\":\"%s\",\"fs_result\":%d,\"fs_mode\":%u,"
        "\"lstat_result\":%d,\"lstat_errno\":%d,\"lstat_mode\":%u}\n",
        session,c->seq,result,cost,sid,target,name,!strcmp(result,"retired")?"true":"false",bytes,error_number,
        fs->step,fs->result,fs->mode,fs->lstat_result,fs->lstat_errno,fs->lstat_mode);
    if(!write_text(path,text))sceKernelDebugOutText(0,"[za-observer] retire_capture ack write failed\n");
}
/* The platform directory implementation uses open + fstat. Open with NOFOLLOW
 * so native lstat availability is not an authorization dependency. Never open
 * for writing; NONBLOCK prevents a crafted FIFO from blocking the observer.
 * Zero the output and fail closed if a successful shim fails to fill it. */
static int retire_open(const char *path, bool directory_path, struct stat *st,
                       RetireFs *fs, int *error_number, const char *open_step,
                       const char *stat_step, const char *type_step) {
    memset(st,0,sizeof *st);
    fs->step=open_step;fs->mode=0;errno=0;
    int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|(directory_path?O_DIRECTORY:0));
    fs->result=fd<0?fd:0;
    if(fd<0) {*error_number=errno?errno:EIO;return -1;}
    fs->step=stat_step;errno=0;
    fs->result=ZA_RETIRE_FSTAT(fd,st);fs->mode=(unsigned)st->st_mode;
    if(fs->result) {*error_number=errno?errno:EIO;close(fd);return -1;}
    if(directory_path?!S_ISDIR(st->st_mode):!S_ISREG(st->st_mode)) {
        fs->step=type_step;fs->result=-1;
        *error_number=directory_path?ENOTDIR:EINVAL;close(fd);return -1;
    }
    return fd;
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
    int error_number=0,dir_fd=-1,ack_fd=-1,capture_fd=-1,check_fd=-1,image_check_fd=-1;
    RetireFs fs={.step="target"};
    if(!retire_target(c->arg,sid,&target))return; /* parser already validated it */
    snprintf(current,sizeof current,"%016" PRIx64,session);
    if(!strcmp(sid,current)&&target>=c->seq)goto done;
    snprintf(dir,sizeof dir,ZA_OBSERVER_ROOT "/session_%s",sid);
    struct stat st,dir_st,check_st,diagnostic={0};
    errno=0;fs.lstat_result=ZA_RETIRE_LSTAT(dir,&diagnostic);
    fs.lstat_errno=errno;fs.lstat_mode=(unsigned)diagnostic.st_mode;
    dir_fd=retire_open(dir,true,&dir_st,&fs,&error_number,"session_open","session_fstat","session_type");
    if(dir_fd<0) {result="invalid_session_directory";goto done;}
    snprintf(path,sizeof path,"%s/ack_%" PRIu64 ".json",dir,target);
    ack_fd=retire_open(path,false,&st,&fs,&error_number,"ack_open","ack_fstat","ack_type");
    if(ack_fd<0) {result=error_number==ENOENT?"missing_snapshot_ack":"invalid_snapshot_ack";goto done;}
    if(st.st_size<=0||st.st_size>=(off_t)sizeof text) {result="invalid_snapshot_ack";goto done;}
    fs.step="ack_read";errno=0;
    ssize_t count=ZA_RETIRE_READ(ack_fd,text,sizeof text-1);
    fs.result=count<0?-1:0;
    if(count<0) {error_number=errno?errno:EIO;result="invalid_snapshot_ack";goto done;}
    size_t n=(size_t)count;
    char extra;
    bool ok=n==(size_t)st.st_size;
    if(!ok) {fs.result=-1;error_number=EIO;}
    else {
        errno=0;ssize_t tail=ZA_RETIRE_READ(ack_fd,&extra,1);
        fs.result=(int)tail;ok=tail==0;
        if(!ok)error_number=tail<0?(errno?errno:EIO):EIO;
    }
    text[n]=0;
    if(!ok||!retire_snapshot_ack(text,n,sid,target,name)) {name[0]=0;result="invalid_snapshot_ack";goto done;}
    snprintf(path,sizeof path,"%s/%s",dir,name);
    capture_fd=retire_open(path,false,&st,&fs,&error_number,"capture_open","capture_fstat","capture_type");
    if(capture_fd<0) {
        result=error_number==ENOENT?"already_absent":
            (error_number==ELOOP||!strcmp(fs.step,"capture_type"))?"invalid_capture_file":"capture_stat_failed";
        goto done;
    }
    if(st.st_size<=32) {result="invalid_capture_file";goto done;}
    bytes=(uint64_t)st.st_size;
    /* Recheck the fixed session path after reading the ack and opening the PNG.
     * Keeping both descriptors open prevents descriptor/inode reuse. */
    check_fd=retire_open(dir,true,&check_st,&fs,&error_number,"session_reopen","session_refstat","session_retype");
    if(check_fd<0) {result="session_changed";goto done;}
    if(check_st.st_dev!=dir_st.st_dev||check_st.st_ino!=dir_st.st_ino) {
        fs.step="session_identity";fs.result=-1;error_number=ESTALE;result="session_changed";goto done;
    }
    image_check_fd=retire_open(path,false,&check_st,&fs,&error_number,"capture_reopen","capture_refstat","capture_retype");
    if(image_check_fd<0) {result="capture_changed";goto done;}
    if(check_st.st_dev!=st.st_dev||check_st.st_ino!=st.st_ino||check_st.st_size!=st.st_size) {
        fs.step="capture_identity";fs.result=-1;error_number=ESTALE;result="capture_changed";goto done;
    }
    fs.step="unlink";fs.mode=(unsigned)st.st_mode;errno=0;fs.result=unlink(path);
    if(fs.result) {error_number=errno?errno:EIO;result="unlink_failed";goto done;}
    result="retired";
done:
    if(image_check_fd>=0)close(image_check_fd);
    if(check_fd>=0)close(check_fd);
    if(capture_fd>=0)close(capture_fd);
    if(ack_fd>=0)close(ack_fd);
    if(dir_fd>=0)close(dir_fd);
    ack_retire(c,sid,target,result,name,bytes,error_number,plat_now_ns()-before,&fs);
}
