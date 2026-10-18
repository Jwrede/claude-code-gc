# claude-code-gc

Claude Code updates itself often, and every update leaves the previous version on disk. On a
remote dev box the same version usually exists up to three times: the CLI binary in
`~/.local/share/claude/versions/`, the editor extension in `~/.vscode-server/extensions/`, and
the downloaded VSIX in the extension cache. Each copy is 250 to 290 MB, so a small VPS fills
up within a few weeks.

`claude-code-gc` lists these copies, shows which ones a running process still uses, and
removes the rest. It never deletes a version that a running session or editor extension uses,
and it keeps the newest version of each kind.

## Install

```
pipx install git+https://github.com/Jwrede/claude-code-gc
```

or run it without installing:

```
uvx --from git+https://github.com/Jwrede/claude-code-gc claude-code-gc
```

It needs Python 3.10+ and Linux (it reads `/proc` to find running processes). It has no
dependencies.

## Usage

Example output on a VPS with several sessions open:

```
$ claude-code-gc
cli        2.1.299     253.0 MB  in use (pid 324791)    ~/.local/share/claude/versions/2.1.299
cli        2.1.300     253.8 MB  remove                 ~/.local/share/claude/versions/2.1.300
cli        2.1.302     272.6 MB  in use (pid 1683736)   ~/.local/share/claude/versions/2.1.302
extension  2.1.300     266.9 MB  remove                 ~/.vscode-server/extensions/anthropic.claude-code-2.1.300-linux-x64
extension  2.1.301     267.5 MB  keep (newest)          ~/.vscode-server/extensions/anthropic.claude-code-2.1.301-linux-x64

2 item(s) removable, 520.7 MB. Run with --delete to remove them.
note: pid 3581507 still runs deleted ~/.local/share/claude/versions/2.1.292; its space returns when it exits.
```

The default is a dry run. `--delete` removes the items marked `remove`. `--keep N` keeps the
newest N versions of each kind (default 1; `--keep 0` keeps only what is in use).

The `note` lines list long-running sessions that still execute a binary that was already
deleted. Linux frees that disk space only when the process exits, so ending old sessions is the
only way to get it back.

## What counts as "in use"

A version is in use when a running process has it as its executable (`/proc/<pid>/exe`) or
names a file inside it on its command line. The second case covers the VS Code extension,
which runs as `node .../extension.js`.

## Locations scanned

| Kind | Directories |
|---|---|
| cli | `~/.local/share/claude/versions/` |
| extension | `~/.vscode-server/extensions/`, `~/.vscode/extensions/`, `~/.cursor-server/extensions/`, `~/.cursor/extensions/`, `~/.windsurf-server/extensions/` |
| vsix | `~/.vscode-server/data/CachedExtensionVSIXs/`, `~/.config/Code/CachedExtensionVSIXs/` |

In extension and VSIX directories only entries named `anthropic.claude-code-<version>...` are
considered.

## License

MIT
