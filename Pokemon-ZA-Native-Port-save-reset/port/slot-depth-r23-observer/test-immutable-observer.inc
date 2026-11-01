static void test_immutable_observer(uint64_t *serial_ptr,uint64_t *frame_ptr) {
    uint64_t serial=*serial_ptr,i=*frame_ptr;
    unsigned prep_before=preparation_current,prep_calls_before=preparation_calls;
    assert(!immutable_calls && !immutable_current);
    send(serial,"immutable_spans on");assert(!za_observer_menu("r123"));
    assert(!immutable_calls);receipt_has(serial,"\"result\":\"rejected_in_menu\"");
    receipt_has(serial++,"\"mode\":\"off\",\"flags\":0");
    const char *bad[]={"immutable_spans","immutable_spans enabled","immutable_spans ON","immutable_spans on extra","immutable_spans ../off"};
    for(unsigned j=0;j<sizeof bad/sizeof bad[0];++j) {
        send(serial,bad[j]);frame(i++,0);assert(!immutable_calls);
        receipt_has(serial++,"\"op\":\"invalid\"");
    }
    const char *modes[]={"off","on","on","off"};
    for(unsigned j=0;j<4;++j) {
        char request[80],wanted[100];snprintf(request,sizeof request,"immutable_spans %s",modes[j]);
        send(serial,request);frame(i++,0);unsigned flag=(unsigned)immutable_mode(modes[j]);
        assert(immutable_current==flag && immutable_calls==j+1);
        receipt_has(serial,"\"result\":\"applied\"");
        snprintf(wanted,sizeof wanted,"\"mode\":\"%s\",\"flags\":%u",modes[j],flag);receipt_has(serial,wanted);
        snprintf(wanted,sizeof wanted,"\"frame\":%" PRIu64,i-1);receipt_has(serial,wanted);
        snprintf(wanted,sizeof wanted,"\"runtime_result\":%u",flag+1);receipt_has(serial,wanted);
        receipt_has(serial++,"\"cost_ns\":50000000");
    }
    send(serial-1,"immutable_spans on");frame(i++,0);assert(immutable_calls==4 && !immutable_current);
    send(serial,"immutable_spans on");za_observer_frame(i++,true,true,0,(void*)1,capture);
    assert(immutable_calls==4);receipt_has(serial++,"\"result\":\"rejected_boundary\"");
    send(serial,"immutable_spans on");za_observer_frame(i++,false,false,0,(void*)1,capture);
    assert(immutable_calls==4);receipt_has(serial++,"\"result\":\"rejected_boundary\"");
    send(serial,"immutable_spans on");za_observer_frame(0,true,false,0,(void*)1,capture);
    assert(immutable_calls==4);receipt_has(serial++,"\"result\":\"rejected_boundary\"");
    send(serial++,"measure 1");frame(i++,0);assert(samples && !stop_at);
    uint64_t consumed=sequence,old_poll=poll_after;
    unsigned old_status=immutable_status_calls;
    send(serial,"immutable_spans on");frame(i++,0);
    assert(samples && !stop_at && immutable_calls==4 && sequence==consumed && poll_after==old_poll);
    assert(!za_observer_menu("r123"));assert(sequence==consumed && poll_after==old_poll);
    clock_ns+=NS;frame(i++,0);assert(stop_at);
    while(samples) {
        clock_ns+=NS/30;frame(i++,0);
        assert(immutable_calls==4 && immutable_status_calls==old_status && sequence==consumed && poll_after==old_poll);
    }
    clock_ns+=NS;frame(i++,0);assert(immutable_calls==5 && immutable_current==1);
    receipt_has(serial++,"\"result\":\"applied\"");
    send(serial++,"immutable_spans off");frame(i++,0);assert(!immutable_current);
    const int failures[]={-1,-3,0,2};
    for(unsigned j=0;j<sizeof failures/sizeof failures[0];++j) {
        immutable_force=failures[j];send(serial,"immutable_spans on");frame(i++,0);
        assert(!immutable_current);
        receipt_has(serial,j==0?"\"result\":\"rejected_mode\"":j==1?"\"result\":\"drain_failed\"":"\"result\":\"receipt_mismatch\"");
        receipt_has(serial++,"\"mode\":\"off\",\"flags\":0");
    }
    immutable_force=INT_MIN;immutable_bad_flags=true;
    send(serial,"immutable_spans on");frame(i++,0);
    receipt_has(serial,"\"result\":\"receipt_mismatch\"");receipt_has(serial++,"\"mode\":\"\",\"flags\":-1");
    immutable_bad_flags=false;
    unsigned calls_before=immutable_calls,status_before=immutable_status_calls;
    for(unsigned j=0;j<100;++j){clock_ns+=NS;frame(i++,0);}
    assert(immutable_calls==calls_before && immutable_status_calls==status_before);
    assert(preparation_current==prep_before && preparation_calls==prep_calls_before);
    *serial_ptr=serial;*frame_ptr=i;
    puts("r22 actual observer: off/on applied readback, cost, invalid/menu/failed-present/represented/frame0 rejection, replay, runtime mismatch, no settling/measurement polling or switching, and independent preparation state passed");
}
