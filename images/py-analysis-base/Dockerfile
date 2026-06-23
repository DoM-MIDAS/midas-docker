# =============================================================================
# Layer 2 org-analysis base: Python scientific stack
#   ghcr.io/dom-midas/py-analysis-base
#
# Built and published by .github/workflows/build-py-analysis-base.yml.
# The committed lockfile (manifest/requirements.txt) is what pins this image:
# every transitive dependency is pinned by version AND sha256, and installed
# with `pip install --require-hashes`, which refuses any package not pinned by
# hash. Rebuilding from the same commit reproduces the same package set.
#
#   - base image  -> pinned by digest (python:3.13-slim)
#   - PyPI pkgs   -> pinned by hash in manifest/requirements.txt, which was
#                    compiled with `uv pip compile --generate-hashes
#                    --exclude-newer <PYPI_DATE>` (see scripts/compile-py-
#                    requirements.sh). --exclude-newer is the PyPI-snapshot
#                    analog of the R image's PPM_DATE.
#   - No VCS-sourced packages: those belong in a project's Layer 3 image,
#     where they are pinned by commit SHA.
#
# This is pure-pip scientific Python; no conda. Heavy native deps that once
# argued for conda have Docker-native answers instead: GPU work uses an
# nvidia/cuda base image and/or CUDA-bundling wheels (torch, jax[cuda12]);
# system libraries come from apt; a tool shipped only as a prebuilt binary is
# COPYd in from its upstream release.
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
LABEL org.opencontainers.image.title="py-analysis-base" \
      org.opencontainers.image.description="MIDAS org base: Python scientific analysis stack (numpy/pandas/scipy/sklearn/pyarrow/polars/jupyter)" \
      org.opencontainers.image.source="https://github.com/DoM-MIDAS/midas-docker" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.midas.layer="2" \
      org.midas.py-version="${PY_VERSION}" \
      org.midas.pypi-date="${PYPI_DATE}" \
      org.midas.image-revision="${IMAGE_REVISION}"

# --- System libraries --------------------------------------------------------
# python:slim is minimal; these cover the common gaps for the scientific stack:
# build-essential for any sdist that has no wheel for this platform, libhdf5-dev
# for h5py-class extensions a project may add in Layer 3, and pandoc for
# notebook/report export. texlive is intentionally NOT installed (HTML reports
# only); PDF-rendering projects add it in Layer 3.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libhdf5-dev \
      pandoc \
 && rm -rf /var/lib/apt/lists/*

# --- Virtualenv outside any future bind mount --------------------------------
# Install into a system-level prefix so a project bind-mounting /workspace
# cannot shadow the interpreter's site-packages. Putting $VIRTUAL_ENV/bin on
# PATH makes `python`/`pip` resolve to the venv without an explicit activate.
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# --- Dependency install: the hash-pinned lockfile ----------------------------
# manifest/requirements.txt pins every transitive dependency by version +
# sha256. --require-hashes refuses to install anything not pinned by hash, so a
# silent substitution (a typosquat, a yanked-and-replaced version) cannot slip
# in. pip resolves the architecture-appropriate wheel for THIS container's
# platform from the hashes recorded for the pinned version.
COPY manifest/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# --- Resolved-version manifest (a build artifact, for auditing) --------------
# Mirrors the R image's packages.txt: a flat record of exactly what landed,
# auditable with `cat /opt/packages.txt` without invoking pip.
RUN pip freeze > /opt/packages.txt

WORKDIR /workspace
CMD ["python"]
