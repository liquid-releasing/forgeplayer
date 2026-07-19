"""Native OS file-open dialog that survives in-process libmpv.

Why this exists: ForgePlayer runs libmpv **in-process**. Once a scene is
playing, opening a Qt file dialog on the GUI thread during playback either
(a) silently falls back to Qt's dated non-native dialog — no Quick Access, no
drive navigation — because the GUI thread's COM apartment is no longer a clean
STA, or (b) hangs hard enough to force a kill, because the native dialog's modal
message pump re-enters while libmpv delivers queued events on the same thread.

Fix: on Windows, run the classic Win32 Explorer dialog (`GetOpenFileNameW`) on a
dedicated worker thread that initialises its **own** single-threaded COM
apartment. The worker owns the modal pump; the GUI thread just `join()`s (a
GIL-releasing wait — it does not pump messages, so there's no re-entrancy). That
guarantees the modern Explorer chrome regardless of what libmpv did to the main
thread, and it can't deadlock against the Qt event loop. libmpv's own threads
keep the video playing throughout.

Non-Windows raises `NativeDialogUnavailable` so the caller falls back to
`QFileDialog` (native there already, no in-process-mpv apartment problem).
"""
from __future__ import annotations

import sys
import threading
from typing import Optional


class NativeDialogUnavailable(RuntimeError):
    """Raised when the native path can't run — caller should use QFileDialog."""


def native_open_file(
    title: str,
    start_dir: str,
    filters: list[tuple[str, str]],
) -> Optional[str]:
    """Show the OS file-open dialog and return the chosen path (or None if the
    user cancelled). `filters` is a list of ``(label, pattern)`` where pattern is
    a Win32 semicolon-separated glob, e.g. ``("Video files", "*.mp4;*.mkv")``.

    Raises `NativeDialogUnavailable` on non-Windows or any Win32/ctypes error so
    the caller can fall back to a Qt dialog.
    """
    if sys.platform != "win32":
        raise NativeDialogUnavailable("native dialog only implemented on Windows")

    box: dict = {}

    def _worker() -> None:
        try:
            box["path"] = _win_open_file(title, start_dir, filters)
        except Exception as exc:  # noqa: BLE001 — reported to caller below
            box["error"] = exc

    t = threading.Thread(target=_worker, name="native-file-dialog", daemon=True)
    t.start()
    t.join()

    if "error" in box:
        raise NativeDialogUnavailable(str(box["error"]))
    return box.get("path")


def _win_open_file(
    title: str,
    start_dir: str,
    filters: list[tuple[str, str]],
) -> Optional[str]:
    import ctypes
    from ctypes import wintypes

    ole32 = ctypes.windll.ole32
    comdlg32 = ctypes.windll.comdlg32

    # STA is what selects the modern Explorer-style dialog (Quick Access, drive
    # nav). S_OK (0) means we initialised it; S_FALSE (1) means already-STA on
    # this fresh thread (won't happen, but balance CoUninitialize either way).
    hr = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    initialised = hr in (0, 1)
    try:
        class OPENFILENAMEW(ctypes.Structure):
            _fields_ = [
                ("lStructSize", wintypes.DWORD),
                ("hwndOwner", wintypes.HWND),
                ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR),
                ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD),
                ("nFilterIndex", wintypes.DWORD),
                ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD),
                ("lpstrFileTitle", wintypes.LPWSTR),
                ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR),
                ("lpstrTitle", wintypes.LPCWSTR),
                ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD),
                ("nFileExtension", wintypes.WORD),
                ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", wintypes.LPARAM),
                ("lpfnHook", wintypes.LPVOID),
                ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", wintypes.LPVOID),
                ("dwReserved", wintypes.DWORD),
                ("FlagsEx", wintypes.DWORD),
            ]

        # The filter is a run of NUL-separated label/pattern pairs, terminated by
        # a double NUL. A plain Python str assigned to LPCWSTR would truncate at
        # the first embedded NUL, so build an explicit wide buffer (its own
        # terminating NUL supplies the closing double-NUL) and pass a pointer.
        filt = "".join(f"{label}\0{pattern}\0" for label, pattern in filters)
        filt_buf = ctypes.create_unicode_buffer(filt)
        # Writable output buffer for the chosen path.
        path_buf = ctypes.create_unicode_buffer(2048)

        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = 0  # no owner — the GUI thread is parked in join(), so an
        #                    owned dialog whose owner never pumps could misbehave.
        ofn.lpstrFilter = ctypes.cast(filt_buf, wintypes.LPCWSTR)
        ofn.lpstrFile = ctypes.cast(path_buf, wintypes.LPWSTR)
        ofn.nMaxFile = 2048
        ofn.lpstrInitialDir = start_dir or None
        ofn.lpstrTitle = title
        # OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR
        ofn.Flags = 0x00080000 | 0x00001000 | 0x00000800 | 0x00000008

        if not comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return None  # user cancelled (or dialog error → treat as cancel)
        return path_buf.value or None
    finally:
        if initialised:
            ole32.CoUninitialize()
