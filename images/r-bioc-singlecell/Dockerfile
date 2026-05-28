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
#   - NO GitHub-sourced packages: those belong in a project's Layer 3 image,
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
# Site library is baked into the image and lives outside any future bind mount.
ENV R_LIBS_SITE=/opt/R/library
RUN mkdir -p /opt/R/library

# --- CRAN packages (pinned by PPM_DATE) --------------------------------------
# Stops the build loudly if anything fails to resolve, rather than shipping a
# silently incomplete library.
RUN R -q -e "pkgs <- c( \
      'tidyverse','data.table','arrow','duckdb', \
      'glue','fs','here','RcppTOML','jsonlite', \
      'knitr','rmarkdown','rmdformats', \
      'ggplot2','ggrepel','patchwork','scales','gt', \
      'Matrix','matrixStats','broom','lme4', \
      'Seurat','SeuratObject','harmony', \
      'rlang','withr','generics','remotes','BiocManager', \
      'roxyglobals','rstudioapi','rslurm', \
      'testthat','targets' \
    ); \
    install.packages(pkgs, lib = Sys.getenv('R_LIBS_SITE')); \
    miss <- setdiff(pkgs, rownames(installed.packages())); \
    if (length(miss)) stop('CRAN packages failed to install: ', paste(miss, collapse = ', '))"

# --- Bioconductor packages (pinned by the base image's Bioc release) ---------
RUN R -q -e "pkgs <- c( \
      'S4Vectors','SummarizedExperiment','SingleCellExperiment', \
      'scater','scran','DropletUtils','scds','scDblFinder', \
      'slingshot','tradeSeq','ComplexHeatmap','DESeq2','iSEE' \
    ); \
    BiocManager::install(pkgs, update = FALSE, ask = FALSE, lib = Sys.getenv('R_LIBS_SITE')); \
    miss <- setdiff(pkgs, rownames(installed.packages())); \
    if (length(miss)) stop('Bioconductor packages failed to install: ', paste(miss, collapse = ', '))"

# --- Resolved-version manifest (a build artifact, for auditing) --------------
RUN R -q -e "write.csv(installed.packages()[, c('Package','Version')], \
                       file.path(Sys.getenv('R_LIBS_SITE'), 'packages.txt'), \
                       row.names = FALSE)"

# --- Ephemeral user library for mid-session install.packages() ---------------
# Writable, image-independent, lost on container restart. Survivors get
# promoted into a project's Layer 3 Dockerfile.
RUN mkdir -p /home/r/R/library && chmod 777 /home/r/R/library
ENV R_LIBS_USER=/home/r/R/library

WORKDIR /workspace
CMD ["R"]
