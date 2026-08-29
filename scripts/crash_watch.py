# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Out-of-process crash watcher for ForgePlayer (Windows, dev tool).

Why this exists: every native crash so far has been diagnosed — badly — from
`~/.forgeplayer/faulthandler.log`, and that file keeps failing us. CPython's
faulthandler dumps every thread on *every* first-chance Windows exception with
the error bit set, and libmpv raises a benign one (`0xe24c4a02`) constantly:
39 of them per 40 thumbnail grabs, hundreds across a dogfood session. When a
real access violation lands while another thread is mid-dump, the two writes
interleave and the real stack is truncated — three crashes on 2026-08-29 all
ended `Windows fatal exception: access violation` with no `Current thread`
marker and no usable frame.

An in-process handler can't fix that: it's writing from inside the process that
is falling over. So attach as a real debugger instead. The OS reports every
exception to us out-of-process, with an exception code and a faulting address,
and nothing the crashing process does can truncate it.

What it reports on a fatal exception:
  - the exception code (access violation, stack overflow, …) and address
  - **which module owns that address** — mpv-2.dll vs Qt6Gui.dll vs
    _multiarray_umath (numpy) vs python3xx.dll. That alone decides where to
    look next, and it needs no symbols.
  - a minidump written next to the log, for later inspection with real tools

Usage (leave running while you dogfood):

    python scripts/crash_watch.py                 # find ForgePlayer.exe by name
    python scripts/crash_watch.py --pid 1234
    python scripts/crash_watch.py --exe python.exe   # dev run from source

Benign first-chance noise is counted, not printed. The watched process is NOT
killed when this exits (DebugSetProcessKillOnExit(False)), so Ctrl-C here is
always safe.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

if sys.platform != "win32":  # pragma: no cover - dev tool, Windows only
    raise SystemExit("crash_watch is Windows-only")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

# Explicit argtypes: a 64-bit module base arrives as a Python int wider than
# ctypes' default int marshalling, and the call fails with OverflowError.
psapi.EnumProcessModulesEx.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
]
psapi.EnumProcessModulesEx.restype = wintypes.BOOL
psapi.GetModuleFileNameExW.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD,
]
psapi.GetModuleFileNameExW.restype = wintypes.DWORD
psapi.GetModuleInformation.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
]
psapi.GetModuleInformation.restype = wintypes.BOOL
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE

# ── Win32 constants ──────────────────────────────────────────────────────────

EXCEPTION_DEBUG_EVENT = 1
CREATE_PROCESS_DEBUG_EVENT = 3
EXIT_PROCESS_DEBUG_EVENT = 5
OUTPUT_DEBUG_STRING_EVENT = 8

DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001

# Codes worth stopping the world for. Everything else is noise we count.
FATAL_CODES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000006: "IN_PAGE_ERROR",
    0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
    0xC0000409: "STACK_BUFFER_OVERRUN",
    0xC0000374: "HEAP_CORRUPTION",
}
# Breakpoints belong to the debugger, not the app: attaching injects one, and
# it MUST be continued as handled. Passing it back as unhandled kills the very
# process we are trying to watch (caught in validation, 2026-08-29).
DEBUGGER_CODES = {0x80000003, 0x80000004, 0x4000001F, 0x4000001E}
# libmpv's constant first-chance chatter — the reason faulthandler.log is
# unusable. Counted so we can say how much of it there was, never printed.
KNOWN_NOISE = {0xE24C4A02, 0x406D1388}

MINIDUMP_WITH_DATA_SEGS = 0x00000001
MINIDUMP_WITH_HANDLE_DATA = 0x00000004
MINIDUMP_WITH_THREAD_INFO = 0x00001000
MINIDUMP_WITH_UNLOADED_MODULES = 0x00000020


# ── Structures ───────────────────────────────────────────────────────────────

class EXCEPTION_RECORD(ctypes.Structure):
    pass


EXCEPTION_RECORD._fields_ = [
    ("ExceptionCode", wintypes.DWORD),
    ("ExceptionFlags", wintypes.DWORD),
    ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)),
    ("ExceptionAddress", ctypes.c_void_p),
    ("NumberParameters", wintypes.DWORD),
    ("__unusedAlignment", wintypes.DWORD),
    ("ExceptionInformation", ctypes.c_void_p * 15),
]


class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("ExceptionRecord", EXCEPTION_RECORD),
        ("dwFirstChance", wintypes.DWORD),
    ]


class CREATE_PROCESS_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("hFile", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("lpBaseOfImage", ctypes.c_void_p),
        ("dwDebugInfoFileOffset", wintypes.DWORD),
        ("nDebugInfoSize", wintypes.DWORD),
        ("lpThreadLocalBase", ctypes.c_void_p),
        ("lpStartAddress", ctypes.c_void_p),
        ("lpImageName", ctypes.c_void_p),
        ("fUnicode", wintypes.WORD),
    ]


class DEBUG_EVENT_UNION(ctypes.Union):
    _fields_ = [
        ("Exception", EXCEPTION_DEBUG_INFO),
        ("CreateProcessInfo", CREATE_PROCESS_DEBUG_INFO),
        ("_pad", ctypes.c_ubyte * 200),
    ]


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [
        ("dwDebugEventCode", wintypes.DWORD),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
        ("u", DEBUG_EVENT_UNION),
    ]


class MINIDUMP_EXCEPTION_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("ThreadId", wintypes.DWORD),
        ("ExceptionPointers", ctypes.c_void_p),
        ("ClientPointers", wintypes.BOOL),
    ]


class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]


# ── Module attribution ───────────────────────────────────────────────────────

def module_map(h_process) -> list[tuple[int, int, str]]:
    """[(base, end, name)] for every module currently loaded in the target."""
    needed = wintypes.DWORD()
    count = 4096
    arr = (ctypes.c_void_p * count)()
    if not psapi.EnumProcessModulesEx(
        h_process, ctypes.cast(arr, ctypes.POINTER(ctypes.c_void_p)),
        ctypes.sizeof(arr), ctypes.byref(needed), 0x03,  # LIST_MODULES_ALL
    ):
        return []
    out: list[tuple[int, int, str]] = []
    for i in range(min(count, needed.value // ctypes.sizeof(ctypes.c_void_p))):
        base = arr[i]
        if not base:
            continue
        name = ctypes.create_unicode_buffer(1024)
        psapi.GetModuleFileNameExW(
            h_process, ctypes.c_void_p(base), name, 1024,
        )
        info = MODULEINFO()
        if psapi.GetModuleInformation(
            h_process, ctypes.c_void_p(base), ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            out.append((int(base), int(base) + info.SizeOfImage, name.value))
    return sorted(out)


def attribute(address: int, modules: list[tuple[int, int, str]]) -> str:
    for base, end, name in modules:
        if base <= address < end:
            return f"{Path(name).name}+0x{address - base:x}"
    return "<unknown module>"


# ── Minidump ─────────────────────────────────────────────────────────────────

def write_minidump(h_process, pid, thread_id, out_dir: Path) -> Path | None:
    dbghelp = ctypes.WinDLL("dbghelp")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"forgeplayer-crash-{stamp}.dmp"
    handle = kernel32.CreateFileW(
        str(path), 0x40000000, 0, None, 2, 0x80, None,  # GENERIC_WRITE, CREATE_ALWAYS
    )
    if handle == -1:
        return None
    try:
        # ExceptionPointers=None: the dump still carries every thread's stack
        # and the full module list, which is what attribution needs. Passing a
        # debuggee-side EXCEPTION_POINTERS would need ClientPointers=TRUE and
        # buys us only the pre-formatted exception record we already print.
        ok = dbghelp.MiniDumpWriteDump(
            h_process, pid, handle,
            MINIDUMP_WITH_DATA_SEGS | MINIDUMP_WITH_HANDLE_DATA
            | MINIDUMP_WITH_THREAD_INFO | MINIDUMP_WITH_UNLOADED_MODULES,
            None, None, None,
        )
        return path if ok else None
    finally:
        kernel32.CloseHandle(handle)


# ── Target discovery ─────────────────────────────────────────────────────────

def find_pid(exe_name: str) -> int | None:
    import subprocess
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH", "/FO", "CSV"],
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        parts = [p.strip('" ') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == exe_name.lower():
            return int(parts[1])
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--exe", default="ForgePlayer.exe")
    ap.add_argument(
        "--out", default=str(Path.home() / ".forgeplayer" / "crashdumps"),
    )
    args = ap.parse_args()

    pid = args.pid or find_pid(args.exe)
    if not pid:
        print(f"no running {args.exe} found", flush=True)
        return 1

    if not kernel32.DebugActiveProcess(pid):
        err = ctypes.get_last_error()
        print(f"DebugActiveProcess({pid}) failed: {err}", flush=True)
        return 1
    # Detaching (or dying) must never take the app down with us.
    kernel32.DebugSetProcessKillOnExit(False)
    print(f"watching pid {pid} ({args.exe}) — dumps to {args.out}", flush=True)

    out_dir = Path(args.out)
    h_process = None
    modules: list[tuple[int, int, str]] = []
    noise = 0
    started = time.time()

    evt = DEBUG_EVENT()
    try:
        while True:
            if not kernel32.WaitForDebugEvent(ctypes.byref(evt), 1000):
                continue
            code = evt.dwDebugEventCode
            status = DBG_CONTINUE

            if code == CREATE_PROCESS_DEBUG_EVENT:
                h_process = evt.u.CreateProcessInfo.hProcess
                modules = module_map(h_process)
                print(f"attached, {len(modules)} modules loaded", flush=True)

            elif code == EXIT_PROCESS_DEBUG_EVENT:
                print(
                    f"process exited after {time.time() - started:.0f}s "
                    f"({noise} benign first-chance exceptions suppressed)",
                    flush=True,
                )
                kernel32.ContinueDebugEvent(
                    evt.dwProcessId, evt.dwThreadId, DBG_CONTINUE,
                )
                return 0

            elif code == EXCEPTION_DEBUG_EVENT:
                rec = evt.u.Exception.ExceptionRecord
                exc = rec.ExceptionCode & 0xFFFFFFFF
                first = bool(evt.u.Exception.dwFirstChance)
                addr = int(rec.ExceptionAddress or 0)

                if exc in DEBUGGER_CODES:
                    status = DBG_CONTINUE
                elif exc in KNOWN_NOISE:
                    noise += 1
                    status = DBG_EXCEPTION_NOT_HANDLED
                elif exc in FATAL_CODES:
                    # Refresh the map: DLLs load as the app runs.
                    if h_process:
                        modules = module_map(h_process)
                    where = attribute(addr, modules)
                    chance = "first" if first else "SECOND (fatal)"
                    print(
                        f"\n=== {FATAL_CODES[exc]} 0x{exc:08X} "
                        f"[{chance} chance] tid={evt.dwThreadId}\n"
                        f"    at 0x{addr:016x}  ->  {where}",
                        flush=True,
                    )
                    if not first and h_process:
                        dump = write_minidump(
                            h_process, pid, evt.dwThreadId, out_dir,
                        )
                        print(f"    minidump: {dump}", flush=True)
                    status = DBG_EXCEPTION_NOT_HANDLED
                else:
                    noise += 1
                    status = DBG_EXCEPTION_NOT_HANDLED

            elif code == OUTPUT_DEBUG_STRING_EVENT:
                status = DBG_CONTINUE

            kernel32.ContinueDebugEvent(
                evt.dwProcessId, evt.dwThreadId, status,
            )
    except KeyboardInterrupt:
        print("detaching", flush=True)
        kernel32.DebugActiveProcessStop(pid)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
