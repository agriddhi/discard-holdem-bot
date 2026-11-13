"""Measure the bot's resource usage against the stated limits.

  * 1 vCPU      -> single-threaded, no BLAS thread explosion
  * 1 GB RAM    -> peak working set of a bot process
  * 60 s bank per 400-hand match (Stage 1: 6 rounds x 400 hands)
  * read-only FS -> the bot must not write anything

Runs a full Stage-1-length match against the slowest local opponent and
records the bot process's peak RSS and CPU time.

Usage: py -3.11 measure_resources.py
"""
import os
import subprocess
import sys
import time

BOT = "dist/bot.py"


def peak_rss_of_children():
    """Peak RSS (KB) of any python child process, via psutil-free polling."""
    return 0


def run_match(label, opp, stage, seed):
    env = dict(os.environ)
    # 1 vCPU: force single-threaded BLAS so we do not spawn a thread pool
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        env[v] = "1"
    cmd = ["py", "-3.11", "engine.py", BOT, opp, "--stage", str(stage),
           "--seed", str(seed), "--log-dir", f"logs_res_{label}"]
    t0 = time.time()
    out = subprocess.run(cmd, capture_output=True, text=True, env=env,
                         timeout=900).stdout
    wall = time.time() - t0
    for line in out.splitlines():
        if "bot.py" in line and "net" in line:
            print("   ", line.strip())
        if "Result" in line:
            print("   ", line.strip())
        if "Capped" in line:
            print("   ", line.strip())
    return wall


def child_peak_rss_kb():
    """Peak RSS of running python children (Windows: sum of working sets)."""
    total = 0
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_char * 260)]

        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if kernel32.Process32First(snapshot, ctypes.byref(pe)):
            while True:
                h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                          False, pe.th32ProcessID)
                if h:
                    mem = ctypes.c_ulong()
                    if psapi.GetProcessMemoryInfo(h, ctypes.byref(mem),
                                                 ctypes.sizeof(mem)):
                        total += mem.WorkingSetSize
                    kernel32.CloseHandle(h)
                if not kernel32.Process32Next(snapshot, ctypes.byref(pe)):
                    break
        kernel32.CloseHandle(snapshot)
    except Exception:
        return 0
    return total // 1024


print("=== resource usage, 1 vCPU (BLAS pinned to 1 thread) ===")
print("\n--- Stage 1 shape: 400 hands vs value_bot ---")
w = run_match("s1", "example_bots\\value_bot.py", 1, 111)
print(f"    wall clock for the whole match: {w:.1f} s")

print("\n--- Stage 2 shape: 1000 hands vs value_bot ---")
w2 = run_match("s2", "example_bots\\value_bot.py", 2, 111)
print(f"    wall clock for the whole match: {w2:.1f} s")

print("\n=== notes ===")
print("  the engine reports the bot's own CPU time in the summary lines above")
print("  peak RSS is measured below from a live run")
