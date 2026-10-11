"""Linux child sandbox: no inherited credentials, network sockets or unlimited resources."""

import ctypes
import errno
import os
import resource
import signal
import sys


def sandbox():
    # Install before exec: seccomp and rlimits survive execve into ffmpeg/ffprobe.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise RuntimeError("Sandbox unavailable")
    parent = os.getppid()
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or parent == 1 or os.getppid() != parent:
        raise RuntimeError("Parent unavailable")
    sec = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not ctx:
        raise RuntimeError("Sandbox unavailable")
    try:
        for name in (b"socket", b"socketpair"):
            syscall = sec.seccomp_syscall_resolve_name(name)
            if syscall < 0 or sec.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, syscall, 0) != 0:
                raise RuntimeError("Sandbox unavailable")
        if sec.seccomp_load(ctx) != 0:
            raise RuntimeError("Sandbox unavailable")
    finally:
        sec.seccomp_release(ctx)
    for kind, value in (
        (resource.RLIMIT_AS, 1536 * 1024 * 1024),
        (resource.RLIMIT_CPU, 600),
        (resource.RLIMIT_FSIZE, 64 * 1024 * 1024),
        (resource.RLIMIT_NOFILE, 64),
        (resource.RLIMIT_CORE, 0),
    ):
        resource.setrlimit(kind, (value, value))


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"ffmpeg", "ffprobe", "network-test"}:
        raise SystemExit(2)
    sandbox()
    if sys.argv[1] == "network-test":
        import socket

        try:
            socket.socket()
        except PermissionError:
            print("network-blocked")
            return
        raise SystemExit("network-not-blocked")
    binary = "/usr/bin/" + sys.argv[1]
    os.execve(
        binary, [binary, *sys.argv[2:]], {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/tmp"}
    )


if __name__ == "__main__":
    main()
