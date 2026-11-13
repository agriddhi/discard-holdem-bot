"""Peak RSS + worst-case single-reply latency of the bot process.

Limits: 1 GB RAM, 5 s hard per-reply wall clock (a timeout forfeits the
match).  Also reports the time-bank consumption per match shape.

Usage: py -3.11 measure_memory.py
"""
import os
import subprocess
import sys
import time

BOT = "dist/bot.py"


def sample_children_rss_kb():
    """Working set of all python child processes, in KB."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    QLI = 0x1000

    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]

    total = 0
    snap = k32.CreateToolhelp32Snapshot(0x00000002, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    if k32.Process32First(snap, ctypes.byref(pe)):
        while True:
            h = k32.OpenProcess(QLI, False, pe.th32ProcessID)
            if h:
                m = ctypes.c_ulong()
                if psapi.GetProcessMemoryInfo(h, ctypes.byref(m),
                                             ctypes.sizeof(m)):
                    total += m.WorkingSetSize
                k32.CloseHandle(h)
            if not k32.Process32Next(snap, ctypes.byref(pe)):
                break
    k32.CloseHandle(snap)
    return total // 1024


env = dict(os.environ)
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
          "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    env[v] = "1"          # simulate the 1 vCPU box

print("=== peak RSS while a match runs (1 vCPU, threads pinned) ===")
cmd = ["py", "-3.11", "engine.py", BOT, "example_bots\\value_bot.py",
       "--stage", "2", "--seed", "111", "--log-dir", "logs_res_mem"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, env=env)
peak = 0
samples = 0
while proc.poll() is None:
    peak = max(peak, sample_children_rss_kb())
    samples += 1
    time.sleep(0.25)
out = proc.stdout.read()
print(f"   peak working set of all bot processes: {peak} KB "
      f"({peak/1024:.0f} MB)  [limit 1024 MB]")
print(f"   margin: {1024 - peak/1024:.0f} MB")
for line in out.splitlines():
    if "bot.py" in line and "net" in line:
        print("  ", line.strip())

print("\n=== worst-case single equity call (the 5 s reply limit) ===")
sys.path.insert(0, ".")
import numpy as np  # noqa: E402
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("subbot", BOT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

worst = 0.0
for trial in range(30):
    b = mod.Bot()
    hole = ["As", "Kd", "Qc"]
    board = ["9h", "Ts", "2c"]
    t0 = time.perf_counter()
    b.equity3(hole, board, 1200)     # largest sample count we use
    dt = time.perf_counter() - t0
    worst = max(worst, dt)
print(f"   slowest equity3(n=1200) over 30 trials: {worst*1000:.1f} ms")
print(f"   margin to the 5 s reply limit: {(5-worst):.2f} s "
      f"({5/worst:.0f}x headroom)")
