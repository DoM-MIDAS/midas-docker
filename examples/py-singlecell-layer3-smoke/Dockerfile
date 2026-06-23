# Layer 3 smoke test for ghcr.io/dom-midas/py-singlecell.
#
# Confirms a downstream project can install extra packages on top of the base
# and run a real scanpy pipeline. The script at the end is the smoke check: a
# failed/partial install or a broken pipeline surfaces as a non-zero build.
#
# Within-org images are pinned by tag here — the base workflow makes a
# best-effort attempt to keep tags stable. Swap to @sha256:<digest> for an
# exact-bytes guarantee.

FROM ghcr.io/dom-midas/py-singlecell:py3.13-2026-05-r1

# Layer 3 is the project's own, less-strict layer: the single-cell stack is
# already baked (and hash-pinned) into the base, so a project just adds the few
# extra packages it needs. Pin to taste; --require-hashes is not required here.
#
# scrublet (doublet detection) is a common single-cell add-on intentionally
# left out of the base; this is exactly the kind of thing a project adds here.
RUN pip install --no-cache-dir "scrublet==0.2.3"

# VCS-sourced project deps belong HERE, pinned by commit SHA:
#   RUN pip install --no-cache-dir \
#         "mypkg @ git+https://github.com/myorg/mypkg@<40-char-sha>"

# Smoke check: run an end-to-end scanpy pipeline plus the project add-on.
RUN python - <<'PY'
import sys
import numpy as np, anndata, scanpy as sc
import scrublet  # the Layer 3 add-on

a = anndata.AnnData(np.random.poisson(1.0, size=(300, 80)).astype("float32"))
sc.pp.normalize_total(a)
sc.pp.log1p(a)
sc.pp.pca(a, n_comps=10)
sc.pp.neighbors(a, n_neighbors=10)
sc.tl.leiden(a, flavor="igraph", n_iterations=2)
sc.tl.umap(a)

ok = a.obsm["X_umap"].shape == (300, 2) and a.obs["leiden"].nunique() >= 1
if not ok:
    sys.exit("Smoke test failed: scanpy pipeline produced unexpected output")
print("Smoke test OK: scanpy pipeline + scrublet import; clusters =",
      a.obs["leiden"].nunique())
PY

WORKDIR /workspace
CMD ["python"]
