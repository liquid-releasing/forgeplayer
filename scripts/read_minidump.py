# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Read a ForgePlayer minidump without WinDbg (Windows dev tool).

Companion to `crash_watch.py`, which writes the dumps. There is no debugger or
symbol server on this machine, and `pip install minidump` needs network — but
the minidump format is plain structs, and the two questions worth asking of a
crash dump here need no symbols at all:

  1. Which module was executing when it faulted? (`python313.dll+0x3a1a25`
     means the interpreter itself; `mpv-2.dll+…` means the player.)
  2. What is on that thread's stack? Return addresses left on the stack still
     resolve to modules, so even without symbols the chain says whether the
     thread came from mpv's event loop, Qt's event loop, PortAudio's callback,
     or a plain Python thread — which is the thing that decides where to look.

Usage:
    python scripts/read_minidump.py [dump.dmp] [--tid 52792] [--frames 40]

With no path it reads the newest dump in ~/.forgeplayer/crashdumps.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

STREAM_THREAD_LIST = 3
STREAM_MODULE_LIST = 4
STREAM_EXCEPTION = 6
STREAM_SYSTEM_INFO = 7

MODULE_ENTRY_SIZE = 108
THREAD_ENTRY_SIZE = 48


class Dump:
    def __init__(self, path: Path) -> None:
        self.data = path.read_bytes()
        sig, _ver, n_streams, dir_rva = struct.unpack_from("<4sIII", self.data, 0)
        if sig != b"MDMP":
            raise SystemExit(f"{path} is not a minidump (signature {sig!r})")
        self.streams: dict[int, tuple[int, int]] = {}
        for i in range(n_streams):
            stype, size, rva = struct.unpack_from(
                "<III", self.data, dir_rva + i * 12,
            )
            self.streams[stype] = (size, rva)

    def string(self, rva: int) -> str:
        (length,) = struct.unpack_from("<I", self.data, rva)
        raw = self.data[rva + 4: rva + 4 + length]
        return raw.decode("utf-16-le", errors="replace")

    # ── streams ──────────────────────────────────────────────────────────────

    def modules(self) -> list[tuple[int, int, str]]:
        """[(base, end, name)] sorted by base."""
        if STREAM_MODULE_LIST not in self.streams:
            return []
        _size, rva = self.streams[STREAM_MODULE_LIST]
        (count,) = struct.unpack_from("<I", self.data, rva)
        out = []
        for i in range(count):
            off = rva + 4 + i * MODULE_ENTRY_SIZE
            base, size_of_image, _csum, _ts, name_rva = struct.unpack_from(
                "<QIIII", self.data, off,
            )
            out.append((base, base + size_of_image, Path(self.string(name_rva)).name))
        return sorted(out)

    def threads(self) -> list[dict]:
        if STREAM_THREAD_LIST not in self.streams:
            return []
        _size, rva = self.streams[STREAM_THREAD_LIST]
        (count,) = struct.unpack_from("<I", self.data, rva)
        out = []
        for i in range(count):
            off = rva + 4 + i * THREAD_ENTRY_SIZE
            (tid, _susp, _pcls, _prio, _teb, stack_start,
             stack_size, stack_rva, ctx_size, ctx_rva) = struct.unpack_from(
                "<IIIIQQIIII", self.data, off,
            )
            out.append({
                "tid": tid, "stack_start": stack_start,
                "stack_size": stack_size, "stack_rva": stack_rva,
                "ctx_size": ctx_size, "ctx_rva": ctx_rva,
            })
        return out

    def exception(self) -> dict | None:
        if STREAM_EXCEPTION not in self.streams:
            return None
        _size, rva = self.streams[STREAM_EXCEPTION]
        tid, _align, code, flags, _rec, address = struct.unpack_from(
            "<IIIIQQ", self.data, rva,
        )
        return {
            "tid": tid, "code": code & 0xFFFFFFFF,
            "flags": flags, "address": address,
        }


def attribute(addr: int, modules: list[tuple[int, int, str]]) -> str | None:
    for base, end, name in modules:
        if base <= addr < end:
            return f"{name}+0x{addr - base:x}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dump", nargs="?", default=None)
    ap.add_argument("--tid", type=int, default=None, help="thread to walk")
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--list-threads", action="store_true")
    args = ap.parse_args()

    if args.dump:
        path = Path(args.dump)
    else:
        crashdir = Path.home() / ".forgeplayer" / "crashdumps"
        dumps = sorted(crashdir.glob("*.dmp"), key=lambda p: p.stat().st_mtime)
        if not dumps:
            print(f"no dumps in {crashdir}")
            return 1
        path = dumps[-1]

    dump = Dump(path)
    modules = dump.modules()
    threads = dump.threads()
    print(f"{path.name}: {len(modules)} modules, {len(threads)} threads")

    exc = dump.exception()
    tid = args.tid
    if exc:
        where = attribute(exc["address"], modules) or "<unknown module>"
        print(
            f"exception 0x{exc['code']:08X} at 0x{exc['address']:016x} "
            f"-> {where}  (tid {exc['tid']})"
        )
        tid = tid or exc["tid"]

    if tid is None:
        # No exception stream (a debugger-written dump has none) — crash_watch
        # leaves the tid/code/address in a sidecar next to the dump.
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            fields = dict(
                line.split("=", 1)
                for line in sidecar.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )
            print("from sidecar: " + ", ".join(
                f"{k}={v}" for k, v in fields.items()
            ))
            if "tid" in fields:
                tid = int(fields["tid"])

    if args.list_threads:
        for t in threads:
            print(f"  tid {t['tid']:>7}  stack {t['stack_size'] // 1024:>5} KB")
        return 0

    if tid is None:
        print("no exception stream and no --tid given; use --list-threads")
        return 1

    target = next((t for t in threads if t["tid"] == tid), None)
    if target is None:
        print(f"tid {tid} not in dump; use --list-threads")
        return 1

    # Walk the raw stack for values that land inside a loaded module. Without
    # symbols this over-reports (stale return addresses, function pointers),
    # but the SEQUENCE of modules is what matters — it shows which subsystem
    # the thread belongs to.
    raw = dump.data[target["stack_rva"]: target["stack_rva"] + target["stack_size"]]
    print(f"\nstack of tid {tid} ({len(raw) // 1024} KB), module hits, top first:")
    hits = 0
    seen_run: str | None = None
    for off in range(0, len(raw) - 8, 8):
        (value,) = struct.unpack_from("<Q", raw, off)
        if value < 0x10000:
            continue
        name = attribute(value, modules)
        if not name:
            continue
        module = name.split("+")[0]
        # Collapse long runs of the same module so one busy frame doesn't
        # bury the transition that actually tells the story.
        if module == seen_run:
            continue
        seen_run = module
        addr = target["stack_start"] + off
        print(f"  0x{addr:016x}  {name}")
        hits += 1
        if hits >= args.frames:
            print("  … (truncated; raise --frames for more)")
            break
    if not hits:
        print("  (no module addresses on this stack — thread was likely idle)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
