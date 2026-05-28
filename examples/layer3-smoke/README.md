# Layer 3 smoke test

A minimal Layer 3 image whose only job is to confirm that the
`r-bioc-singlecell` base can host a realistic project: GeneseeSC plus
`amcdavid/seurat-disk-lazily` plus their transitive deps.

This image is **never published** — the workflow builds it and discards it.
Build success is the test.

## What it pins, and how

| Source | Pin |
| --- | --- |
| `ghcr.io/dom-midas/r-bioc-singlecell` | tag (`bioc3.22-ppm…-rN`) |
| GitHub packages (Genesee, SeuratDisk, GeneseeSC) | commit SHA |
| CRAN/Bioc packages | inherited from the base (PPM date + Bioc release) |

The base is pinned by tag because the base workflow enforces tag immutability;
a `@sha256:` pin is a one-line substitution if you need it.

## Running the smoke test

Actions → **smoke r-bioc-singlecell layer 3** → *Run workflow*. It builds this
Dockerfile and reports the build result; no push, no GHCR clutter.

## Refreshing the GitHub-package pins

```bash
scripts/resolve-pins.sh
```

prints the current `main`/`master` SHAs for the three repos. Update the
Dockerfile with the new values and re-run the smoke workflow.
