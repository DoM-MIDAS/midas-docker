# Layer 3 smoke test (Python single-cell)

A minimal Layer 3 image whose only job is to confirm that the `py-singlecell`
base can host a realistic project: one extra single-cell package (`scrublet`,
doublet detection) on top of the baked scanpy stack, plus an end-to-end scanpy
pipeline (normalize → log1p → PCA → neighbors → leiden → umap).

This image is **never published** — the workflow builds it and discards it.
Build success (the pipeline check at the end of the Dockerfile) is the test.

## What it pins, and how

| Source | Pin |
| --- | --- |
| `ghcr.io/dom-midas/py-singlecell` | tag (`py3.13-…-rN`) |
| Project PyPI packages (scrublet) | version (`==`) |
| VCS packages | commit SHA (`git+https://…@<sha>`) |
| scanpy/anndata/leiden/… | inherited from the base (hash-pinned lockfile) |

The base is pinned by tag because the base workflow makes a best-effort attempt
to keep tags stable; a `@sha256:` pin is a one-line substitution for an
exact-bytes guarantee.

`louvain` and `scrublet` are deliberately **not** in the base (`louvain` has no
cp313 wheel; `scrublet` is an optional, unmaintained add-on). Adding them here
is exactly the Layer 3 pattern.

## Running the smoke test

Actions → **smoke py-singlecell layer 3** → *Run workflow*. It builds this
Dockerfile and reports the build result; no push, no GHCR clutter.
