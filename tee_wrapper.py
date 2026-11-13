"""Debug wrapper: tees the inner bot's stdout to a file, passes everything through."""
import subprocess
import sys
import os

inner = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bot.py")
args = sys.argv[2:]
dbg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_stdout_capture.txt")

p = sys.stdout
proc = subprocess.Popen([sys.executable, inner] + args,
                        stdin=sys.stdin, stdout=subprocess.PIPE,
                        stderr=sys.stderr, text=True, bufsize=1)
with open(dbg, "a", encoding="utf-8") as f:
    f.write("=== new process ===\n")
    for line in proc.stdout:
        with open(dbg, "a", encoding="utf-8") as f2:
            f2.write(repr(line) + "\n")
        p.write(line)
        p.flush()
sys.exit(proc.wait())
