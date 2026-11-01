"""Win32 process containment/counters. All termination is scoped to our Job Object."""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import time

if os.name == 'nt':
    k = C.WinDLL('kernel32', use_last_error=True)
    ps = C.WinDLL('psapi', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([W.LPVOID, W.LPCWSTR], W.HANDLE),
        'OpenJobObjectW': ([W.DWORD, W.BOOL, W.LPCWSTR], W.HANDLE),
        'SetInformationJobObject': ([W.HANDLE, C.c_int, W.LPVOID, W.DWORD], W.BOOL),
        'QueryInformationJobObject': ([W.HANDLE, C.c_int, W.LPVOID, W.DWORD, W.LPVOID], W.BOOL),
        'AssignProcessToJobObject': ([W.HANDLE, W.HANDLE], W.BOOL),
        'TerminateJobObject': ([W.HANDLE, W.UINT], W.BOOL),
        'CloseHandle': ([W.HANDLE], W.BOOL),
        'OpenProcess': ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
        'GetProcessTimes': ([W.HANDLE, W.LPVOID, W.LPVOID, W.LPVOID, W.LPVOID], W.BOOL),
        'QueryFullProcessImageNameW': ([W.HANDLE, W.DWORD, W.LPWSTR, W.LPVOID], W.BOOL),
        'GetExitCodeProcess': ([W.HANDLE, W.LPVOID], W.BOOL),
        'GlobalMemoryStatusEx': ([W.LPVOID], W.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(k, name)
        fn.argtypes, fn.restype = args, result
    ps.GetProcessMemoryInfo.argtypes = [W.HANDLE, W.LPVOID, W.DWORD]
    ps.GetProcessMemoryInfo.restype = W.BOOL


def check(ok):
    if not ok:
        raise C.WinError(C.get_last_error())
    return ok


class BasicLimit(C.Structure):
    _fields_ = [('process_time', C.c_int64), ('job_time', C.c_int64), ('flags', W.DWORD),
                ('min_ws', C.c_size_t), ('max_ws', C.c_size_t), ('active_limit', W.DWORD),
                ('affinity', C.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]


class IOCounters(C.Structure):
    _fields_ = [(n, C.c_uint64) for n in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimit(C.Structure):
    _fields_ = [('basic', BasicLimit), ('io', IOCounters), ('process_mem', C.c_size_t),
                ('job_mem', C.c_size_t), ('peak_process_mem', C.c_size_t), ('peak_job_mem', C.c_size_t)]


class MemoryCounters(C.Structure):
    _fields_ = [('cb', W.DWORD), ('faults', W.DWORD)] + [(n, C.c_size_t) for n in
                ('peak_ws', 'ws', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]


class MemoryStatus(C.Structure):
    _fields_ = [('length', W.DWORD), ('load', W.DWORD)] + [(n, C.c_uint64) for n in
                ('total_ram', 'free_ram', 'commit_limit', 'free_commit', 'total_virtual', 'free_virtual', 'extended')]


def memory_status():
    s = MemoryStatus()
    s.length = C.sizeof(s)
    check(k.GlobalMemoryStatusEx(C.byref(s)))
    return {'memory_load_percent': s.load, 'free_ram_bytes': s.free_ram,
            'free_commit_bytes': s.free_commit, 'commit_limit_bytes': s.commit_limit}


def process_sample(pid):
    h = k.OpenProcess(0x1000 | 0x0010, False, pid)  # QUERY_LIMITED_INFORMATION | VM_READ
    if not h:
        return None
    try:
        creation, exit_time, kernel, user = (C.c_uint64() for _ in range(4))
        check(k.GetProcessTimes(h, C.byref(creation), C.byref(exit_time), C.byref(kernel), C.byref(user)))
        name = C.create_unicode_buffer(32768)
        length = W.DWORD(len(name))
        check(k.QueryFullProcessImageNameW(h, 0, name, C.byref(length)))
        mem = MemoryCounters()
        mem.cb = C.sizeof(mem)
        check(ps.GetProcessMemoryInfo(h, C.byref(mem), mem.cb))
        return {'pid': pid, 'created_filetime': creation.value, 'image': name.value,
                'cpu_seconds': (kernel.value + user.value) / 10000000,
                'private_bytes': mem.private, 'working_set_bytes': mem.ws,
                'exited': exit_time.value != 0}
    except OSError:
        return None
    finally:
        k.CloseHandle(h)


def identity():
    sample = process_sample(os.getpid())
    if not sample:
        raise RuntimeError('cannot establish worker process identity')
    return {n: sample[n] for n in ('pid', 'created_filetime')}


def identity_alive(record):
    # An exited process can remain queryable while its parent retains a handle.
    # Memory counters may already be unavailable; identity/liveness needs only times.
    h = k.OpenProcess(0x1000, False, record['pid'])
    if not h:
        error = C.get_last_error()
        if error in (87, 1168):
            return False
        raise C.WinError(error)
    try:
        created, ended, kernel, user = (C.c_uint64() for _ in range(4))
        check(k.GetProcessTimes(h, C.byref(created), C.byref(ended), C.byref(kernel), C.byref(user)))
        return created.value == record['created_filetime'] and ended.value == 0
    finally:
        k.CloseHandle(h)


class RuntimeWatch:
    """Retain handles so a crash just before planned termination cannot vanish with its PID."""
    def __init__(self, image_name='lasrecomp.exe'):
        self.image_name = image_name.lower()
        self.handles = {}
        self.warnings = []

    def observe(self, pids):
        for pid in pids:
            # Retained handles already preserve identity/exit codes. Querying the
            # image name again while that process exits can return Access Denied.
            if any(known_pid == pid for known_pid, _ in self.handles):
                continue
            h = k.OpenProcess(0x1000, False, pid)
            if not h:
                self.warnings.append({'pid': pid, 'operation': 'OpenProcess', 'winerror': C.get_last_error()})
                continue
            keep = False
            try:
                name = C.create_unicode_buffer(32768)
                length = W.DWORD(len(name))
                check(k.QueryFullProcessImageNameW(h, 0, name, C.byref(length)))
                if Path(name.value).name.lower() != self.image_name:
                    continue
                creation, end, kernel, user = (C.c_uint64() for _ in range(4))
                check(k.GetProcessTimes(h, C.byref(creation), C.byref(end), C.byref(kernel), C.byref(user)))
                key = (pid, creation.value)
                if key not in self.handles:
                    self.handles[key] = h
                    keep = True
            except OSError as exc:
                # Short-lived bridge/launcher processes may vanish during inspection.
                # This is diagnostic sampling; it must never prevent tree cleanup.
                self.warnings.append({'pid': pid, 'operation': 'inspect_process', 'winerror': exc.winerror})
            finally:
                if not keep:
                    k.CloseHandle(h)

    def exits(self):
        result = []
        for (pid, created), h in self.handles.items():
            creation, end, kernel, user = (C.c_uint64() for _ in range(4))
            check(k.GetProcessTimes(h, C.byref(creation), C.byref(end), C.byref(kernel), C.byref(user)))
            if end.value:
                code = W.DWORD()
                check(k.GetExitCodeProcess(h, C.byref(code)))
                result.append({'pid': pid, 'created_filetime': created, 'exit_code': code.value})
        return result

    def close(self):
        for h in self.handles.values():
            k.CloseHandle(h)
        self.handles.clear()


class Job:
    def __init__(self, name, existing=False):
        self.name = name
        if existing:
            self.handle = k.OpenJobObjectW(0x0004 | 0x0008, False, name)  # QUERY | TERMINATE
            if not self.handle:
                error = C.get_last_error()
                if error == 2:
                    return
                raise C.WinError(error)
        else:
            C.set_last_error(0)
            self.handle = check(k.CreateJobObjectW(None, name))
            if C.get_last_error() == 183:
                k.CloseHandle(self.handle)
                raise RuntimeError('execution Job Object already exists')
            limits = ExtendedLimit()
            limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            try:
                check(k.SetInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits)))
            except BaseException:
                self.close()
                raise

    def assign(self, process):
        check(k.AssignProcessToJobObject(self.handle, W.HANDLE(int(process._handle))))

    def pids(self):
        if not self.handle:
            return []
        class ProcessList(C.Structure):
            _fields_ = [('assigned', W.DWORD), ('count', W.DWORD), ('pids', C.c_size_t * 512)]
        rows = ProcessList()
        check(k.QueryInformationJobObject(self.handle, 3, C.byref(rows), C.sizeof(rows), None))
        if rows.count > 512:
            raise RuntimeError('unexpectedly large process tree')
        return list(rows.pids[:rows.count])

    def stop(self):
        if self.handle and self.pids():
            check(k.TerminateJobObject(self.handle, 1))
        deadline = time.monotonic() + 15
        while self.pids():
            if time.monotonic() >= deadline:
                raise RuntimeError('contained process tree did not stop; retain PC turn')
            time.sleep(0.05)
        return {'job_object': self.name, 'active_processes': 0, 'verified_at': time.time()}

    def close(self):
        if self.handle:
            check(k.CloseHandle(self.handle))
            self.handle = None
