from __future__ import annotations

import argparse
import sys
from pathlib import Path

from claude_code_gc import __version__
from claude_code_gc.core import default_locations, find_installs, mark_in_use, plan, remove, scan_processes


def human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="claude-code-gc",
        description="List Claude Code versions on disk (CLI, editor extensions, VSIX cache) "
        "and remove the ones no running process uses.",
    )
    ap.add_argument("--keep", type=int, default=1, help="newest versions to keep per kind (default 1)")
    ap.add_argument("--delete", action="store_true", help="delete removable versions (default: dry run)")
    ap.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    ap.add_argument("--proc", type=Path, default=Path("/proc"), help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    installs = find_installs(default_locations(args.home))
    refs, held = scan_processes(args.proc) if args.proc.is_dir() else ({}, [])
    mark_in_use(installs, refs)
    _, removable = plan(installs, args.keep)

    if not installs:
        print("No Claude Code versions found.")
    for inst in sorted(installs, key=lambda i: (i.kind, i.version)):
        if inst in removable:
            status = "remove"
        elif inst.pids:
            status = "in use (pid " + ",".join(map(str, inst.pids[:3])) + ")"
        else:
            status = "keep (newest)"
        print(f"{inst.kind:<10} {inst.version_str:<10} {human(inst.size):>9}  {status:<22} {inst.path}")

    freed = sum(i.size for i in removable)
    if removable:
        if args.delete:
            for inst in removable:
                remove(inst)
            print(f"\nDeleted {len(removable)} item(s), freed {human(freed)}.")
        else:
            print(f"\n{len(removable)} item(s) removable, {human(freed)}. Run with --delete to remove them.")
    elif installs:
        print("\nNothing to remove.")

    for h in held:
        if "claude" in h.path:
            print(f"note: pid {h.pid} still runs deleted {h.path}; its space returns when it exits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
