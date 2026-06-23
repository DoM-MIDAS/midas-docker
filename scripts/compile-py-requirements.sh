#!/usr/bin/env bash
# Compile a Python base image's lockfile from its requirements.in.
#
# This is the Python analog of "bumping ARG PPM_DATE": it re-resolves the
# stack against a PyPI snapshot and writes a fully pinned, hash-locked
# requirements.txt that the Dockerfile installs with
# `pip install --require-hashes`.
#
#   - --universal       resolution carries environment markers, so one lockfile
#                       installs correctly on any platform (the Linux container
#                       included) regardless of where it was compiled.
#   - --generate-hashes pins every distribution by sha256.
#   - --exclude-newer   freezes resolution to distributions published on or
#                       before PYPI_DATE. This is the PPM_DATE analog.
#
# Works for any image under images/<name>/manifest/requirements.in (e.g.
# py-analysis-base, py-singlecell). Requires uv (https://docs.astral.sh/uv/).
# Read-only except for the output requirements.txt, which is meant to be
# committed.
#
# Usage:
#   scripts/compile-py-requirements.sh                              # py-analysis-base, defaults
#   scripts/compile-py-requirements.sh 2026-11 3.13                 # PYPI month, py version
#   scripts/compile-py-requirements.sh --image py-singlecell 2026-05 3.13
set -euo pipefail

IMAGE="py-analysis-base"
if [ "${1:-}" = "--image" ]; then
  IMAGE="${2:?--image needs a value}"
  shift 2
fi

# Defaults mirror the ARGs in images/<image>/Dockerfile.
PYPI_DATE="${1:-2026-05}"
PY_VERSION="${2:-3.13}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../images/${IMAGE}/manifest"

if [ ! -f "${MANIFEST_DIR}/requirements.in" ]; then
  echo "error: no requirements.in at ${MANIFEST_DIR} (is --image '${IMAGE}' right?)" >&2
  exit 1
fi

# --exclude-newer wants a full timestamp. PYPI_DATE is a month (YYYY-MM) or a
# day (YYYY-MM-DD); expand a bare month to "first of the *next* month" so the
# whole named month is included.
case "$PYPI_DATE" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9])
    y="${PYPI_DATE%-*}"; m="${PYPI_DATE#*-}"
    if [ "$m" = "12" ]; then nexty=$((y + 1)); nextm="01"; else nexty="$y"; nextm="$(printf '%02d' $((10#$m + 1)))"; fi
    EXCLUDE_NEWER="${nexty}-${nextm}-01T00:00:00Z"
    ;;
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
    EXCLUDE_NEWER="${PYPI_DATE}T00:00:00Z"
    ;;
  *)
    echo "error: PYPI_DATE must be YYYY-MM or YYYY-MM-DD, got: '$PYPI_DATE'" >&2
    exit 1
    ;;
esac

echo "Compiling ${MANIFEST_DIR}/requirements.txt"
echo "  image          : ${IMAGE}"
echo "  python-version : ${PY_VERSION}"
echo "  exclude-newer  : ${EXCLUDE_NEWER}  (PYPI_DATE=${PYPI_DATE})"

# Run from the manifest dir so the command uv records in the file header uses
# bare relative paths (reproducible across machines), not absolute ones.
cd "${MANIFEST_DIR}"
uv pip compile requirements.in \
  --universal \
  --python-version "${PY_VERSION}" \
  --generate-hashes \
  --exclude-newer "${EXCLUDE_NEWER}" \
  --no-annotate \
  --output-file requirements.txt

echo "Done. Review the diff, then bump ARG PYPI_DATE / PY_VERSION in the"
echo "Dockerfile to match and commit both files together."
