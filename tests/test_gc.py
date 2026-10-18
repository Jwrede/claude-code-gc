import os
from pathlib import Path

from claude_code_gc.cli import main
from claude_code_gc.core import default_locations, find_installs, mark_in_use, parse_version, plan, scan_processes


def make_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    cli = home / ".local/share/claude/versions"
    cli.mkdir(parents=True)
    for v in ("2.1.299", "2.1.300", "2.1.301"):
        (cli / v).write_bytes(b"x" * 1000)
    ext = home / ".vscode-server/extensions"
    ext.mkdir(parents=True)
    for v in ("2.1.300", "2.1.301"):
        d = ext / f"anthropic.claude-code-{v}-linux-x64"
        d.mkdir()
        (d / "extension.js").write_bytes(b"y" * 500)
    (ext / "mechatroner.rainbow-csv-3.24.1").mkdir()
    return home


def make_proc(tmp_path: Path, procs: dict) -> Path:
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "self").mkdir()
    for pid, (exe, cmdline) in procs.items():
        d = proc / str(pid)
        d.mkdir()
        os.symlink(exe, d / "exe")
        (d / "cmdline").write_bytes("\0".join(cmdline).encode() + b"\0")
    return proc


def test_parse_version():
    assert parse_version("anthropic.claude-code-2.1.301-linux-x64") == (2, 1, 301)
    assert parse_version("2.1.9") == (2, 1, 9)
    assert parse_version("latest") is None


def test_find_installs_ignores_other_extensions(tmp_path):
    installs = find_installs(default_locations(make_home(tmp_path)))
    assert sorted((i.kind, i.version_str) for i in installs) == [
        ("cli", "2.1.299"),
        ("cli", "2.1.300"),
        ("cli", "2.1.301"),
        ("extension", "2.1.300"),
        ("extension", "2.1.301"),
    ]
    assert all(i.size > 0 for i in installs)


def test_plan_keeps_newest_and_in_use(tmp_path):
    home = make_home(tmp_path)
    old_cli = home / ".local/share/claude/versions/2.1.299"
    proc = make_proc(tmp_path, {101: (str(old_cli), [str(old_cli), "--resume"])})
    installs = find_installs(default_locations(home))
    refs, held = scan_processes(proc)
    mark_in_use(installs, refs)
    kept, removable = plan(installs, keep=1)
    assert sorted((i.kind, i.version_str) for i in removable) == [("cli", "2.1.300"), ("extension", "2.1.300")]
    in_use = next(i for i in kept if i.version_str == "2.1.299")
    assert in_use.pids == [101]
    assert held == []


def test_extension_in_use_via_cmdline(tmp_path):
    home = make_home(tmp_path)
    js = home / ".vscode-server/extensions/anthropic.claude-code-2.1.300-linux-x64/extension.js"
    proc = make_proc(tmp_path, {7: ("/usr/bin/node", ["node", str(js)])})
    installs = find_installs(default_locations(home))
    mark_in_use(installs, scan_processes(proc)[0])
    _, removable = plan(installs, keep=1)
    assert ("extension", "2.1.300") not in {(i.kind, i.version_str) for i in removable}


def test_prefix_does_not_match_longer_version(tmp_path):
    home = make_home(tmp_path)
    (home / ".local/share/claude/versions/2.1.30").write_bytes(b"z")
    other = home / ".local/share/claude/versions/2.1.301"
    proc = make_proc(tmp_path, {5: (str(other), [str(other)])})
    installs = find_installs(default_locations(home))
    mark_in_use(installs, scan_processes(proc)[0])
    short = next(i for i in installs if i.version_str == "2.1.30")
    assert short.pids == []


def test_deleted_binary_is_reported(tmp_path):
    proc = make_proc(tmp_path, {9: ("/home/u/.local/share/claude/versions/2.1.292 (deleted)", ["claude"])})
    _, held = scan_processes(proc)
    assert [(h.pid, h.path) for h in held] == [(9, "/home/u/.local/share/claude/versions/2.1.292")]


def test_cli_dry_run_then_delete(tmp_path, capsys):
    home = make_home(tmp_path)
    proc = make_proc(tmp_path, {})
    assert main(["--home", str(home), "--proc", str(proc)]) == 0
    out = capsys.readouterr().out
    assert "3 item(s) removable" in out
    assert (home / ".local/share/claude/versions/2.1.299").exists()

    assert main(["--home", str(home), "--proc", str(proc), "--delete"]) == 0
    left = sorted(p.name for p in (home / ".local/share/claude/versions").iterdir())
    assert left == ["2.1.301"]
    ext_left = sorted(p.name for p in (home / ".vscode-server/extensions").iterdir())
    assert ext_left == ["anthropic.claude-code-2.1.301-linux-x64", "mechatroner.rainbow-csv-3.24.1"]


def test_keep_zero_removes_all_unused(tmp_path):
    installs = find_installs(default_locations(make_home(tmp_path)))
    kept, removable = plan(installs, keep=0)
    assert kept == [] and len(removable) == 5
