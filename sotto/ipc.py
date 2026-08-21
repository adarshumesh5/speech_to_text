"""Inter-process commands for the single-instance app.

Jump-list items and future launchers run ``Grogu.exe --dictate`` etc. When
another instance starts, it connects to the running instance's named pipe,
writes the command, and exits. The running instance executes it on the GUI
thread via a queue polled by a QTimer.

Pipe: ``\\\\.\\pipe\\Grogu-Commands`` — one-line JSON payloads.
"""

from __future__ import annotations

import ctypes
import json
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

PIPE_NAME = r"\\.\pipe\Grogu-Commands"

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
NMPWAIT_USE_DEFAULT_WAIT = 0x00000000
ERROR_PIPE_BUSY = 231
ERROR_PIPE_CONNECTED = 535
ERROR_PIPE_LISTENING = 536
INVALID_HANDLE_VALUE = -1

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


INVALID_HANDLE = 0xFFFFFFFFFFFFFFFF  # INVALID_HANDLE_VALUE as c_void_p value


def _is_invalid_handle(handle) -> bool:
    """True when a HANDLE-typed result is INVALID_HANDLE_VALUE.

    On this Python/ctypes, HANDLE restype results may be c_void_p (wrapping -1
    as 0xFFFFFFFFFFFFFFFF unsigned) or a plain int -1 — accept both.
    """
    value = getattr(handle, "value", handle)
    return not value or value in (-1, INVALID_HANDLE)
kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.ConnectNamedPipe.restype = wintypes.BOOL
kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
kernel32.DisconnectNamedPipe.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.ReadFile.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.HANDLE]
kernel32.CreateFileW.restype = wintypes.HANDLE


class CommandServer:
    """Listens on the pipe in a background thread; queues commands."""

    def __init__(self, on_command):
        self._on_command = on_command
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="sotto-ipc",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # The server thread blocks in ConnectNamedPipe; closing its handle from
        # here would hang (CloseHandle waits on the in-flight operation), so we
        # open a dummy client connection instead — that unblocks the wait and
        # the thread observes the stop flag on its next loop iteration.
        def wake() -> None:
            for _ in range(20):
                if _open_wakeup_connection():
                    return
                time.sleep(0.05)

        threading.Thread(target=wake, daemon=True).start()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            handle = kernel32.CreateNamedPipeW(
                PIPE_NAME,
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                1, 4096, 4096, 0, None,
            )
            if _is_invalid_handle(handle):
                # e.g. ERROR_PIPE_BUSY while another instance settles — retry
                log.warning("CreateNamedPipe failed: %s", ctypes.get_last_error())
                time.sleep(0.1)
                continue
            if self._stop.is_set():
                kernel32.CloseHandle(handle)
                return
            connected = kernel32.ConnectNamedPipe(handle, None)
            if not connected and ctypes.get_last_error() != ERROR_PIPE_CONNECTED:
                kernel32.CloseHandle(handle)
                continue
            data = b""
            while True:
                buf = ctypes.create_string_buffer(4096)
                read = wintypes.DWORD(0)
                ok = kernel32.ReadFile(handle, buf, 4096, ctypes.byref(read), None)
                if not ok or read.value == 0:
                    break
                data += buf.raw[: read.value]
                if len(data) >= 4096 or b"\n" in data:
                    break
            kernel32.DisconnectNamedPipe(handle)
            kernel32.CloseHandle(handle)
            if data.strip():
                try:
                    payload = json.loads(data.decode("utf-8"))
                except ValueError:
                    payload = {"command": data.decode("utf-8", "replace").strip()}
                try:
                    self._on_command(payload)
                except Exception:  # noqa: BLE001
                    log.exception("command handler failed")


def _open_wakeup_connection() -> bool:
    """Connect to the pipe and immediately close — unblocks the server."""
    handle = kernel32.CreateFileW(
        PIPE_NAME, 0xC0000000, 0, None, 3, 0, None,
    )
    if _is_invalid_handle(handle):
        return False
    kernel32.CloseHandle(handle)
    return True


def send_command(command: str, **extra) -> bool:
    """Deliver a command to the running instance. Returns False if none."""
    payload = json.dumps({"command": command, **extra})
    handle = kernel32.CreateFileW(
        PIPE_NAME, 0xC0000000, 0, None, 3, 0, None,
    )
    if _is_invalid_handle(handle):
        return False
    try:
        data = (payload + "\n").encode("utf-8")
        written = wintypes.DWORD(0)
        buf = ctypes.create_string_buffer(data)
        kernel32.WriteFile(handle, buf, len(data), ctypes.byref(written), None)
    finally:
        kernel32.CloseHandle(handle)
    return True
