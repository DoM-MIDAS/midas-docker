# Layer 3 smoke test for ghcr.io/dom-midas/r-bioc-singlecell.
#
# Confirms a downstream project can install the GeneseeSC stack on top of the
# base image, with all GitHub-only packages pinned by commit SHA. The package
# loads at the end of this build act as the smoke checks: if any install was
# incomplete, the build fails loudly.
#
# Within-org images are pinned by tag here — the base workflow enforces tag
# immutability, so the tag IS a stable contract. Swap to @sha256:<digest> if a
# stricter contract is wanted.

FROM ghcr.io/dom-midas/r-bioc-singlecell:bioc3.22-ppm2026-04-01-r1

# GitHub-only packages pinned by commit SHA — the SHA is the lockfile entry.
# Genesee is a transitive Imports dep of GeneseeSC; we install it first at a
# pinned SHA so the later GeneseeSC install (whose Remotes line is unpinned)
# does not silently grab Genesee@HEAD.
#
# upgrade = 'never' prevents remotes from re-resolving CRAN/Bioc deps already
# baked into the base image.
RUN R -q -e "remotes::install_github( \
      c( \
        'amcdavid/Genesee@334ac8d7fc0bf2c8904e83b2a4a7e315c6f25c8f', \
        'amcdavid/seurat-disk-lazily@bdd615432527e726d69766f93186021be9636fc2', \
        'amcdavid/GeneseeSC@ff5d5bcd165e766a2b9134815a715176050be16b' \
      ), \
      lib = Sys.getenv('R_LIBS_SITE'), \
      upgrade = 'never', \
      dependencies = TRUE \
    ); \
    needed <- c('Genesee', 'SeuratDisk', 'GeneseeSC'); \
    miss <- needed[!vapply(needed, requireNamespace, logical(1), quietly = TRUE)]; \
    if (length(miss)) stop('Smoke test failed; missing: ', paste(miss, collapse = ', '))"

WORKDIR /workspace
CMD ["R"]
