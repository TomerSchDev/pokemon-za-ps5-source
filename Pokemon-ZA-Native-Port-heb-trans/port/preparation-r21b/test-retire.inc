static void fixture(const char *sid,uint64_t seq,const char *op,const char *result,const char *name,
                    char dir[256],char ackpath[384],char capturepath[384]) {
    char text[900];
    snprintf(dir,256,ZA_OBSERVER_ROOT "/session_%s",sid);assert(directory(dir));
    snprintf(ackpath,384,"%s/ack_%" PRIu64 ".json",dir,seq);
    snprintf(capturepath,384,"%s/%s",dir,name);
    snprintf(text,sizeof text,"{\"session\":\"%s\",\"seq\":%" PRIu64 ",\"op\":\"%s\",\"result\":\"%s\",\"file\":\"%s\",\"cost_ns\":123}\n",sid,seq,op,result,name);
    assert(write_text(ackpath,text));
}
static void retire_request(uint64_t serial,const char *sid,uint64_t target,uint64_t frame_no) {
    char request[80];snprintf(request,sizeof request,"retire_capture %s:%" PRIu64,sid,target);
    send(serial,request);frame(frame_no,0);
}
static void test_retirement(uint64_t *serial,uint64_t *frame_no) {
    char current[17],dir[256],ackpath[384],path[384],target[80],keep[384],outside[384];
    snprintf(current,sizeof current,"%016" PRIx64,session);
    uint64_t snap=*serial;
    send((*serial)++,"snapshot");frame((*frame_no)++,0);
    snprintf(path,sizeof path,"%s/frame_%" PRIu64 "_%" PRIu64 ".png",session_dir,*frame_no-1,snap);
    assert(!access(path,F_OK));
    retire_request(*serial,current,snap,(*frame_no)++);
    assert(access(path,F_OK)&&errno==ENOENT);receipt_has((*serial)++,"\"result\":\"retired\"");
    snprintf(ackpath,sizeof ackpath,"%s/ack_%" PRIu64 ".json",session_dir,snap);assert(!access(ackpath,F_OK));
    retire_request(*serial,current,snap,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"already_absent\"");
    retire_request(*serial,current,*serial,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"rejected_target\"");

    const char *sid="0123456789abcdef";
    fixture(sid,9000,"snapshot","saved","frame_123_9000.png",dir,ackpath,path);
    assert(write_text(path,"........................................"));
    snprintf(keep,sizeof keep,"%s/untouched.bin",dir);assert(write_text(keep,"keep this unrelated file"));
    snprintf(target,sizeof target,"retire_capture %s:9000",sid);
    send(*serial,target);assert(!za_observer_menu("r123"));
    receipt_has((*serial)++,"\"result\":\"retired\"");assert(access(path,F_OK)&&!access(keep,F_OK)&&!access(ackpath,F_OK));

    const char *bad[]={"retire_capture", "retire_capture ../x:1", "retire_capture 0123456789ABCDEF:1",
        "retire_capture 0123456789abcdef:0","retire_capture 0123456789abcdef:01",
        "retire_capture 0123456789abcdef:18446744073709551616","retire_capture 0123456789abcdef:1/../x",
        "retire_capture 0123456789abcdef:1 extra"};
    for(unsigned j=0;j<sizeof bad/sizeof bad[0];j++) {
        send(*serial,bad[j]);frame((*frame_no)++,0);receipt_has((*serial)++,"\"op\":\"invalid\"");
    }
    retire_request(*serial,"1111111111111111",1,(*frame_no)++);
    receipt_has((*serial)++,"\"result\":\"invalid_session_directory\"");
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"missing_snapshot_ack\"");
    const char *names[]={"../../save/main","/download0/save/main","frame_1_9002.png","frame_01_9001.png","frame_1_09001.png",
        "frame_18446744073709551616_9001.png","frame_1_9001.png.extra"};
    for(unsigned j=0;j<sizeof names/sizeof names[0];j++) {
        fixture(sid,9001,"snapshot","saved",names[j],dir,ackpath,path);
        retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_snapshot_ack\"");
    }
    fixture(sid,9001,"measure","saved","frame_1_9001.png",dir,ackpath,path);
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_snapshot_ack\"");
    fixture(sid,9001,"snapshot","capture_failed","frame_1_9001.png",dir,ackpath,path);
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_snapshot_ack\"");
    fixture(sid,9001,"snapshot","saved","frame_1_9001.png",dir,ackpath,path);
    char invalid[1024];memset(invalid,'x',sizeof invalid-1);invalid[sizeof invalid-1]=0;assert(write_text(ackpath,invalid));
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_snapshot_ack\"");
    fixture(sid,9001,"snapshot","saved","frame_1_9001.png",dir,ackpath,path);
    FILE *af=fopen(ackpath,"ab");assert(af);assert(fwrite("\0evil",1,5,af)==5);assert(!fclose(af));
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_snapshot_ack\"");
    fixture(sid,9001,"snapshot","saved","frame_1_9001.png",dir,ackpath,path);
    af=fopen(ackpath,"ab");assert(af);assert(fwrite("evil",1,4,af)==4);assert(!fclose(af));
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_snapshot_ack\"");
    fixture(sid,9001,"snapshot","saved","frame_1_9001.png",dir,ackpath,path);
    assert(write_text(path,"too short"));
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_capture_file\"");assert(!unlink(path));
    /* Symlinked session, receipt and image are all rejected; target survives. */
    snprintf(outside,sizeof outside,ZA_OBSERVER_ROOT "/outside.bin");assert(write_text(outside,"........................................"));
    assert(!symlink(outside,path));
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_capture_file\"");
    assert(!access(outside,F_OK));assert(!unlink(path));
    assert(!unlink(ackpath));assert(!symlink(outside,ackpath));
    retire_request(*serial,sid,9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_snapshot_ack\"");assert(!unlink(ackpath));
    char linkdir[256];snprintf(linkdir,sizeof linkdir,ZA_OBSERVER_ROOT "/session_2222222222222222");assert(!symlink(dir,linkdir));
    retire_request(*serial,"2222222222222222",9001,(*frame_no)++);receipt_has((*serial)++,"\"result\":\"invalid_session_directory\"");assert(!unlink(linkdir));
    fixture(sid,9001,"snapshot","saved","frame_1_9001.png",dir,ackpath,path);
    assert(!mkdir(path,0755));retire_request(*serial,sid,9001,(*frame_no)++);
    receipt_has((*serial)++,"\"result\":\"invalid_capture_file\"");assert(!rmdir(path));
    /* Valid receipt wrong SID/sequence and extra/duplicate keys must not authorize unlink. */
    const char *malformed[]={
        "{\"session\":\"aaaaaaaaaaaaaaaa\",\"seq\":9001,\"op\":\"snapshot\",\"result\":\"saved\",\"file\":\"frame_1_9001.png\",\"cost_ns\":0}\n",
        "{\"session\":\"0123456789abcdef\",\"seq\":9002,\"op\":\"snapshot\",\"result\":\"saved\",\"file\":\"frame_1_9001.png\",\"cost_ns\":0}\n",
        "{\"session\":\"0123456789abcdef\",\"seq\":9001,\"op\":\"snapshot\",\"result\":\"saved\",\"file\":\"frame_1_9001.png\",\"cost_ns\":0,\"file\":\"../../save\"}\n"};
    assert(write_text(path,"........................................"));
    for(unsigned j=0;j<sizeof malformed/sizeof malformed[0];j++) {
        assert(write_text(ackpath,malformed[j]));retire_request(*serial,sid,9001,(*frame_no)++);
        receipt_has((*serial)++,"\"result\":\"invalid_snapshot_ack\"");assert(!access(path,F_OK));
    }
    fixture(sid,9001,"snapshot","saved","frame_1_9001.png",dir,ackpath,path);
    send((*serial)++,"measure 1");frame((*frame_no)++,0);assert(samples);
    uint64_t oldseq=sequence,oldpoll=poll_after;
    snprintf(target,sizeof target,"retire_capture %s:9001",sid);send(*serial,target);
    while(samples) {clock_ns+=NS/30;frame((*frame_no)++,0);assert(sequence==oldseq&&poll_after==oldpoll&&!access(path,F_OK));}
    clock_ns+=NS;frame((*frame_no)++,0);receipt_has((*serial)++,"\"result\":\"retired\"");
    assert(access(path,F_OK)&&!access(keep,F_OK)&&!access(outside,F_OK)&&!access(ackpath,F_OK));
    puts("retire_capture current/historic exact receipt scope, menu handling, measurement deferral, canonical target/filename, traversal/wrong ack/NUL/oversize/symlink/directory rejection passed");
}
