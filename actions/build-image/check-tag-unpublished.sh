#!/usr/bin/env bash
# Best-effort guard against overwriting an already-published tag.
#
# GHCR does NOT enforce tag immutability server-side, so this client-side check
# is the only thing standing between a rebuild and a silent overwrite. It is
# best-effort *by nature*: `docker buildx imagetools inspect` returns a generic
# non-zero exit for BOTH "manifest not found" (tag is genuinely free) and
# "registry error" (auth blip, rate-limit, 5xx, network), and the two can only
# be told apart by sniffing the message. So the policy is:
#
#   - tag DEFINITELY exists (exit 0)        -> abort the build (don't overwrite)
#   - tag DEFINITELY absent (404-class msg) -> proceed
#   - anything else (timeout, ambiguous)    -> WARN and proceed
#
# We only ever block when we are certain the tag exists; we never fail a build
# because the registry was briefly unreachable. A caller that needs an
# iron-clad "this exact image" guarantee should pin downstream FROM lines by
# @sha256:<digest> (printed in each build's run summary), not by tag.
#
# Usage:  check-tag-unpublished.sh "<phase label>"   # reads newline-separated
#                                                    # refs on stdin
set -euo pipefail

phase="${1:-check}"

while IFS= read -r ref; do
  [ -z "$ref" ] && continue
  out=""
  ec=0
  out="$(timeout 120 docker buildx imagetools inspect "$ref" 2>&1)" || ec=$?
  case "$ec" in
    0)
      echo "::error::${ref} already exists (${phase}). Bump the tag/revision," \
           "or pin downstream by @sha256 if you need an exact-bytes guarantee." >&2
      exit 1
      ;;
    124)
      echo "::warning::imagetools inspect timed out for ${ref} (${phase});" \
           "cannot confirm the tag is unpublished. Proceeding (best-effort)." >&2
      ;;
    *)
      if printf '%s' "$out" \
           | grep -qiE 'not found|manifest unknown|no such manifest|MANIFEST_UNKNOWN'; then
        : # Unambiguous "absent" — safe to proceed.
      else
        echo "::warning::imagetools inspect failed for ${ref} (${phase}, ec=${ec});" \
             "cannot confirm the tag is unpublished. Proceeding (best-effort): ${out}" >&2
      fi
      ;;
  esac
done

echo "Tag check (${phase}) complete."
