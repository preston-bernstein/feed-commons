#!/usr/bin/env bash
# Install the pinned gate tools into one directory outside the repo (Linux x86_64).
# Every download is checked against a SHA-256 below before it is unpacked.
# Python and Node tools install from lockfiles with hashes. Bump a version by
# editing the pin and its checksum together, then read the diff.
#
#   install-gate-tools.sh [DEST]   DEST defaults to $GATE_TOOLS_DIR or ~/.cache/feed-commons-gates
#
# Afterwards, put DEST/bin on PATH.
set -euo pipefail

ACTIONLINT_VERSION=1.7.12
ACTIONLINT_SHA256=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8
SHELLCHECK_VERSION=0.11.0
SHELLCHECK_SHA256=8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198
SHFMT_VERSION=3.14.1
SHFMT_SHA256=76e77641faa025814b77f153b29796b8e6fa2fca03e0c76a691608b86c7ea7bf
VALE_VERSION=3.27.0
VALE_SHA256=c80d62f6bce87b81843ac5b512a26e63213927b957adba0a64fc594570da2000
BATS_VERSION=1.14.0
BATS_SHA256=bb537b70b15b732f6d8827dd6578e3d8ce166636ce1f18ea9a074184fcce9177

log() { echo "install-gate-tools: $*" >&2; }
die() {
  log "$*"
  exit "${2:-1}"
}

need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1" 127; }

# fetch URL SHA256 FILE: download to FILE and stop if the checksum differs.
fetch() {
  local url="$1" sha="$2" file="$3" actual
  curl --fail --silent --show-error --location --output "$file" "$url"
  actual="$(sha256sum "$file")"
  [ "${actual%% *}" = "$sha" ] || die "checksum mismatch for $url"
}

install_binaries() {
  local dest="$1" work="$2" base
  base="https://github.com"

  fetch "$base/rhysd/actionlint/releases/download/v$ACTIONLINT_VERSION/actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" \
    "$ACTIONLINT_SHA256" "$work/actionlint.tgz"
  tar -xzf "$work/actionlint.tgz" -C "$dest/bin" actionlint

  fetch "$base/koalaman/shellcheck/releases/download/v$SHELLCHECK_VERSION/shellcheck-v$SHELLCHECK_VERSION.linux.x86_64.tar.xz" \
    "$SHELLCHECK_SHA256" "$work/shellcheck.txz"
  tar -xJf "$work/shellcheck.txz" -C "$work" "shellcheck-v$SHELLCHECK_VERSION/shellcheck"
  install -m 0755 "$work/shellcheck-v$SHELLCHECK_VERSION/shellcheck" "$dest/bin/shellcheck"

  fetch "$base/mvdan/sh/releases/download/v$SHFMT_VERSION/shfmt_v${SHFMT_VERSION}_linux_amd64" \
    "$SHFMT_SHA256" "$work/shfmt"
  install -m 0755 "$work/shfmt" "$dest/bin/shfmt"

  fetch "$base/vale-cli/vale/releases/download/v$VALE_VERSION/vale_${VALE_VERSION}_Linux_64-bit.tar.gz" \
    "$VALE_SHA256" "$work/vale.tgz"
  tar -xzf "$work/vale.tgz" -C "$dest/bin" vale

  fetch "$base/bats-core/bats-core/archive/refs/tags/v$BATS_VERSION.tar.gz" \
    "$BATS_SHA256" "$work/bats.tgz"
  tar -xzf "$work/bats.tgz" -C "$work"
  "$work/bats-core-$BATS_VERSION/install.sh" "$dest/bats" >/dev/null
  ln -sf "$dest/bats/bin/bats" "$dest/bin/bats"
}

install_locked() {
  local dest="$1" here="$2"
  python3 -m venv "$dest/venv"
  "$dest/venv/bin/pip" install --quiet --disable-pip-version-check --require-hashes -r "$here/tools/gate-requirements.txt"
  ln -sf "$dest/venv/bin/lizard" "$dest/bin/lizard"
  ln -sf "$dest/venv/bin/zizmor" "$dest/bin/zizmor"

  cp "$here/tools/package.json" "$here/tools/package-lock.json" "$dest/node/"
  (cd "$dest/node" && npm ci --silent --ignore-scripts)
  ln -sf "$dest/node/node_modules/.bin/jscpd" "$dest/bin/jscpd"
}

main() {
  local dest here
  dest="${1:-${GATE_TOOLS_DIR:-$HOME/.cache/feed-commons-gates}}"
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  [ "$(uname -s)-$(uname -m)" = "Linux-x86_64" ] || die "this installer supports Linux x86_64 only" 2
  need curl
  need python3
  need npm
  need sha256sum

  mkdir -p "$dest/bin" "$dest/node"
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT

  install_binaries "$dest" "$WORK"
  install_locked "$dest" "$here"
  log "installed into $dest/bin"
}

main "$@"
