"""Developer test tool: convert one file and watch time and memory.

Run from the project root as:

    python -m scripts.convert_file "<input file>" <md|pdf|docx> [--out-dir <folder>]

The "-m" form is used so Python puts the project root on the import search
path, which is what lets this script import the md_converter package. This is
a developer test tool, not a product command-line mode.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import threading
import time
from pathlib import Path

from md_converter.config import setup_logging
from md_converter.core.models import (
    ConversionRequest,
    ConversionResult,
    ConversionStatus,
    DocFormat,
)
from md_converter.core.pipeline import convert


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    """Win32 PROCESS_MEMORY_COUNTERS structure (fields in documented order)."""

    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_TARGET_FORMATS: dict[str, DocFormat] = {
    "md": DocFormat.MD,
    "pdf": DocFormat.PDF,
    "docx": DocFormat.DOCX,
}


def _working_set_mb() -> tuple[float, float] | None:
    """Return (current, peak) working set in MB, or None on any failure."""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetCurrentProcess.argtypes = []

        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            ctypes.c_uint32,
        ]

        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
        ok = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        if not ok:
            return None
        mb = 1024.0 * 1024.0
        return (
            counters.WorkingSetSize / mb,
            counters.PeakWorkingSetSize / mb,
        )
    except Exception:
        return None


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the developer tool."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.convert_file",
        description=(
            "Developer test tool: convert one file and print time and memory."
        ),
    )
    parser.add_argument("input", type=Path, help="Path to the input file.")
    parser.add_argument(
        "target",
        choices=("md", "pdf", "docx"),
        help="Target format: md, pdf or docx.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output folder; defaults to the input file's folder.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one conversion in a worker thread and print a short report."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Deliberate call, not an import side effect.
    setup_logging()

    input_path: Path = args.input
    target_format: DocFormat = _TARGET_FORMATS[args.target]
    output_dir: Path | None = args.out_dir

    request = ConversionRequest(
        source=input_path,
        target_format=target_format,
        output_dir=output_dir,
    )

    cancel = threading.Event()
    result_holder: list[ConversionResult] = []
    start_time = time.perf_counter()

    def progress_cb(done: int, total: int | None) -> None:
        """Print a line every 25 chunks with elapsed time and current memory."""
        if done % 25 == 0:
            elapsed = time.perf_counter() - start_time
            mem = _working_set_mb()
            mem_str = "n/a" if mem is None else f"{mem[0]:.1f} MB"
            print(
                f"pages done: {done} | elapsed: {elapsed:.1f} s | "
                f"memory now: {mem_str}"
            )

    # The worker thread runs the conversion; the main thread stays free to
    # notice Ctrl+C and set the cancel event. This mirrors how the future UI
    # will work.
    def worker() -> None:
        result = convert(request, progress=progress_cb, cancel=cancel)
        result_holder.append(result)

    thread = threading.Thread(target=worker, name="md-converter-worker")
    thread.start()

    try:
        while thread.is_alive():
            thread.join(timeout=0.2)
    except KeyboardInterrupt:
        print()
        print("Cancel requested, waiting for the worker to stop...")
        cancel.set()
        thread.join()
        elapsed = time.perf_counter() - start_time
        print(f"Conversion cancelled after {elapsed:.2f} s.")
        return 2

    elapsed = time.perf_counter() - start_time

    if not result_holder:
        print("Internal error: the worker produced no result.")
        return 1

    result = result_holder[0]

    print(f"Status: {result.status.value}")
    if result.error_message:
        print(f"Error: {result.error_message}")
    if result.output_path is not None:
        try:
            size_mb = result.output_path.stat().st_size / (1024 * 1024)
        except OSError:
            size_mb = 0.0
        print(f"Output: {result.output_path} ({size_mb:.2f} MB)")
    print(f"Chunks processed: {result.chunks_processed}")
    print(f"Total time: {elapsed:.2f} s")

    mem = _working_set_mb()
    if mem is None:
        print("Peak memory: n/a")
    else:
        print(f"Peak memory: {mem[1]:.1f} MB")

    if result.status is ConversionStatus.SUCCESS:
        return 0
    if result.status is ConversionStatus.CANCELLED:
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())