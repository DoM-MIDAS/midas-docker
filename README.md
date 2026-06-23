# midas-docker

Org-standard **base images** (Layers 1–2) for agent-safe analysis projects.
Project repos build their own Layer 3 image `FROM` one of these. The
project-side tooling and the overall design live in the companion **sandy**
repo.

Images are published to **GitHub Container Registry** under
`ghcr.io/dom-midas/` and are **public** — no auth needed to pull.

## Available images

| Image | What's in it | Use for |
| --- | --- | --- |
| [`r-bioc-singlecell`](images/r-bioc-singlecell/) | R 4.5.2 + Bioconductor 3.22; tidyverse, Seurat, scran/scater, DropletUtils, DESeq2, slingshot, ComplexHeatmap, iSEE, … (the GeneseeSC dependency stack) | single-cell / scRNA-seq projects |
| [`py-analysis-base`](images/py-analysis-base/) | Python 3.13; numpy, pandas, scipy, scikit-learn, pyarrow, polars, matplotlib, seaborn, jupyter, pytest (hash-pinned) | general scientific / stats / ML Python projects |
| [`py-singlecell`](images/py-singlecell/) | Python 3.13; scanpy (w/ built-in `sc.pp.scrublet` doublets), anndata, mudata, leidenalg, igraph, harmonypy, umap-learn, scikit-image/-misc, celltypist, gseapy, h5py + the scientific stack (hash-pinned). Standalone sibling of py-analysis-base (anndata pins pandas<3) | single-cell / scRNA-seq Python (scanpy) projects |

> One base per *project type*, not per project. If a needed package is used by
> only one project, add it to that project's Layer 3 Dockerfile instead.

To see what's actually in the registry right now — tags, digests, OCI
descriptions — run [`scripts/list-images.py`](scripts/list-images.py). It
prefers a PAT from `git credential` (the `DoM-MIDAS@github.com` entry with
`read:packages`) to enumerate every package in the org; if no PAT is
available it falls back to a hardcoded `KNOWN_PACKAGES` list and anonymous
GHCR endpoints, which only see public packages. Useful flags: `--layer 2`
to filter by layer label, `--all-tags` for every tag instead of just
latest, `--json` for machine-readable output.

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

Within the org, tag-pinning is the convenient default and the publish
workflow makes a **best-effort** attempt to keep tags stable (it aborts a
build when it can confirm the tag already exists). But **GHCR does not
enforce tag immutability server-side**, so a tag is a *convention*, not a
hard guarantee — a determined or careless push could still move it.

If a project needs an iron-clad "this exact image bytes" contract, pin by
digest: substitute `@sha256:<digest>` for the tag. The digest is printed in
each build's Actions run summary and never moves. Use it for anything where
silent drift would be unacceptable (HPC pipelines, published results).

### Worked example

[`examples/layer3-smoke/`](examples/layer3-smoke/) is an R Layer 3 that
depends on GeneseeSC + SeuratDisk pinned by SHA, with its own
*smoke r-bioc-singlecell layer 3* workflow that uses the same composite
action with `push: false`.
[`examples/py-layer3-smoke/`](examples/py-layer3-smoke/) is the Python
equivalent on top of `py-analysis-base`, with the *smoke py-analysis-base
layer 3* workflow.

## Tagging scheme

Tags encode the reproducibility inputs plus a build revision. The inputs differ
by language, but the shape is the same: `<inputs>-r<N>`.

```
r-bioc-singlecell:  bioc<RELEASE>-ppm<YYYY-MM-DD>-r<N>
e.g.                bioc3.22-ppm2026-04-01-r1

py-analysis-base:   py<VERSION>-<YYYY-MM>-r<N>
e.g.                py3.13-2026-05-r1
```

- **R inputs:** Bioc release + PPM date (CRAN frozen at the PPM date;
  Bioconductor frozen at the release).
- **Python inputs:** Python version + PyPI date. The PyPI date is the
  `--exclude-newer` snapshot the hash-pinned lockfile was compiled against — the
  PPM-date analog. The lockfile (`manifest/requirements.txt`, every dep pinned
  by sha256) is the actual contract; the date just records when it was cut.
- **Revision (`-rN`)** distinguishes rebuilds of the *same* tuple — e.g. a
  base-OS security patch. Bump it rather than overwriting a tag.
- **No `latest`.** Projects must pin a specific tag/digest so an org-base
  rebuild never silently changes a project's package versions.
- **Tags are stable by convention (best-effort), not enforced.** GHCR has no
  server-side tag immutability, so the publish workflow does a client-side
  check and aborts when it can confirm the tag already exists (within ~10 s,
  before any disk cleanup or build). It tells you to bump the revision. This
  catches the honest-mistake case; it is not a security boundary. For a hard
  guarantee, pin downstream by `@sha256:<digest>` (see *Tag vs digest*).

## Building & publishing a Layer 2 base

Builds run in **GitHub Actions** and push to GHCR using the workflow's
repo-scoped `GITHUB_TOKEN`. There are three layers, each owning strictly less:

- **Per-image caller** ([build-r-bioc-singlecell.yml](.github/workflows/build-r-bioc-singlecell.yml),
  [build-py-analysis-base.yml](.github/workflows/build-py-analysis-base.yml)) —
  just the `workflow_dispatch` inputs, the concurrency group, and the
  image-class-specific tag shape (which ARGs encode the inputs, the tag
  template, its regex). A dozen lines, no logic.
- **Reusable workflow** ([_build-base-image.yml](.github/workflows/_build-base-image.yml))
  — the shared build mechanics: checkout, tag derivation from the Dockerfile's
  pinned ARGs, build-date stamping, hand-off. Both callers share this one file,
  so the parsing/validation logic exists once.
- **Composite action** ([`actions/build-image`](actions/build-image/)) — the
  generic registry plumbing (login, best-effort tag check, buildx, push, digest
  summary). The same composite that Layer 3 project repos call directly.

To cut a build: **Actions → "build r-bioc-singlecell"** (or **"build
py-analysis-base"**) **→ Run workflow**, set the `revision` (leave `push`
checked). The workflow reads the pinned inputs out of the Dockerfile, so the
tag always matches what was built.

### Changing what's in a base

This is expected to occur roughly twice a year.

Pins are mostly implicit in the Dockerfile / lockfile rather than pointing at
SHAs. To update them:

**`r-bioc-singlecell`** (R/Bioc; pins are implicit in the Dockerfile):

- **Bump the PPM date** (pick up newer CRAN): edit `ARG PPM_DATE`, re-run.
- **Bump the Bioconductor release**: change the `FROM` digest *and*
  `ARG BIOC_RELEASE`. Re-resolve the digest with `scripts/resolve-pins.sh`.
- **Add a package**: append to `Imports:` in
  [`images/r-bioc-singlecell/manifest/DESCRIPTION`](images/r-bioc-singlecell/manifest/DESCRIPTION).
  Bump the `revision` on the next build. pak resolves CRAN, Bioconductor,
  and any `Remotes:` together; you don't choose where the package comes from.
- **Security rebuild, same inputs**: just bump the `revision` input.

**`py-analysis-base`** and **`py-singlecell`** (Python/PyPI; the committed
hash-pinned lockfile is the pin). Both use the same flow — pass `--image
<name>` to the compile script (default is `py-analysis-base`):

- **Bump the PyPI date** (pick up newer PyPI): run
  `scripts/compile-py-requirements.sh --image <name> <YYYY-MM>` to recompile
  `manifest/requirements.txt`, then set `ARG PYPI_DATE` to match.
- **Bump the Python version**: change the `FROM` digest *and* `ARG PY_VERSION`,
  recompile the lockfile with the new version, re-resolve the digest with
  `scripts/resolve-pins.sh`.
- **Add a package**: append to that image's `manifest/requirements.in`,
  recompile the lockfile, bump the `revision`.
- **Security rebuild, same inputs**: just bump the `revision` input.

> `py-singlecell` is a **standalone sibling**, not a child of
> `py-analysis-base`: anndata pins `pandas<3` while the generic base rides
> pandas 3.0, so they can't share a frozen base. Both bases currently resolve
> to all-wheels on the amd64 build target; if a dependency has no wheel there
> (e.g. `louvain` has no cp313 wheel), the default choice is to drop it to
> Layer 3 rather than pull in a source build.

`scripts/resolve-pins.sh` re-resolves the base-image digest and the Action
commit SHAs so they are never hand-copied:

```bash
scripts/resolve-pins.sh RELEASE_3_22
```

## Supply-chain controls

- Base image pinned by **digest**, not tag.
- Every GitHub Action pinned by **commit SHA**, not tag (see the `uses:` lines).
- `py-analysis-base` installs with `pip install --require-hashes`, so every
  PyPI dependency is pinned by **sha256** and any unpinned package is refused.
- A resolved package manifest is baked into each image for auditing:
  `${R_LIBS_SITE}/packages.txt` (R) and `/opt/packages.txt` (Python).
