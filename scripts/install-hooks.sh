#!/usr/bin/env bash
# One-time per clone: point git at the versioned .githooks/ dir and check the
# scanner is present. Run this after cloning feed-commons on a new machine
# (Mac dev box, desktop). Git does NOT enable shared hooks automatically.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/pre-push
echo "hooks: core.hooksPath -> .githooks (pre-commit + pre-push active)"

if command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks: $(gitleaks version) present"
else
  echo "WARNING: gitleaks not installed — the hooks will BLOCK every commit/push until it is." >&2
  echo "  macOS:  brew install gitleaks" >&2
  echo "  Linux:  see https://github.com/gitleaks/gitleaks#installing" >&2
  exit 1
fi
