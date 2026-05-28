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

## Using a base image in a project (Layer 3)

Pick a tag from the release notes and `FROM` it:

```dockerfile
# myproject/Dockerfile
FROM ghcr.io/dom-midas/r-bioc-singlecell:bioc3.22-ppm2026-04-01-r1

# project-specific packages (CRAN/Bioc pinned by the inherited PPM date;
# GitHub-only packages pinned by commit SHA)
RUN R -q -e "install.packages(c('lme4','emmeans'), lib = Sys.getenv('R_LIBS_SITE'))"
RUN R -q -e "remotes::install_github('amcdavid/Genesee@<sha>', lib = Sys.getenv('R_LIBS_SITE'))"
```

**Tag vs digest.** Within the org, tag-pinning is the default — the base
workflow refuses to overwrite an existing tag, so the tag is itself a stable
contract. If a project wants the stricter "this exact image bytes" guarantee,
substitute `@sha256:<digest>`; the digest is printed in each build's Actions
run summary.

A worked smoke-test Layer 3 (GeneseeSC + SeuratDisk pinned by SHA) lives in
[`examples/layer3-smoke/`](examples/layer3-smoke/) and has its own
*smoke r-bioc-singlecell layer 3* workflow.

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
- **Tags are immutable.** The build workflow refuses to overwrite an existing
  tag and tells you to bump the revision.

## Building / publishing

Builds run in **GitHub Actions** and push to GHCR using the workflow's
repo-scoped `GITHUB_TOKEN` — no personal access token, no credentials on any
developer's machine.

To cut a build: **Actions → "build r-bioc-singlecell" → Run workflow**, set the
`revision` (leave `push` checked). The workflow reads the Bioc release and PPM
date out of the Dockerfile, so the tag always matches what was built.

### Changing what's in a base

Everything is pinned in the Dockerfile (the lockfile):

- **Bump the PPM date** (pick up newer CRAN): edit `ARG PPM_DATE`, re-run.
- **Bump the Bioconductor release**: change the `FROM` digest *and*
  `ARG BIOC_RELEASE`. Re-resolve the digest with `scripts/resolve-pins.sh`.
- **Add a package**: add it to the CRAN or Bioc list in the Dockerfile.
- **Security rebuild, same inputs**: just bump the `revision` input.

`scripts/resolve-pins.sh` re-resolves the base-image digest and the Action
commit SHAs so they are never hand-copied:

```bash
scripts/resolve-pins.sh RELEASE_3_22
```

## Supply-chain controls

- Base image pinned by **digest**, not tag.
- Every GitHub Action pinned by **commit SHA**, not tag (see the `uses:` lines).
- Builds publish **SLSA provenance** and an **SBOM** attestation.
- A resolved `packages.txt` manifest is baked into each image at
  `${R_LIBS_SITE}/packages.txt` for auditing.
