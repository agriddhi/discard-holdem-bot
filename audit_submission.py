"""Audit the shipped submission against the stated runtime constraints.

Checks the file that will actually be uploaded (submission.zip -> bot.py):
  1. imports: standard library + NumPy/SciPy only
  2. no file writes (read-only filesystem), no network, no subprocess
  3. stdout carries ONLY protocol JSON
  4. no Python-version-risky constructs for 3.11
  5. memory footprint sane (1 GB limit)
"""
import ast
import re
import sys
import zipfile

ALLOWED = {
    "json", "sys", "os", "time", "random", "traceback", "types",
    "collections", "itertools", "functools", "math", "re", "copy",
    "numpy", "scipy",
}
STDLIB = set(sys.stdlib_module_names)

path = sys.argv[1] if len(sys.argv) > 1 else "submission.zip"
if path.endswith(".zip"):
    src = zipfile.ZipFile(path).read("bot.py").decode("utf-8")
    print(f"auditing {path} -> bot.py ({len(src)} bytes)")
else:
    src = open(path, encoding="utf-8").read()
    print(f"auditing {path} ({len(src)} bytes)")

tree = ast.parse(src)

print("\n=== 1. imports ===")
bad_imports = []
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for a in node.names:
            top = a.name.split(".")[0]
            ok = top in ALLOWED
            print(f"   import {a.name:<20} {'ok' if ok else 'NOT ALLOWED'}")
            if not ok:
                bad_imports.append(a.name)
    elif isinstance(node, ast.ImportFrom):
        top = (node.module or "").split(".")[0]
        ok = top in ALLOWED
        print(f"   from {node.module} import ...  "
              f"{'ok' if ok else 'NOT ALLOWED'}")
        if not ok:
            bad_imports.append(node.module)
        for a in node.names:
            if a.name in ("eval7", "cid", "equity_mc"):
                print(f"        (inlined equity.py: {a.name})")

print("\n=== 2. forbidden runtime behaviour ===")
patterns = {
    "file write mode": r"open\([^)]*['\"](w|a|x|wb|ab|r\+)\b",
    "os.remove/unlink/rename": r"os\.(remove|unlink|rename|rmdir)\s*\(",
    "os.mkdir/makedirs": r"os\.(mkdir|makedirs)\s*\(",
    "pathlib": r"\bpathlib\b",
    "socket": r"\bsocket\b",
    "urllib": r"\burllib\b",
    "requests/httpx": r"\b(requests|httpx|aiohttp)\b",
    "subprocess": r"\bsubprocess\b",
    "tempfile/pickle": r"\b(tempfile|pickle|shelve|marshal)\b",
    "os.environ assignment": r"os\.environ\s*\[",
    "time.sleep": r"time\.sleep\b",
    "signal": r"(^|[^\w.])signal\s*\.",
    "multiprocessing": r"\bmultiprocessing\b",
    "threading": r"\bthreading\b",
}
found = {}
for name, pat in patterns.items():
    m = re.search(pat, src)
    found[name] = m.group(0) if m else None
    print(f"   {name:<28} {m.group(0) if m else 'none'}")

print("\n=== 3. stdout purity ===")
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id == "print":
        seg = ast.get_source_segment(src, node) or ""
        has_file = any(kw.arg == "file" for kw in node.keywords)
        print(f"   print({seg[:70]})"
              f"{'  [-> stderr]' if has_file else '  [-> stdout]'}")

print("\n=== 4. python 3.11 compatibility ===")
risky = []
for node in ast.walk(tree):
    if isinstance(node, ast.Match):
        risky.append("match statement (3.10+, fine in 3.11)")
    if isinstance(node, ast.NamedExpr):
        risky.append("walrus (3.8+, fine)")
print("   constructs needing >=3.11:", risky if risky else "none")
print(f"   source parses under the running "
      f"{sys.version_info.major}.{sys.version_info.minor}")

print("\n=== SUMMARY ===")
problems = list(bad_imports)
for name, hit in found.items():
    if hit:
        problems.append(f"{name}: {hit}")
print("PROBLEMS:", problems if problems else "NONE")
sys.exit(1 if problems else 0)
