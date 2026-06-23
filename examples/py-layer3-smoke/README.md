# Layer 3 smoke test (Python)

A minimal Layer 3 image whose only job is to confirm that the
`py-analysis-base` base can host a realistic project: a couple of extra PyPI
packages (`networkx`, `tqdm`) plus their transitive deps, on top of the baked
scientific stack.

This image is **never published** — the workflow builds it and discards it.
Build success (the import checks at the end of the Dockerfile) is the test.

## What it pins, and how

| Source | Pin |
| --- | --- |
| `ghcr.io/dom-midas/py-analysis-base` | tag (`py3.13-…-rN`) |
| Project PyPI packages (networkx, tqdm) | version (`==`) |
| VCS packages | commit SHA (`git+https://…@<sha>`) |
| numpy/pandas/scipy/sklearn/… | inherited from the base (hash-pinned lockfile) |

The base is pinned by tag because the base workflow enforces tag immutability;
a `@sha256:` pin is a one-line substitution if you need it.

Layer 3 is the project's own, less-strict layer, so `--require-hashes` is not
used here — the heavy, security-sensitive stack is already hash-pinned in the
base. Projects that want hash discipline on their extra deps can compile their
own `requirements.txt` the same way the base does
(`scripts/compile-py-requirements.sh` is a usable template).

## Running the smoke test

Actions → **smoke py-analysis-base layer 3** → *Run workflow*. It builds this
Dockerfile and reports the build result; no push, no GHCR clutter.
