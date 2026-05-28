#!/usr/bin/env python3
"""List container images published under a GitHub org's GHCR namespace.

Two modes, chosen automatically:

  Authenticated (preferred)
    Uses the GitHub Packages REST API to enumerate every container package in
    the org, then GHCR (OCI) endpoints to fetch each image's labels. Needs a
    PAT in the git credential helper (the DoM-MIDAS@github.com entry) with
    `read:packages` scope.

  Anonymous fallback
    If no PAT is available, or the Packages API returns 401/403, falls back
    to KNOWN_PACKAGES below and the public OCI endpoints — which work without
    credentials for *public* packages. The fallback won't see private packages
    or packages not listed in KNOWN_PACKAGES, but it needs no auth.

Why the fallback exists: fine-grained PATs do not have a usable Packages read
permission, so users who refuse to issue org-unrestricted classic PATs need a
way to still see the published images. The script's repo is the authoritative
list of what we publish anyway.

Examples:

  scripts/list-images.py                       # everything in DoM-MIDAS
  scripts/list-images.py --layer 2             # only org.midas.layer=2
  scripts/list-images.py --all-tags            # every tag, not just latest
  scripts/list-images.py --org someother-org   # different org (must edit
                                               #   KNOWN_PACKAGES for fallback)
  scripts/list-images.py --json                # machine-readable

Exit codes: 0 on a successful, non-empty listing; 1 if any HTTP fetch
ultimately failed or no rows were produced (so scripted callers can
distinguish "empty org" from "auth was wrong").
"""
import argparse
import base64
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

GH_API = "https://api.github.com"
GHCR = "https://ghcr.io"

# Tightened: GitHub allows up to 39 chars, alnum + dashes, can't start with -.
ORG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
# GitHub package names: more permissive than orgs but still no slashes or
# query/auth metacharacters. Match what the GHCR registry allows in a path
# component, lowercase or original case.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

NET_TIMEOUT = 30  # seconds; per-request

# Anonymous-fallback discovery list. The Packages API is the preferred source;
# this list is consulted only when the API path is unavailable. Keep it in
# sync with images/<name>/Dockerfile when a new base lands.
KNOWN_PACKAGES = [
    "r-bioc-singlecell",
]


# ---------------------------------------------------------------------------
# urllib opener that strips Authorization on cross-host redirect
# ---------------------------------------------------------------------------

class _AuthScrubbingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Drop the Authorization header when a 3xx points at a different host.

    urllib's default behavior is to re-send the original headers — including
    Authorization — to the redirect target. GHCR routinely redirects blob
    fetches from ghcr.io to a CDN host (pkg-containers.githubusercontent.com)
    that uses presigned URLs; without this scrub, the Bearer token from the
    original request leaks to the CDN edge.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        orig_host = urllib.parse.urlsplit(req.full_url).netloc
        new_host = urllib.parse.urlsplit(newurl).netloc
        if orig_host != new_host:
            # The headers dict on the new Request is case-sensitive; clear all
            # plausible spellings.
            for key in list(new_req.headers):
                if key.lower() == "authorization":
                    del new_req.headers[key]
        return new_req


_OPENER = urllib.request.build_opener(_AuthScrubbingRedirectHandler())


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with _OPENER.open(req, timeout=NET_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_org(org):
    if not ORG_RE.match(org):
        sys.exit(f"error: invalid org name: {org!r}")


def _validate_package_name(name):
    if not NAME_RE.match(name):
        # Don't include the raw value (no chance to inject) — just refuse.
        raise ValueError("invalid package name from API response or KNOWN_PACKAGES")


# ---------------------------------------------------------------------------
# PAT retrieval
# ---------------------------------------------------------------------------

def fetch_pat(host="github.com", username="DoM-MIDAS"):
    """Pull the PAT from git's credential helper. Returns None on any failure.

    GIT_TERMINAL_PROMPT=0 prevents `git credential fill` from blocking on an
    interactive UI prompt when no credential is stored. We rstrip CR/LF
    because the Windows credential helper emits `password=...\\r\\n` and a
    bare `\\r` smuggled into an Authorization header is both broken and
    embarrassing.
    """
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input=f"protocol=https\nhost={host}\nusername={username}\n\n",
            capture_output=True,
            text=True,
            check=True,
            env=env,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):].rstrip("\r\n").strip()
    return None


# ---------------------------------------------------------------------------
# Authenticated path: GitHub Packages API
# ---------------------------------------------------------------------------

def list_packages_api(org, pat):
    """Yield every container package in `org` (paginated)."""
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    page = 1
    while True:
        url = (
            f"{GH_API}/orgs/{org}/packages"
            f"?package_type=container&per_page=100&page={page}"
        )
        batch = get_json(url, headers)
        if not batch:
            return
        for pkg in batch:
            yield pkg
        if len(batch) < 100:
            return
        page += 1


def tagged_versions_api(org, name, pat):
    """All tagged versions of a package, most-recently-updated first.

    Paginated like list_packages_api. Untagged versions (attestation
    manifests) are filtered out.
    """
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    out = []
    page = 1
    while True:
        url = (
            f"{GH_API}/orgs/{org}/packages/container/{name}/versions"
            f"?per_page=100&page={page}"
        )
        batch = get_json(url, headers)
        if not batch:
            break
        out.extend(
            v for v in batch
            if v.get("metadata", {}).get("container", {}).get("tags")
        )
        if len(batch) < 100:
            break
        page += 1
    out.sort(key=lambda v: v.get("updated_at", ""), reverse=True)
    return out


# ---------------------------------------------------------------------------
# Registry path: GHCR OCI endpoints. PAT-optional.
# ---------------------------------------------------------------------------

def registry_token(org_lower, name, pat=None):
    """Bearer pull token from ghcr.io. Anonymous when pat is None."""
    url = f"{GHCR}/token?scope=repository:{org_lower}/{name}:pull"
    headers = {}
    if pat:
        auth = base64.b64encode(f"{org_lower}:{pat}".encode()).decode()
        headers["Authorization"] = f"Basic {auth}"
    return get_json(url, headers)["token"]


def list_tags_registry(org_lower, name, token):
    """Tags reported by the OCI /tags/list endpoint."""
    url = f"{GHCR}/v2/{org_lower}/{name}/tags/list"
    try:
        data = get_json(url, {"Authorization": f"Bearer {token}"})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return data.get("tags") or []


def _pick_platform_manifest(index):
    """From an OCI image index, return the first manifest entry that looks
    like a real platform image, skipping attestation manifests."""
    for entry in index.get("manifests", []):
        platform = entry.get("platform") or {}
        artifact_type = entry.get("artifactType")
        if platform.get("os", "") in ("", "unknown"):
            continue
        if artifact_type and artifact_type.startswith("application/vnd.in-toto"):
            continue
        return entry["digest"]
    return None


def fetch_labels(org_lower, name, tag, token):
    """OCI labels for {org}/{name}:{tag}. Returns {} on any structural miss."""
    accept = ",".join([
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    ])
    headers = {"Authorization": f"Bearer {token}", "Accept": accept}
    manifest = get_json(f"{GHCR}/v2/{org_lower}/{name}/manifests/{tag}", headers)
    if "manifests" in manifest:
        per_arch = _pick_platform_manifest(manifest)
        if not per_arch:
            return {}
        manifest = get_json(
            f"{GHCR}/v2/{org_lower}/{name}/manifests/{per_arch}", headers
        )
    config = manifest.get("config")
    if not config or "digest" not in config:
        return {}
    blob = get_json(
        f"{GHCR}/v2/{org_lower}/{name}/blobs/{config['digest']}", headers
    )
    return (blob.get("config") or {}).get("Labels") or {}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def discover_packages(org, pat, warnings):
    if pat:
        try:
            infos = []
            for pkg in list_packages_api(org, pat):
                _validate_package_name(pkg["name"])
                infos.append((pkg["name"], pkg.get("visibility", "?")))
            return infos, pat
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                warnings.append(
                    f"Packages API returned {e.code}; using KNOWN_PACKAGES + "
                    f"anonymous OCI fallback."
                )
            else:
                warnings.append(f"Packages API error {e.code}; falling back.")
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            warnings.append(f"Packages API unreachable ({type(e).__name__}); "
                            "falling back.")
    else:
        warnings.append("no PAT in credential helper; using KNOWN_PACKAGES + "
                        "anonymous OCI fallback.")
    for name in KNOWN_PACKAGES:
        _validate_package_name(name)
    return [(name, "?") for name in KNOWN_PACKAGES], None


def _fresh_registry_token(org_lower, name, pat):
    """Wrap registry_token so callers can refresh on 401."""
    return registry_token(org_lower, name, pat)


def _safe_str(s):
    """Strip control chars so embedded newlines don't break table alignment."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(s))


def gather(org, pat, layer_filter, all_tags, warnings):
    org_lower = org.lower()
    package_infos, registry_pat = discover_packages(org, pat, warnings)

    rows = []
    for name, vis in package_infos:
        try:
            token = _fresh_registry_token(org_lower, name, registry_pat)
        except urllib.error.HTTPError as e:
            rows.append({
                "name": name, "tag": "-", "layer": "-", "visibility": vis,
                "description": f"(registry token: {e.code} — is the package "
                               f"public?)",
                "created": "-",
            })
            warnings.append(f"{name}: registry token returned {e.code}")
            continue
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            rows.append({
                "name": name, "tag": "-", "layer": "-", "visibility": vis,
                "description": f"(registry unreachable: {type(e).__name__})",
                "created": "-",
            })
            warnings.append(f"{name}: registry unreachable ({type(e).__name__})")
            continue

        # Tag enumeration: prefer the Packages API (gives sortable timestamps),
        # else use the OCI tags list and sort by image-created label afterwards.
        if registry_pat and pat:
            try:
                versions = tagged_versions_api(org, name, pat)
                tag_candidates = [
                    v["metadata"]["container"]["tags"][0] for v in versions
                ]
            except urllib.error.HTTPError:
                tag_candidates = list_tags_registry(org_lower, name, token)
        else:
            tag_candidates = list_tags_registry(org_lower, name, token)

        if not tag_candidates:
            rows.append({
                "name": name, "tag": "-", "layer": "-", "visibility": vis,
                "description": "(no tagged versions)", "created": "-",
            })
            continue

        candidates = []
        for tag in tag_candidates:
            try:
                labels = fetch_labels(org_lower, name, tag, token)
            except urllib.error.HTTPError as e:
                # GHCR pull tokens are short-lived. Refresh once on 401 and
                # retry; otherwise surface as a per-tag warning so the
                # operator notices.
                if e.code == 401:
                    try:
                        token = _fresh_registry_token(
                            org_lower, name, registry_pat
                        )
                        labels = fetch_labels(org_lower, name, tag, token)
                    except urllib.error.HTTPError as e2:
                        warnings.append(
                            f"{name}:{tag}: labels HTTP {e2.code} after retry"
                        )
                        continue
                else:
                    warnings.append(
                        f"{name}:{tag}: labels HTTP {e.code}"
                    )
                    continue
            except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
                warnings.append(
                    f"{name}:{tag}: labels unreachable ({type(e).__name__})"
                )
                continue
            candidates.append((tag, labels))
        candidates.sort(
            key=lambda c: c[1].get("org.opencontainers.image.created", ""),
            reverse=True,
        )
        if not all_tags:
            candidates = candidates[:1]

        for tag, labels in candidates:
            layer = labels.get("org.midas.layer", "-")
            if layer_filter is not None and str(layer) != str(layer_filter):
                continue
            rows.append({
                "name": _safe_str(
                    labels.get("org.opencontainers.image.title", name)
                ),
                "tag": _safe_str(tag),
                "layer": _safe_str(layer),
                "description": _safe_str(
                    labels.get("org.opencontainers.image.description", "")
                ),
                "visibility": vis,
                "created": _safe_str(
                    labels.get("org.opencontainers.image.created", "-")
                ),
            })
    return rows


def print_table(rows):
    if not rows:
        print("(no images matched)")
        return
    cols = ("name", "layer", "tag", "visibility", "description")
    headers = ("NAME", "LAYER", "LATEST TAG", "VIS", "DESCRIPTION")
    widths = [
        max(len(headers[i]), max(len(str(r[cols[i]])) for r in rows))
        for i in range(len(cols))
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for r in rows:
        print(fmt.format(*(str(r[c]) for c in cols)))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--org", default="DoM-MIDAS")
    ap.add_argument("--layer",
                    help="Filter to images with org.midas.layer=LAYER")
    ap.add_argument("--all-tags", action="store_true",
                    help="Show every tag instead of just the latest")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of a table")
    args = ap.parse_args()

    _validate_org(args.org)

    pat = fetch_pat()
    warnings = []
    try:
        rows = gather(args.org, pat, args.layer, args.all_tags, warnings)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            sys.exit(
                f"error: HTTP {e.code} during enumeration. The PAT in the\n"
                f"git credential helper (DoM-MIDAS@github.com) needs the\n"
                f"`read:packages` scope (classic PAT) or 'Packages: read'\n"
                f"(fine-grained PAT scoped to the {args.org} org)."
            )
        raise

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print_table(rows)

    # Nonzero exit on any partial-failure warning or empty result so scripted
    # callers can distinguish "all good" from "something was wrong."
    if warnings or not rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
