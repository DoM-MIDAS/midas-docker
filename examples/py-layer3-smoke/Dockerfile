# Layer 3 smoke test for ghcr.io/dom-midas/py-analysis-base.
#
# Confirms a downstream project can install extra packages on top of the base
# image. The imports at the end of this build are the smoke checks: if any
# install was incomplete, the build fails loudly.
#
# Within-org images are pinned by tag here — the base workflow enforces tag
# immutability, so the tag IS a stable contract. Swap to @sha256:<digest> if a
# stricter contract is wanted.

FROM ghcr.io/dom-midas/py-analysis-base:py3.13-2026-05-r1

# Layer 3 is the project's own, less-strict layer: the heavy scientific stack is
# already baked (and hash-pinned) into the base, so a project just adds the few
# extra packages it needs. Pin to taste; --require-hashes is not required here.
#
# Project PyPI deps. The base already provides numpy/pandas/scipy/sklearn, so
# these resolve their (few) extra deps against what's installed.
RUN pip install --no-cache-dir \
      "networkx==3.5" \
      "tqdm==4.67.1"

# VCS-sourced project deps belong HERE, not in the Layer 2 base, and are pinned
# by commit SHA — the SHA is the lockfile entry. Example (commented; needs a
# real repo + SHA):
#
#   RUN pip install --no-cache-dir \
#         "mypkg @ git+https://github.com/myorg/mypkg@<40-char-sha>"

# Smoke checks: import everything that was supposed to land. A failed/partial
# install surfaces as a non-zero build here.
RUN python - <<'PY'
import importlib, sys
needed = ["numpy", "pandas", "sklearn", "networkx", "tqdm"]
missing = []
for mod in needed:
    try:
        importlib.import_module(mod)
    except Exception as e:  # noqa: BLE001
        missing.append(f"{mod} ({e.__class__.__name__})")
if missing:
    sys.exit("Smoke test failed; could not import: " + ", ".join(missing))
print("Smoke test OK:", ", ".join(needed))
PY

WORKDIR /workspace
CMD ["python"]
