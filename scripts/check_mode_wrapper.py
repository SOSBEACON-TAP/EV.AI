"""Guards against the bug that stopped every mode switch in 1.0.33-1.0.35: _faded() forgot `return wrapper`, so the six
wrapped methods (Jarvis, Ultron, Game, Karen, characters) all became None and every switch failed with
"'NoneType' object is not callable". Run: python scripts/check_mode_wrapper.py"""
import ast
import sys
from pathlib import Path

tree = ast.parse((Path(__file__).resolve().parent.parent / "ui" / "main_window.py").read_text(encoding="utf-8"))
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_faded")
if not isinstance(fn.body[-1], ast.Return):
    sys.exit("FAIL: _faded() does not return its wrapper")
print("ok: _faded() returns its wrapper")
