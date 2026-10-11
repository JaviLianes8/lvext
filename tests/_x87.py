"""Test-only oracle: run real x87 FPU instructions on Windows x86-64.

Each helper copies a few bytes of machine code into an executable page and calls
it through ctypes. The code loads the operand with the x87 rounding control set to
the requested mode (all exceptions masked, 64-bit precision), stores the result, and
restores the caller's control word. This lets the tests compare lvext with the
hardware bit for bit instead of with values written down by hand.
"""

from __future__ import annotations

import ctypes
import platform
import struct
import sys
from collections.abc import Callable

AVAILABLE = sys.platform == "win32" and platform.machine().upper() in ("AMD64", "X86_64")

# Windows x64 arguments: rcx, rdx, r8 (pointer to the control word), r9.
_PROLOGUE = bytes.fromhex("4883ec08d93c2441d928")  # sub rsp,8; fnstcw [rsp]; fldcw [r8]
_EPILOGUE = bytes.fromhex("d92c24dbe24883c408c3")  # fldcw [rsp]; fnclex; add; ret
_BODIES = {
    "load80_store64": bytes.fromhex("db29dd1a"),  # fld tword [rcx]; fstp qword [rdx]
    "load64_store80": bytes.fromhex("dd01db3a"),  # fld qword [rcx]; fstp tword [rdx]
    # fild qword [rcx]; fild qword [rdx]; fdivp st(1), st; fstp tword [r9]
    "divide_to80": bytes.fromhex("df29df2adef941db39"),
}
_RC = {"nearest-even": 0, "floor": 1, "ceiling": 2, "toward-zero": 3}

_Fn = Callable[[object, object, object, object], None]
_cache: dict[str, _Fn] = {}


def _function(name: str) -> _Fn:
    if name not in _cache:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.VirtualAlloc.restype = ctypes.c_void_p
        kernel32.VirtualAlloc.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        kernel32.VirtualProtect.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        code = _PROLOGUE + _BODIES[name] + _EPILOGUE
        page = kernel32.VirtualAlloc(None, 4096, 0x3000, 0x04)  # commit, read-write
        ctypes.memmove(page, code, len(code))
        old = wintypes.DWORD()
        if not kernel32.VirtualProtect(page, 4096, 0x20, ctypes.byref(old)):  # execute-read
            raise OSError(ctypes.get_last_error())
        prototype = ctypes.CFUNCTYPE(None, *([ctypes.c_void_p] * 4))
        _cache[name] = prototype(page)
    return _cache[name]


def _control_word(mode: str) -> ctypes.Array[ctypes.c_char]:
    return ctypes.create_string_buffer(struct.pack("<H", 0x037F | (_RC[mode] << 10)), 2)


def narrow(ext_big_endian: bytes, mode: str) -> bytes:
    """FLD an 80-bit value and FSTP it as a double; return big-endian double bytes."""
    src = ctypes.create_string_buffer(ext_big_endian[::-1], 10)
    dst = ctypes.create_string_buffer(8)
    _function("load80_store64")(src, dst, _control_word(mode), None)
    return dst.raw[::-1]


def widen(double_big_endian: bytes) -> bytes:
    """FLD a double and FSTP it as an 80-bit value; return big-endian bytes."""
    src = ctypes.create_string_buffer(double_big_endian[::-1], 8)
    dst = ctypes.create_string_buffer(10)
    _function("load64_store80")(src, dst, _control_word("nearest-even"), None)
    return dst.raw[::-1]


def divide(numerator: int, denominator: int, mode: str) -> bytes:
    """Divide two int64 values on the FPU; return the 80-bit quotient, big-endian."""
    a = ctypes.create_string_buffer(struct.pack("<q", numerator), 8)
    b = ctypes.create_string_buffer(struct.pack("<q", denominator), 8)
    dst = ctypes.create_string_buffer(10)
    _function("divide_to80")(a, b, _control_word(mode), dst)
    return dst.raw[::-1]
