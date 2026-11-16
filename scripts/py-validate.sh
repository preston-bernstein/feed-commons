#!/usr/bin/env bash
# Validation gate for agent-written Python. Pack: python-uv, rule py-one-gate-command.
#
#   py-validate.sh [ROOT]
#
# Order: ruff check -> ruff format --check -> type check -> pytest.
# With a uv.lock, every tool runs as `uv run --locked <tool>`, so it uses the locked environment.
# Without one, the tools must already be on PATH and the project installed there (pip install -e .).
# Every tool is checked before any step runs. A missing tool fails the gate with exit 127. Nothing is skipped.
# Env:
#   PY_TYPECHECKER   mypy or ty (default: mypy when pyproject.toml has [tool.mypy], ty when it has [tool.ty...])
#   PY_TYPECHECK_PATHS   what the type checker reads (default src)
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

fail() { echo "py-validate: $*" >&2; exit "${2:-1}"; }
need() { command -v "$1" >/dev/null 2>&1 || fail "missing tool: $1 (the gate never skips a step)" 127; }

if [ ! -f pyproject.toml ]; then
  echo "py-validate: no pyproject.toml, nothing to check"
  exit 0
fi

checker="${PY_TYPECHECKER:-}"
if [ -z "$checker" ]; then
  if grep -q '^\[tool\.mypy\]' pyproject.toml; then
    checker=mypy
  elif grep -q '^\[tool\.ty[].]' pyproject.toml; then
    checker=ty
  else
    fail "no type checker configured: add [tool.mypy] (strict) or [tool.ty] to pyproject.toml (see templates/pyproject.tooling.toml)" 2
  fi
fi
[ "$checker" = mypy ] || [ "$checker" = ty ] || fail "PY_TYPECHECKER must be mypy or ty, got '$checker'" 2
[ -d tests ] || fail "no tests/ directory: a feature ships with tests" 2

RUN=()
if [ -f uv.lock ]; then
  need uv
  RUN=(uv run --locked)
else
  need ruff
  need "$checker"
  need pytest
fi

paths="${PY_TYPECHECK_PATHS:-src}"
run() { "${RUN[@]+"${RUN[@]}"}" "$@"; }

run ruff check .
run ruff format --check .
if [ "$checker" = ty ]; then
  run ty check $paths
else
  run mypy $paths
fi
run pytest -q
echo "py-validate: all checks passed"
