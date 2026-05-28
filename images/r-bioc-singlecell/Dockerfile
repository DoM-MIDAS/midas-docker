# =============================================================================
# Layer 2 org-analysis base: R / Bioconductor single-cell stack
#   ghcr.io/dom-midas/r-bioc-singlecell
#
# Built and published by .github/workflows/build-r-bioc-singlecell.yml.
# This Dockerfile is the lockfile: every input is pinned, so rebuilding from
# the same commit reproduces the same package set.
#
#   - base image  -> pinned by digest (RELEASE_3_22 => R 4.5.2, Bioc 3.22)
#   - CRAN pkgs   -> pinned by PPM snapshot date (see PPM_DATE below)
#   - Bioc pkgs   -> pinned by the Bioconductor release of the base image
#   - Generally no GitHub-sourced packages: those belong in a project's Layer 3 image,
#     where they are pinned by commit SHA.
# =============================================================================

# RELEASE_3_22 (R 4.5.2, Bioconductor 3.22). Multi-arch OCI index digest, so
# this line stays correct when an arm64 build is added later.
# Re-resolve with scripts/resolve-pins.sh after bumping the release.
FROM bioconductor/bioconductor_docker@sha256:e34177896c1579f66d48b756e4229b58237499183a089da084af72d7aba1d40a

# --- Reproducibility inputs (the workflow reads these to build the image tag) -
# Keep BIOC_RELEASE consistent with the RELEASE_X_Y of the base digest above.
ARG BIOC_RELEASE=3.22
# PPM CRAN snapshot. Pinned inside the Bioc 3.22 window (Oct 2025 - Apr 2026)
# so CRAN and Bioconductor stay mutually consistent, and before R 4.6 shipped.
ARG PPM_DATE=2026-04-01

# --- OCI provenance labels (values supplied by CI) ---------------------------
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG IMAGE_REVISION=1
LABEL org.opencontainers.image.title="r-bioc-singlecell" \
      org.opencontainers.image.description="MIDAS org base: R/Bioconductor single-cell analysis stack" \
      org.opencontainers.image.source="https://github.com/DoM-MIDAS/midas-docker" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.midas.layer="2" \
      org.midas.bioc-release="${BIOC_RELEASE}" \
      org.midas.ppm-date="${PPM_DATE}" \
      org.midas.image-revision="${IMAGE_REVISION}"

# --- System libraries --------------------------------------------------------
# bioconductor_docker already ships most of what this stack needs (HDF5, XML,
# cairo, fontconfig, pandoc). These cover the common gaps for igraph/leiden
# (GLPK) and a few Bioc packages (GSL). texlive is intentionally NOT installed:
# this base renders HTML reports; PDF-rendering projects add it in Layer 3.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglpk-dev \
      libgsl-dev \
 && rm -rf /var/lib/apt/lists/*

# --- R repositories: freeze CRAN to a PPM snapshot ---------------------------
# All install.packages() calls below resolve against PPM frozen at PPM_DATE,
# using prebuilt binaries for this image's Ubuntu codename (no compilation).
# BiocManager::repositories() supplies the matching Bioconductor release repos.
RUN CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")" \
 && printf '%s\n' \
      "options(repos = c(" \
      "  PPM = \"https://packagemanager.posit.co/cran/__linux__/${CODENAME}/${PPM_DATE}\"," \
      "  BioC = BiocManager::repositories()" \
      "))" \
      'options(Ncpus = max(1L, parallel::detectCores()))' \
      >> "${R_HOME}/etc/Rprofile.site"

# --- Library paths -----------------------------------------------------------
# /opt/R/library holds everything this Dockerfile installs — auditable
# separately from what the base image shipped (e.g. `ls /opt/R/library`).
#
# R_LIBS_SITE *replaces* the default site-library lookup, so we must list
# both paths: our /opt/R/library first (writable, takes precedence), and the
# base's /usr/local/lib/R/site-library second (read-only, ships BiocManager
# and the Bioc release stack). Drop the second path and R startup dies the
# next time Rprofile.site evaluates BiocManager::repositories().
# /usr/local/lib/R/site-library is the rocker/bioconductor convention.
ENV R_LIBS_SITE=/opt/R/library:/usr/local/lib/R/site-library
RUN mkdir -p /opt/R/library

# --- Dependency manifest -----------------------------------------------------
# manifest/DESCRIPTION is the requirements.in: it declares the top-level R
# and Bioconductor packages this image bakes. pak resolves it (Imports +
# transitive) against the PPM snapshot and Bioconductor release pinned
# above, in a single pass that handles CRAN and Bioc together, and installs
# in parallel into .libPaths()[1] = /opt/R/library (R_LIBS_USER is set
# later in the file, so /opt/R/library is currently first).
#
# Version-intent constraints (e.g. Seurat >= 4.0.4) belong in the
# DESCRIPTION's Imports; PPM_DATE provides the resolved-version pin.
COPY manifest /tmp/manifest

# pak itself: small, install once from PPM, then let it do the heavy lifting.
RUN R -q -e "install.packages('pak', lib = '/opt/R/library'); \
              stopifnot(requireNamespace('pak', quietly = TRUE))"

# pak::local_install_deps errors out if any dep fails, so a silent partial
# install is not a possible outcome. cache_clean removes the multi-hundred-MB
# download cache before this layer closes.
RUN R -q -e "pak::local_install_deps('/tmp/manifest', upgrade = TRUE); \
              pak::cache_clean()"

# --- Resolved-version manifest (a build artifact, for auditing) --------------
RUN R -q -e "write.csv(installed.packages()[, c('Package','Version')], \
                       file.path('/opt/R/library', 'packages.txt'), \
                       row.names = FALSE)"

# --- Ephemeral user library for mid-session install.packages() ---------------
# Writable, image-independent, lost on container restart. Survivors get
# promoted into a project's Layer 3 Dockerfile.
RUN mkdir -p /home/r/R/library && chmod 777 /home/r/R/library
ENV R_LIBS_USER=/home/r/R/library

WORKDIR /workspace
CMD ["R"]
