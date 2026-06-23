# =============================================================================
# Layer 2 org-analysis base: Python single-cell stack (scanpy)
#   ghcr.io/dom-midas/py-singlecell
#
# The Python sibling of r-bioc-singlecell. Built and published by
# .github/workflows/build-py-singlecell.yml. The committed lockfile
# (manifest/requirements.txt) is the pin: every transitive dependency is pinned
# by version AND sha256 and installed with `pip install --require-hashes`, which
# refuses any package not pinned by hash. Same commit -> same package set.
#
#   - base image  -> pinned by digest (python:3.13-slim)
#   - PyPI pkgs   -> pinned by hash in manifest/requirements.txt, compiled with
#                    `uv pip compile --generate-hashes --exclude-newer <PYPI_DATE>`
#                    (scripts/compile-py-requirements.sh --image py-singlecell).
#   - No VCS-sourced packages: those belong in a project's Layer 3 image,
#     pinned by commit SHA.
#
# This is a STANDALONE sibling of py-analysis-base, NOT a child of it: anndata
# pins pandas<3 (single-cell ecosystem isn't on pandas 3 yet) while
# py-analysis-base rides pandas 3.0, so they cannot share a frozen base.
# Resolving the whole stack here lets scanpy's constraints drive one coherent
# pin set (this image lands on pandas 2.3.x).
#
# Scope: CPU scanpy. GPU single-cell (rapids-singlecell/cupy) belongs on a
# separate nvidia/cuda base; scvi-tools (pulls torch) belongs in Layer 3.
# =============================================================================

# python:3.13-slim, multi-arch OCI index digest so this line stays correct when
# an arm64 build is added later. Re-resolve with scripts/resolve-pins.sh.
FROM python@sha256:c33f0bc4364a6881bed1ec0cc2665e6c53c87a43e774aaeab88e6f17af105e4f

# --- Reproducibility inputs (the workflow reads these to build the image tag) -
ARG PY_VERSION=3.13
# PyPI snapshot: the --exclude-newer date the lockfile was compiled against.
# Keep consistent with the header of manifest/requirements.txt.
ARG PYPI_DATE=2026-05

# --- OCI provenance labels (values supplied by CI) ---------------------------
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG IMAGE_REVISION=1
LABEL org.opencontainers.image.title="py-singlecell" \
      org.opencontainers.image.description="MIDAS org base: Python single-cell stack (scanpy, anndata, mudata, leiden, umap; harmonypy/scanorama/bbknn batch; scrublet doublets; celltypist; decoupler/gseapy; soupx-python; scirpy; plotnine)" \
      org.opencontainers.image.source="https://github.com/DoM-MIDAS/midas-docker" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.midas.layer="2" \
      org.midas.py-version="${PY_VERSION}" \
      org.midas.pypi-date="${PYPI_DATE}" \
      org.midas.image-revision="${IMAGE_REVISION}"

# --- System libraries --------------------------------------------------------
# python:slim is minimal. build-essential covers any sdist without a wheel for
# this platform; libhdf5-dev covers an h5py/loom build in a downstream Layer 3
# (the baked h5py wheel bundles its own HDF5); pandoc covers notebook/report
# export. The scanpy native stack (numba/llvmlite, igraph, leidenalg) ships
# manylinux wheels, so no extra system libs are needed for the base itself.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libhdf5-dev \
      pandoc \
 && rm -rf /var/lib/apt/lists/*

# --- Virtualenv outside any future bind mount --------------------------------
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# --- Dependency install: the hash-pinned lockfile ----------------------------
# --require-hashes refuses anything not pinned by sha256 (typosquat,
# yanked-and-replaced version). --only-binary=:all: makes wheels the default, so
# a missing-wheel package fails loudly instead of silently triggering a source
# build with un-pinned PEP 517 build deps.
#
# --no-binary names a SHORT, deliberate allowlist of packages we DO build from
# source because they have no cp313 wheel but are cheap, safe builds: airr,
# docrep, fbpca are pure-Python; annoy is header-only C++ that compiles with
# build-essential (no extra system libs). Their sdists are still hash-pinned by
# --require-hashes, so the source we build is verified. Adding anything here is
# a conscious decision — keep it in sync with manifest/requirements.in. A
# package needing a real system library (e.g. pycairo -> libcairo2-dev) would
# go here AND add an apt line above; none currently do (pycairo is Windows-only
# and never installs on this base).
COPY manifest/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --require-hashes \
      --only-binary=:all: --no-binary airr,annoy,docrep,fbpca \
      -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# --- Resolved-version manifest (a build artifact, for auditing) --------------
RUN pip freeze > /opt/packages.txt

WORKDIR /workspace
CMD ["python"]
