# Sourced by deploy.sh and e2e.sh: run an image build, and when it fails with
# the signature of a broken BuildKit cache, say so and how to clear it.
#
#   build_or_explain docker build -t klopot:x .     # prints the last lines; returns the build's status
#   BUILD_QUIET=1 build_or_explain …                # prints nothing on success
#
# The signatures (seen on the production host 2026-11-16/17, Docker 29 with
# the containerd image store): `lease "…": not found`, or `failed to walk …
# io.containerd.snapshotter.v1.overlayfs/snapshots/N: no such file or
# directory`. They are not about the code: containerd's garbage collector
# removed snapshots a build still needed — every time right after a container
# was removed twice (`docker run --rm` + `docker rm -f`), which these scripts no
# longer do. `docker builder prune -a` clears it (build cache only).
# shellcheck shell=bash

build_or_explain() {
  local log status
  log="$(mktemp)"
  "$@" >"$log" 2>&1
  status=$?
  if [ "$status" -eq 0 ]; then
    [ -n "${BUILD_QUIET:-}" ] || tail -5 "$log"
  else
    tail -5 "$log" >&2
    if grep -qE 'lease "[^"]*": not found|failed to walk|io\.containerd\.snapshotter\.v1\.overlayfs/snapshots/[0-9]+: no such file' "$log"; then
      echo "-> BuildKit's cache is broken on this host, not the code. Clear it with" >&2
      echo "   'docker builder prune -a' (build cache only — no image or container is touched) and build again." >&2
    fi
  fi
  rm -f "$log"
  return "$status"
}
