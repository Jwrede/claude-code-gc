from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_EXT_PREFIX = "anthropic.claude-code-"


@dataclass
class Install:
    """One copy of one Claude Code version on disk."""

    kind: str  # "cli", "extension" or "vsix"
    version: tuple[int, int, int]
    path: Path
    size: int = 0
    pids: list[int] = field(default_factory=list)

    @property
    def version_str(self) -> str:
        return ".".join(map(str, self.version))


@dataclass
class HeldBinary:
    """A deleted file that a running process still holds open."""

    pid: int
    path: str


def parse_version(name: str) -> tuple[int, int, int] | None:
    m = _VERSION_RE.search(name)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def disk_size(path: Path) -> int:
    if path.is_symlink():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            p = Path(root) / f
            if not p.is_symlink():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    return total


def default_locations(home: Path) -> dict[str, list[Path]]:
    """Directories where Claude Code versions accumulate."""
    ext_dirs = [
        home / ".vscode-server" / "extensions",
        home / ".vscode" / "extensions",
        home / ".cursor-server" / "extensions",
        home / ".cursor" / "extensions",
        home / ".windsurf-server" / "extensions",
    ]
    vsix_dirs = [
        home / ".vscode-server" / "data" / "CachedExtensionVSIXs",
        home / ".config" / "Code" / "CachedExtensionVSIXs",
    ]
    return {
        "cli": [home / ".local" / "share" / "claude" / "versions"],
        "extension": ext_dirs,
        "vsix": vsix_dirs,
    }


def find_installs(locations: dict[str, list[Path]]) -> list[Install]:
    installs = []
    for kind, dirs in locations.items():
        for d in dirs:
            if not d.is_dir():
                continue
            for entry in d.iterdir():
                if kind != "cli" and not entry.name.startswith(_EXT_PREFIX):
                    continue
                version = parse_version(entry.name)
                if version is None:
                    continue
                installs.append(Install(kind, version, entry, disk_size(entry)))
    return installs


def scan_processes(proc: Path = Path("/proc")) -> tuple[dict[int, list[str]], list[HeldBinary]]:
    """Return the paths each process references and deleted binaries still held.

    A process references a path through its executable or its command line
    (the VS Code extension runs as `node .../extension.js`).
    """
    refs: dict[int, list[str]] = {}
    held: list[HeldBinary] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        paths = []
        try:
            exe = os.readlink(entry / "exe")
            if exe.endswith(" (deleted)"):
                held.append(HeldBinary(pid, exe[: -len(" (deleted)")]))
            else:
                paths.append(exe)
        except OSError:
            pass
        try:
            raw = (entry / "cmdline").read_bytes()
            paths.extend(a for a in raw.decode(errors="replace").split("\0") if a)
        except OSError:
            pass
        if paths:
            refs[pid] = paths
    return refs, held


def mark_in_use(installs: list[Install], refs: dict[int, list[str]]) -> None:
    for inst in installs:
        prefix = str(inst.path)
        for pid, paths in refs.items():
            if any(p == prefix or p.startswith(prefix + os.sep) for p in paths):
                inst.pids.append(pid)


def plan(installs: list[Install], keep: int) -> tuple[list[Install], list[Install]]:
    """Split installs into (kept, removable).

    The newest `keep` versions of each kind stay, and so does every install
    that a running process uses.
    """
    kept, removable = [], []
    for kind in sorted({i.kind for i in installs}):
        group = sorted((i for i in installs if i.kind == kind), key=lambda i: i.version, reverse=True)
        newest = {i.version for i in group[:keep]} if keep > 0 else set()
        for inst in group:
            (kept if inst.version in newest or inst.pids else removable).append(inst)
    return kept, removable


def remove(inst: Install) -> None:
    if inst.path.is_dir() and not inst.path.is_symlink():
        shutil.rmtree(inst.path)
    else:
        inst.path.unlink()
