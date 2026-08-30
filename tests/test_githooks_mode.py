"""Regression test: the versioned git hooks must be executable.

`core.hooksPath` points at `.githooks/`, but git silently no-ops a hook file
that lacks the executable bit -- no error, no warning, the hook just never
runs. A prior session's `chmod +x` on these two files was never committed,
so every fresh clone (and every worktree checked out from that commit)
inherited non-executable, therefore inert, hooks. This pins the fix: the
tracked file mode itself must carry the executable bit, not just whatever
happens to be on disk on one machine.
"""

import os
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_FILES = ["pre-commit", "pre-push"]


def test_githooks_are_executable():
    missing_exec = []
    for name in HOOK_FILES:
        path = REPO_ROOT / ".githooks" / name
        mode = os.stat(path).st_mode
        if not (mode & stat.S_IXUSR):
            missing_exec.append(name)
    assert not missing_exec, (
        f"non-executable git hooks (core.hooksPath silently skips these): {missing_exec}"
    )
