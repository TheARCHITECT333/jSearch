"""Verify every logger.* call's %-placeholder count matches its argument count.

A mismatch does not raise at import time - logging swallows it into a
'--- Logging error ---' on stderr at runtime - so it has to be checked
statically.
"""
import ast
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
LEVELS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
PLACEHOLDER = re.compile(r"%(?:\((\w+)\))?[-#0 +]*(?:\d+|\*)?(?:\.(?:\d+|\*))?([a-zA-Z%])")

problems = 0
for path in sorted(BASE.glob("app/**/*.py")):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in LEVELS:
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "logger"):
            continue

        args = list(node.args)
        if func.attr == "log":
            args = args[1:]  # drop the level argument
        if not args or not isinstance(args[0], ast.Constant):
            continue
        fmt = args[0].value
        if not isinstance(fmt, str):
            continue

        specs = [m for m in PLACEHOLDER.finditer(fmt) if m.group(2) != "%"]
        if any(m.group(1) for m in specs):
            continue  # %(name)s style takes a dict
        expected = len(specs)
        supplied = len(args) - 1
        if expected != supplied:
            problems += 1
            print(
                f"{path.relative_to(BASE)}:{node.lineno}: "
                f"{expected} placeholder(s) but {supplied} arg(s): {fmt!r}"
            )

print("OK - no mismatches" if not problems else f"{problems} mismatch(es)")
sys.exit(1 if problems else 0)
