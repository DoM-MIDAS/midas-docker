#!/usr/bin/env bash
# Resolve the SHA pins this repo depends on, so they are never hand-copied.
#
#   - base image digests     (Docker Hub / OCI registry API)
#   - GitHub Action SHAs     (commit a tag points to; git ls-remote)
#   - Project GitHub deps    (head of a branch; git ls-remote)
#
# Read-only: prints values, changes nothing. Requires curl and git.
#
# The three primitives are defined as functions so callers (this script, other
# scripts, or you at the shell) can compose them. The data — which repos to
# resolve — lives in flat arrays at the bottom.
set -euo pipefail

# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

# Print the manifest digest for <repo>:<tag> on Docker Hub.
#   docker_digest bioconductor/bioconductor_docker RELEASE_3_22
# -> sha256:e34177...
docker_digest() {
  local repo="$1" tag="$2"
  local token
  token="$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:${repo}:pull" \
            | grep -o '"token":"[^"]*"' | sed 's/"token":"//;s/"//')"
  curl -fsS -o /dev/null -D - \
    -H "Authorization: Bearer ${token}" \
    -H "Accept: application/vnd.oci.image.index.v1+json" \
    -H "Accept: application/vnd.docker.distribution.manifest.list.v2+json" \
    -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
    "https://registry-1.docker.io/v2/${repo}/manifests/${tag}" \
    | grep -i '^docker-content-digest:' | tr -d '\r' | awk '{print $2}'
}

# Print the commit SHA a Git tag points to (deref annotated tags via ^{}).
#   action_sha actions/checkout v6.0.2
# -> de0fac2e4500...
action_sha() {
  local repo="$1" tag="$2"
  git ls-remote "https://github.com/${repo}" \
      "refs/tags/${tag}^{}" "refs/tags/${tag}" \
    | head -1 | awk '{print $1}'
}

# Print the head commit SHA of a branch.
#   branch_head amcdavid/GeneseeSC main
# -> ff5d5bcd1657...
branch_head() {
  local repo="$1" branch="$2"
  git ls-remote "https://github.com/${repo}" "refs/heads/${branch}" \
    | awk '{print $1}'
}

# ---------------------------------------------------------------------------
# What we pin
# ---------------------------------------------------------------------------

# Base images: "<repo> <tag>"
BASE_IMAGES=(
  "bioconductor/bioconductor_docker ${1:-RELEASE_3_22}"
)

# GitHub Actions used in workflows: "<repo> <tag>"
ACTIONS=(
  "actions/checkout v6.0.2"
  "docker/setup-buildx-action v4.1.0"
  "docker/login-action v4.2.0"
  "docker/build-push-action v7.2.0"
  "docker/setup-qemu-action v4.1.0"
)

# Project GitHub deps (examples/layer3-smoke): "<repo> <branch>"
GH_DEPS=(
  "amcdavid/Genesee main"
  "amcdavid/seurat-disk-lazily master"
  "amcdavid/GeneseeSC main"
)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

echo "== Base images =="
for entry in "${BASE_IMAGES[@]}"; do
  read -r repo tag <<<"$entry"
  printf 'FROM %s@%s  # %s\n' "$repo" "$(docker_digest "$repo" "$tag")" "$tag"
done
echo

echo "== GitHub Actions =="
for entry in "${ACTIONS[@]}"; do
  read -r repo tag <<<"$entry"
  printf 'uses: %s@%s  # %s\n' "$repo" "$(action_sha "$repo" "$tag")" "$tag"
done
echo

echo "== Layer 3 GitHub deps (smoke test) =="
for entry in "${GH_DEPS[@]}"; do
  read -r repo branch <<<"$entry"
  printf '%s@%s  # %s\n' "$repo" "$(branch_head "$repo" "$branch")" "$branch"
done
