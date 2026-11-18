# Agent rules for feed-commons

Read `CLAUDE.md` for what this repo is. These rules come from the stack packs. The gates enforce them.

## Gates

Run each gate from the repo root before you say a task is done. CI and `.githooks/pre-commit` run the same scripts. Never commit with `--no-verify`.

- Core: `bash scripts/core-validate.sh` (file size, names, complexity, function length, parameters, nesting, duplication).
- GitHub Actions: `bash scripts/gha-validate.sh` (pins, permissions, actionlint, zizmor).
- Python: `bash scripts/py-validate.sh`. It runs `uv run --locked` for `ruff check .`, `ruff format --check .`, `mypy src` and `pytest -q`.
- Shell: `bash scripts/shell-validate.sh` (bash -n, shellcheck, shfmt, bats).
- Writing: `bash scripts/writing-validate.sh` (Vale on changed files).
- Install the gate tools once: `bash scripts/install-gate-tools.sh`, then put `~/.cache/feed-commons-gates/bin` on `PATH`. Every download is checksum-pinned.

## Core rules

- Reuse before you write. Search for an existing function or module first. Extend it instead of adding a near copy.
- Keep variants in data and generic code. When two things differ only in a type or a value, write one function that takes the type or the value.
- Extract on the second real occurrence, not the first guess. Never merge code that looks alike but belongs to different domains.
- No boolean flag arguments. Two behaviors are two functions.
- Organize by domain (orders, billing, auth), not by kind (utils, helpers, managers). Dependencies point one way: edge to domain, never back.
- A function does one thing at one level of detail. Use guard clauses to return early. Keep it under 50 lines, under 10 branches, at most 4 parameters.
- Names say what a thing is or does. No `data`, `info`, `tmp`, `handle`, `process` as a whole name.
- Prefer composition and plain functions to inheritance. Keep side effects at the edges.
- Fail loudly: return or raise an error with context. Never swallow one. Comments say why, not what.
- Delete dead code and unused options. Concise means fewer concepts, not shorter names.
- A behavior change ships with a test that fails without it. Do not edit generated files; change the generator.
- Never edit a limit or a config to make a run pass. Fix the code. A waiver goes in `.core-allow` with a reason.

## Repo traps

- `scripts/*-validate.sh`, `scripts/*-check.py`, `scripts/core-lizard.py`, `scripts/vale-central.ini` and `scripts/styles/` are copies from the packs. Do not edit them. Update them by copying a new pack version.
- `.core-config` may only shrink. There is no `.core-baseline.json`: fix an over-limit function, do not baseline it.
- Lizard is pinned in `scripts/tools/gate-requirements.txt`. A baseline from another lizard version can fail. Write it with the pinned one.
- Add a dependency with `uv add`. Ask before you add a production dependency. Commit `uv.lock`.

## GitHub Actions rules

- Pin every `uses:` to a full 40-character commit SHA with the version in a trailing comment. No `@v4`, `@main`.
- Set `permissions: contents: read` at the top of every workflow and raise it per job only where needed.
- Never put `${{ github.event... }}`, `${{ github.head_ref }}` or `${{ inputs.x }}` inside `run:`. Pass it through `env:` and read `$VAR`.
- Do not use `pull_request_target`. If a workflow truly needs it, never check out the PR head, and add `# gha-allow: pull_request_target <reason>`.
- `actions/checkout` gets `persist-credentials: false`. Every job has `timeout-minutes`. No `secrets: inherit`.
- Authenticate to clouds and registries with OIDC, not stored long-lived secrets.
- Never edit the workflow checks, the zizmor config or branch protection to make a run pass. Fix the workflow.

## Python rules

- Never commit with `--no-verify`. The hook and CI run the same gate.
- Fix what a tool reports. Do not add an `ignore` to pyproject.toml. A one-line exception is
  `# noqa: CODE -- reason` or `# type: ignore[code]  # reason`.
- New code is fully typed. Public functions have a docstring line.
- Catch the narrowest exception. Never `except:` or a silent `pass`.
- Log with `log = logging.getLogger(__name__)` and `log.info("x=%s", x)`. No `print` in library code.
- Never call blocking code (`time.sleep`, `requests`) inside `async def`.
- Every behavior change ships with a test in `tests/`.

## Shell rules

- `#!/usr/bin/env bash` and `set -euo pipefail` on every script. A sourced library is named `*.bash`.
- Scripts must run on macOS `/bin/bash` 3.2 and on bash 5: no `mapfile`, `declare -A`, `${x,,}`, `${arr[-1]}`, `|&`, `wait -n`. Use a `while read` loop. A Linux-only script says `# sh-allow: bash4 <reason>`.
- Quote every expansion: `"$var"`, `"$@"`, `"${arr[@]}"`. On bash 3.2 an empty array is `${arr[@]+"${arr[@]}"}` under `set -u`.
- Errors go to stderr (`echo ... >&2`) and the script exits non-zero. Check external tools with `command -v`. Wrap logic in `main "$@"`.
- Every `mktemp` has a `trap '...' EXIT` cleanup. Never `curl | sh`; never `eval` without a reason.
- Declare and assign separately when the value is a command substitution (`local x; x="$(cmd)"`), so the exit code is not masked.
- A behavior change ships with a bats test. Never edit `.shellcheckrc` or the checks to make a run pass. Waive one finding with `# shellcheck disable=SCxxxx` or `# sh-allow: <name> <reason>`.

## Writing (writing pack)

Docs and code comments are short, plain, American English. Run `bash scripts/writing-validate.sh` before you commit. It lints changed files with Vale.

1. Put the point first. One idea per sentence. Cut a sentence that adds no fact.
2. Use plain words ("use" over its long forms). Spell American: "color", "behavior", "organize".
3. Write steps as numbered imperatives. Put the condition first: "If the build fails, run X".
4. A code comment says why, or what breaks if someone changes the line. It does not say what the next line does. Three sentences at most.
<!-- This rule names the banned words, so it must quote them. -->
<!-- vale off -->
5. No AI filler: "delve", "robust", "seamless", "leverage", "not just X but Y", em-dash chains.
<!-- vale on -->
6. An error rule fails the gate. A warning prints and passes. A false positive gets `<!-- vale off -->` with a reason, or a line in `.writing-allow`.
