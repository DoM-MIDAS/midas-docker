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
# Every CRAN install below must resolve against PPM frozen at PPM_DATE, using
# prebuilt binaries for this image's Ubuntu codename (no compilation). This is
# subtler than it looks because pak is what actually does the installing:
#
#   1. pak only recognises a repo as CRAN if it is *named* "CRAN". A repo named
#      anything else (e.g. "PPM") is treated as a generic cranlike repo, and pak
#      then appends its OWN default CRAN (cran.rstudio.com, undated/latest) so it
#      has a canonical CRAN to resolve against. pak picks the highest version
#      across all repos, so that latest mirror silently wins over the snapshot.
#   2. BiocManager::repositories() returns the Bioc repos PLUS its own CRAN entry
#      pointing at latest CRAN — a second undated mirror, even if we name ours
#      "CRAN". So we must overwrite that entry, not sit beside it.
#
# Hence: build the repo set from BiocManager::repositories() and force its CRAN
# entry to the dated snapshot. Result is exactly one CRAN repo == the snapshot,
# and pak adds no latest mirror. The check below (pak::repo_get) enforces this.
RUN CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")" \
 && printf '%s\n' \
      'local({' \
      "  ppm <- \"https://packagemanager.posit.co/cran/__linux__/${CODENAME}/${PPM_DATE}\"" \
      '  repos <- BiocManager::repositories()' \
      '  repos[["CRAN"]] <- ppm' \
      '  options(repos = repos)' \
      '})' \
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

# --- Repository pin assertion (fail the build if the snapshot is bypassed) ----
# pak::repo_get() returns the exact repo set pak will resolve against, INCLUDING
# any latest-CRAN mirror pak auto-injects or that BiocManager smuggles in. We
# assert: exactly one CRAN-type repo, it IS the PPM_DATE snapshot, and no known
# latest mirror appears anywhere. If a future edit renames the repo, drops the
# CRAN override, or bumps PPM_DATE inconsistently, this stops the build here —
# before the manifest install bakes latest packages into the image.
RUN R -q -e "ppm_date <- '${PPM_DATE}'; \
    rg <- pak::repo_get(bioc = FALSE); \
    cran <- rg[rg\$type == 'cran', , drop = FALSE]; \
    if (nrow(cran) != 1L) stop('repo-pin check: expected exactly 1 CRAN repo, got ', nrow(cran)); \
    if (!grepl(ppm_date, cran\$url, fixed = TRUE)) stop('repo-pin check: CRAN repo is not the PPM_DATE snapshot: ', cran\$url); \
    bad <- grep('cran[.]rstudio[.]com|cran[.]r-project[.]org|/cran/latest', rg\$url, value = TRUE); \
    if (length(bad)) stop('repo-pin check: undated CRAN mirror leaked into repo set: ', paste(bad, collapse = ', ')); \
    cat('repo-pin check OK: CRAN frozen at', cran\$url, '\n')"

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
