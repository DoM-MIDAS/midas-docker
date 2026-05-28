# midas-docker

Org-standard **base images** (Layers 1–2 of the [design](design.md)) for
agent-safe analysis projects. Project repos build their own Layer 3 image
`FROM` one of these.

Images are published to **GitHub Container Registry** under
`ghcr.io/dom-midas/` and are **public** — no auth needed to pull.

## Available images

| Image | What's in it | Use for |
| --- | --- | --- |
| [`r-bioc-singlecell`](images/r-bioc-singlecell/) | R 4.5.2 + Bioconductor 3.22; tidyverse, Seurat, scran/scater, DropletUtils, DESeq2, slingshot, ComplexHeatmap, iSEE, … (the GeneseeSC dependency stack) | single-cell / scRNA-seq projects |

> One base per *project type*, not per project. If a needed package is used by
> only one project, add it to that project's Layer 3 Dockerfile instead.

## Building a Layer 3 image (in a project repo)

Layer 3 = a single analysis project's image, built `FROM` one of the bases
above. Layer 3 Dockerfiles live in each project's own repo so dependencies
are explicit and local to the work.

### 1. Copy and adapt

Start from the worked example at
[`examples/layer3-smoke/Dockerfile`](examples/layer3-smoke/Dockerfile):

```dockerfile
# myproject/Dockerfile
FROM ghcr.io/dom-midas/r-bioc-singlecell:bioc3.22-ppm2026-04-01-r2

# project-specific packages — pak handles CRAN, Bioconductor, and GitHub in
# one call. CRAN/Bioc deps are pinned by the base image's PPM date and Bioc
# release; GitHub deps are pinned by commit SHA.
RUN R -q -e "pak::pkg_install( \
      c('lme4', 'emmeans', 'amcdavid/Genesee@<sha>'), \
      lib = '/opt/R/library', \
      upgrade = FALSE \
    )"
```

Two changes are typical: update the `FROM` tag if you want a different base,
and edit the `pak::pkg_install` list to your project's actual dependencies.

That's enough for a working Dockerfile. From here you have **two build paths,
and you'll use both at different times**.

### 2a. Local builds (dev iteration)

```bash
docker build -t myproject:dev .
docker run --rm -it myproject:dev R
```

No registry, no push, no credentials. The `FROM` image pulls anonymously
because the Layer 2 base is public. This is the right loop while the
Dockerfile is in flux.

### 2b. Canonical builds on GitHub Actions

When you want a reproducible-from-git-SHA image that teammates and HPC
nodes can pull, add a thin caller workflow that delegates to the
[`actions/build-image`](actions/build-image/) composite action exported by
this repo:

```yaml
# myproject/.github/workflows/build.yml
name: build
on:
  workflow_dispatch:
  push:
    tags: ['v*']

permissions:
  contents: read
  packages: write

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<sha>          # pin by SHA, same as elsewhere
      - id: meta
        run: |
          TAG=${GITHUB_REF#refs/tags/}
          [ "$TAG" = "$GITHUB_REF" ] && TAG="git-${GITHUB_SHA:0:7}"
          echo "tag=$TAG" >> "$GITHUB_OUTPUT"
      - uses: DoM-MIDAS/midas-docker/actions/build-image@<sha>
        with:
          image: ghcr.io/${{ github.repository_owner }}/${{ github.event.repository.name }}
          tags: ${{ steps.meta.outputs.tag }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

The composite action handles GHCR login, **fails fast if the tag already
exists** in the registry (within ~10 s, before disk cleanup or any build
work runs), builds the image, pushes it, and writes the digest into the
Actions run summary. On HPC, `apptainer pull docker://ghcr.io/.../<project>:<tag>`
then pulls the image anonymously.

> ⚠ **Do not invoke this workflow from `pull_request_target` or an
> untrusted-fork `pull_request` event.** Those triggers run with the base
> repo's secrets, which would hand a write-capable `GITHUB_TOKEN` to a
> Dockerfile an attacker controls. Stick to `workflow_dispatch`, tag pushes,
> or `pull_request` on same-repo branches.

### Tag vs digest

Within the org, tag-pinning is the default — the publish workflow refuses
to overwrite an existing tag, so the tag itself is a stable contract. If a
project wants the stricter "this exact image bytes" guarantee, substitute
`@sha256:<digest>`; the digest is printed in each build's Actions run
summary.

### Worked example

[`examples/layer3-smoke/`](examples/layer3-smoke/) is a Layer 3 that
depends on GeneseeSC + SeuratDisk pinned by SHA, with its own
*smoke r-bioc-singlecell layer 3* workflow that uses the same composite
action with `push: false`.

## Tagging scheme

Tags encode the two reproducibility inputs plus a build revision:

```
bioc<RELEASE>-ppm<YYYY-MM-DD>-r<N>
e.g.  bioc3.22-ppm2026-04-01-r1
```

- **Bioc release** and **PPM date** are the pinned inputs (CRAN frozen at the
  PPM date; Bioconductor frozen at the release).
- **Revision (`-rN`)** distinguishes rebuilds of the *same* tuple — e.g. a
  base-OS security patch. Bump it rather than overwriting a tag.
- **No `latest`.** Projects must pin a specific tag/digest so an org-base
  rebuild never silently changes a project's package versions.
- **Tags are immutable.** The publish workflow refuses to overwrite an
  existing tag and tells you to bump the revision. The check fires before
  any disk cleanup or build work, so a duplicate-tag attempt fails within
  ~10 s of the job starting rather than after a long build.

## Building & publishing a Layer 2 base

Builds run in **GitHub Actions** and push to GHCR using the workflow's
repo-scoped `GITHUB_TOKEN`. The publishing workflow
([build-r-bioc-singlecell.yml](.github/workflows/build-r-bioc-singlecell.yml))
is a thin caller of the [`actions/build-image`](actions/build-image/)
composite action — the same composite that Layer 3 project repos call. Per-
image specifics (the tag-derivation step that reads `BIOC_RELEASE` /
`PPM_DATE` out of the Dockerfile) stay in the caller; everything generic
(login, immutability check, buildx, push, digest summary) lives in the
composite action.

To cut a build: **Actions → "build r-bioc-singlecell" → Run workflow**, set
the `revision` (leave `push` checked). The workflow reads the Bioc release
and PPM date out of the Dockerfile, so the tag always matches what was
built.

### Changing what's in a base

This is expected to occur roughly twice a year.

Pins for R are mostly implicit in the Dockerfile (the lockfile) rather than being able to point at shas.  To update the pins:

- **Bump the PPM date** (pick up newer CRAN): edit `ARG PPM_DATE`, re-run.
- **Bump the Bioconductor release**: change the `FROM` digest *and*
  `ARG BIOC_RELEASE`. Re-resolve the digest with `scripts/resolve-pins.sh`.
- **Add a package**: append to `Imports:` in
  [`images/r-bioc-singlecell/manifest/DESCRIPTION`](images/r-bioc-singlecell/manifest/DESCRIPTION).
  Bump the `revision` on the next build. pak resolves CRAN, Bioconductor,
  and any `Remotes:` together; you don't choose where the package comes from.
- **Security rebuild, same inputs**: just bump the `revision` input.

`scripts/resolve-pins.sh` re-resolves the base-image digest and the Action
commit SHAs so they are never hand-copied:

```bash
scripts/resolve-pins.sh RELEASE_3_22
```

## Supply-chain controls

- Base image pinned by **digest**, not tag.
- Every GitHub Action pinned by **commit SHA**, not tag (see the `uses:` lines).
- A resolved `packages.txt` manifest is baked into each image at
  `${R_LIBS_SITE}/packages.txt` for auditing.
