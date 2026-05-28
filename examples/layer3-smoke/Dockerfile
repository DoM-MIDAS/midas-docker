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

FROM ghcr.io/dom-midas/r-bioc-singlecell:bioc3.22-ppm2026-04-01-r2

# GitHub-only packages pinned by commit SHA — the SHA is the lockfile entry.
# pak resolves all three together: when it sees an explicit Genesee@<sha> ref
# in the install set, it uses that for GeneseeSC's unpinned Remotes:Genesee
# line rather than silently fetching Genesee@HEAD. No bootstrap-ordering trick
# needed (compare to remotes::install_github, which would install in argument
# order and miss this).
#
# upgrade = FALSE keeps CRAN/Bioc deps already baked into the base image as-is.
RUN R -q -e "pak::pkg_install( \
      c( \
        'amcdavid/Genesee@334ac8d7fc0bf2c8904e83b2a4a7e315c6f25c8f', \
        'amcdavid/seurat-disk-lazily@bdd615432527e726d69766f93186021be9636fc2', \
        'amcdavid/GeneseeSC@ff5d5bcd165e766a2b9134815a715176050be16b' \
      ), \
      lib = '/opt/R/library', \
      upgrade = FALSE \
    ); \
    needed <- c('Genesee', 'SeuratDisk', 'GeneseeSC'); \
    miss <- needed[!vapply(needed, requireNamespace, logical(1), quietly = TRUE)]; \
    if (length(miss)) stop('Smoke test failed; missing: ', paste(miss, collapse = ', '))"

WORKDIR /workspace
CMD ["R"]
