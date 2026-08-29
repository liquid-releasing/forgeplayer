"""Native OS file/folder dialogs that survive in-process libmpv.

Why this exists: ForgePlayer runs libmpv **in-process**. Once a scene is
playing, opening a Qt dialog on the GUI thread during playback either
(a) silently falls back to Qt's dated non-native dialog — no Quick Access, no
drive navigation — because the GUI thread's COM apartment is no longer a clean
STA, or (b) hangs hard enough to force a kill (title bar reads "Not
Responding"), because the native dialog's modal message pump re-enters while
libmpv delivers queued events on the same thread.

Fix: on Windows, run the real Explorer dialog on a dedicated worker thread that
initialises its **own** single-threaded COM apartment. The worker owns the modal
pump, so the GUI thread never dispatches messages inside it and there's no
re-entrancy. That guarantees the modern Explorer chrome regardless of what
libmpv did to the main thread, and it can't deadlock against the Qt event loop.
libmpv's own threads keep the video playing throughout.

Meanwhile the GUI thread keeps running its own event loop (`qt_modal_waiter`)
rather than blocking in `join()` — a blocked GUI thread stops repainting, and
Windows greys the window and appends "(Not Responding)" to the title bar after a
few seconds, which users correctly report as a freeze even though the dialog is
working fine.

Three dialogs live here, and **every** picker in the app routes through one of
them — a picker that still calls `QFileDialog` directly on the GUI thread has
both bugs back:

- `native_open_file`  — `GetOpenFileNameW` (comdlg32)
- `native_save_file`  — `GetSaveFileNameW` (comdlg32)
- `native_pick_folder` — `IFileOpenDialog` + `FOS_PICKFOLDERS` (the modern
  shell dialog; the legacy `SHBrowseForFolder` tree is the ugly chrome users
  recognise as "the old selector", so it is deliberately not used)

Non-Windows raises `NativeDialogUnavailable` so the caller falls back to
`QFileDialog` (native there already, no in-process-mpv apartment problem).
"""
from __future__ import annotations

import sys
import threading
from typing import Callable, Optional, TypeVar


class NativeDialogUnavailable(RuntimeError):
    """Raised when the native path can't run — caller should use QFileDialog."""


T = TypeVar("T")


Waiter = Callable[[threading.Thread], None]


def qt_modal_waiter(widget=None) -> Waiter:
    """Waiter that keeps the Qt event loop alive while the dialog is open.

    Without this the GUI thread sits in `join()` and stops pumping messages, so
    Windows greys the control window out and stamps "(Not Responding)" on the
    title bar for as long as the user browses — the app is fine, but it reads as
    a hang, which is the bug users actually report.

    The worker thread still owns the dialog's modal pump (that's what keeps it
    off the GUI thread's dirtied COM apartment); the GUI thread just runs its own
    normal event loop, repainting and keeping mpv's queued events flowing.
    Input to *widget*'s window is blocked meanwhile so the dialog behaves modally
    — the native dialog is deliberately owner-less, so nothing else enforces it.
    """
    def _wait(thread: threading.Thread) -> None:
        from PySide6.QtCore import QEventLoop, QTimer  # noqa: PLC0415

        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(30)

        def _poll() -> None:
            if not thread.is_alive():
                loop.quit()

        timer.timeout.connect(_poll)
        timer.start()
        top = widget.window() if widget is not None else None
        if top is not None:
            top.setEnabled(False)
        try:
            loop.exec()
        finally:
            timer.stop()
            if top is not None:
                top.setEnabled(True)

    return _wait


def _run_on_sta(work: Callable[[], T], waiter: Optional[Waiter] = None) -> T:
    """Run *work* on a dedicated thread that owns its own STA apartment.

    The worker owns the dialog's modal pump, so the GUI thread never dispatches
    messages inside it — that re-entrancy is what deadlocked against libmpv's
    event delivery. Callers pass `qt_modal_waiter(self)` so the GUI thread spends
    the wait running its own event loop instead of blocking; without a waiter it
    simply `join()`s (fine for tests and non-GUI callers). Any exception from the
    worker surfaces here as `NativeDialogUnavailable` so callers have exactly one
    failure mode to catch.
    """
    if sys.platform != "win32":
        raise NativeDialogUnavailable("native dialogs only implemented on Windows")

    box: dict = {}

    def _worker() -> None:
        try:
            box["value"] = work()
        except Exception as exc:  # noqa: BLE001 — reported to caller below
            box["error"] = exc

    t = threading.Thread(target=_worker, name="native-file-dialog", daemon=True)
    t.start()
    if waiter is not None:
        waiter(t)
    t.join()

    if "error" in box:
        raise NativeDialogUnavailable(str(box["error"]))
    return box["value"]


def native_open_file(
    title: str,
    start_dir: str,
    filters: list[tuple[str, str]],
    waiter: Optional[Waiter] = None,
) -> Optional[str]:
    """Show the OS file-open dialog and return the chosen path (or None if the
    user cancelled). `filters` is a list of ``(label, pattern)`` where pattern is
    a Win32 semicolon-separated glob, e.g. ``("Video files", "*.mp4;*.mkv")``.

    Raises `NativeDialogUnavailable` on non-Windows or any Win32/ctypes error so
    the caller can fall back to a Qt dialog.
    """
    return _run_on_sta(
        lambda: _win_file_dialog(title, start_dir, filters, save=False), waiter,
    )


def native_save_file(
    title: str,
    start_dir: str,
    filters: list[tuple[str, str]],
    default_name: str = "",
    default_ext: str = "",
    waiter: Optional[Waiter] = None,
) -> Optional[str]:
    """Show the OS file-save dialog and return the chosen path (or None if the
    user cancelled). `default_name` pre-fills the filename box; `default_ext` is
    appended by the shell when the user types a name without one (no leading
    dot). Overwrite confirmation is handled by the dialog.
    """
    return _run_on_sta(
        lambda: _win_file_dialog(
            title, start_dir, filters,
            save=True, default_name=default_name, default_ext=default_ext,
        ),
        waiter,
    )


def native_pick_folder(
    title: str, start_dir: str, waiter: Optional[Waiter] = None,
) -> Optional[str]:
    """Show the OS folder picker (Quick Access, This PC, drive navigation) and
    return the chosen folder (or None if the user cancelled).
    """
    return _run_on_sta(lambda: _win_pick_folder(title, start_dir), waiter)


# ── Win32 implementations (worker thread only) ───────────────────────────────


def _win_file_dialog(
    title: str,
    start_dir: str,
    filters: list[tuple[str, str]],
    *,
    save: bool,
    default_name: str = "",
    default_ext: str = "",
) -> Optional[str]:
    """`GetOpenFileNameW` / `GetSaveFileNameW`. Runs on the STA worker only."""
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
        # Writable output buffer for the chosen path — pre-filled with the
        # suggested filename on save, which is what the shell shows in the box.
        path_buf = ctypes.create_unicode_buffer(default_name, 2048)

        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = 0  # no owner — the GUI thread is parked in join(), so an
        #                    owned dialog whose owner never pumps could misbehave.
        ofn.lpstrFilter = ctypes.cast(filt_buf, wintypes.LPCWSTR)
        ofn.lpstrFile = ctypes.cast(path_buf, wintypes.LPWSTR)
        ofn.nMaxFile = 2048
        ofn.lpstrInitialDir = start_dir or None
        ofn.lpstrTitle = title
        ofn.lpstrDefExt = default_ext or None
        # OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR
        ofn.Flags = 0x00080000 | 0x00000800 | 0x00000008
        if save:
            ofn.Flags |= 0x00000002  # OFN_OVERWRITEPROMPT
        else:
            ofn.Flags |= 0x00001000  # OFN_FILEMUSTEXIST

        show = comdlg32.GetSaveFileNameW if save else comdlg32.GetOpenFileNameW
        if not show(ctypes.byref(ofn)):
            return None  # user cancelled (or dialog error → treat as cancel)
        return path_buf.value or None
    finally:
        if initialised:
            ole32.CoUninitialize()


def _win_pick_folder(title: str, start_dir: str) -> Optional[str]:
    """`IFileOpenDialog` in folder-pick mode. Runs on the STA worker only.

    Called through raw ctypes vtable dispatch — no comtypes/pywin32 dependency,
    matching the rest of this module. Vtable indices come from the COM interface
    declaration order in ShObjIdl_core.h, which is ABI-frozen.
    """
    import ctypes
    from ctypes import wintypes

    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(text: str) -> GUID:
        g = GUID()
        if ole32.CLSIDFromString(text, ctypes.byref(g)) != 0:
            raise OSError(f"CLSIDFromString failed for {text}")
        return g

    def call(ptr, index: int, *args, argtypes=()):
        """Invoke method *index* on the COM object at *ptr* via its vtable."""
        vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p)).contents.value
        fn_addr = ctypes.cast(
            vtable, ctypes.POINTER(ctypes.c_void_p)
        )[index]
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
        return proto(fn_addr)(ptr, *args)

    def release(ptr) -> None:
        if ptr:
            call(ptr, 2)  # IUnknown::Release

    CLSID_FileOpenDialog = "{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}"
    IID_IFileOpenDialog = "{d57c7288-d4ad-4768-be02-9d969532d960}"
    IID_IShellItem = "{43826d1e-e718-42ee-bc55-a1e261c37bfe}"

    # IFileDialog vtable (after IUnknown's 0-2): Show=3 … SetOptions=9,
    # GetOptions=10, SetFolder=12, SetTitle=17, GetResult=20.
    IDX_SHOW, IDX_SET_OPTIONS, IDX_GET_OPTIONS = 3, 9, 10
    IDX_SET_FOLDER, IDX_SET_TITLE, IDX_GET_RESULT = 12, 17, 20
    IDX_GET_DISPLAY_NAME = 5  # IShellItem::GetDisplayName

    FOS_NOCHANGEDIR = 0x00000008
    FOS_PICKFOLDERS = 0x00000020
    FOS_FORCEFILESYSTEM = 0x00000040   # refuse virtual (non-path) picks
    FOS_PATHMUSTEXIST = 0x00000800
    SIGDN_FILESYSPATH = 0x80058000
    # Show() returns this when the user cancels — a normal outcome, not an error.
    HRESULT_CANCELLED = -2147023673  # 0x800704C7 as a signed long

    hr = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    initialised = hr in (0, 1)
    dialog = ctypes.c_void_p()
    item = ctypes.c_void_p()
    try:
        clsid = guid(CLSID_FileOpenDialog)
        iid = guid(IID_IFileOpenDialog)
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None,
            0x1,  # CLSCTX_INPROC_SERVER
            ctypes.byref(iid), ctypes.byref(dialog),
        )
        if hr < 0 or not dialog:
            raise OSError(f"CoCreateInstance(FileOpenDialog) failed: {hr:#010x}")

        options = wintypes.DWORD()
        call(dialog, IDX_GET_OPTIONS, ctypes.byref(options),
             argtypes=(ctypes.POINTER(wintypes.DWORD),))
        options.value |= (
            FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM
            | FOS_PATHMUSTEXIST | FOS_NOCHANGEDIR
        )
        call(dialog, IDX_SET_OPTIONS, options,
             argtypes=(wintypes.DWORD,))

        if title:
            call(dialog, IDX_SET_TITLE, title, argtypes=(wintypes.LPCWSTR,))

        # Opening folder: best-effort. A stale/unreachable start dir must not
        # stop the dialog appearing — the shell just opens at its default.
        if start_dir:
            start_item = ctypes.c_void_p()
            item_iid = guid(IID_IShellItem)
            if shell32.SHCreateItemFromParsingName(
                wintypes.LPCWSTR(start_dir), None,
                ctypes.byref(item_iid), ctypes.byref(start_item),
            ) == 0 and start_item:
                call(dialog, IDX_SET_FOLDER, start_item,
                     argtypes=(ctypes.c_void_p,))
                release(start_item)

        hr = call(dialog, IDX_SHOW, None, argtypes=(wintypes.HWND,))
        if hr == HRESULT_CANCELLED:
            return None
        if hr < 0:
            raise OSError(f"IFileOpenDialog::Show failed: {hr & 0xFFFFFFFF:#010x}")

        hr = call(dialog, IDX_GET_RESULT, ctypes.byref(item),
                  argtypes=(ctypes.POINTER(ctypes.c_void_p),))
        if hr < 0 or not item:
            raise OSError(f"IFileOpenDialog::GetResult failed: {hr:#010x}")

        name = ctypes.c_wchar_p()
        hr = call(item, IDX_GET_DISPLAY_NAME,
                  SIGDN_FILESYSPATH, ctypes.byref(name),
                  argtypes=(wintypes.DWORD, ctypes.POINTER(ctypes.c_wchar_p)))
        if hr < 0 or not name.value:
            raise OSError(f"IShellItem::GetDisplayName failed: {hr:#010x}")
        try:
            return name.value or None
        finally:
            ole32.CoTaskMemFree(name)
    finally:
        release(item)
        release(dialog)
        if initialised:
            ole32.CoUninitialize()
