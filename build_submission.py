"""Merge bot.py + equity.py into one self-contained submission file.

The submission must be a single bot.py at the top level of a zip (Rulebook
5.10), with no sibling modules to import.  This script inlines equity.py at
the `import equity as EQ` line and exposes the three functions the bot uses
under the EQ alias, so the strategy code stays byte-identical.

Usage:  py -3.11 build_submission.py   ->  dist/bot.py
"""
import pathlib

root = pathlib.Path(__file__).resolve().parent
bot = (root / "bot.py").read_text(encoding="utf-8")
eq = (root / "equity.py").read_text(encoding="utf-8")

MARKER = "import equity as EQ"
if bot.count(MARKER) != 1:
    raise SystemExit(f"expected exactly one {MARKER!r}, found {bot.count(MARKER)}")

shim = (
    "# ---- inlined from equity.py (single-file submission) -----------------\n"
    + eq.rstrip()
    + "\n\n"
    + "# expose the evaluator under the EQ alias used by the strategy code\n"
    + "import types as _types\n"
    + "EQ = _types.SimpleNamespace(eval7=eval7, cid=cid, equity_mc=equity_mc)\n"
)

merged = bot.replace(MARKER, shim)

out_dir = root / "dist"
out_dir.mkdir(exist_ok=True)
out = out_dir / "bot.py"
out.write_text(merged, encoding="utf-8", newline="\n")
print(f"wrote {out} ({len(merged.encode('utf-8'))} bytes)")
