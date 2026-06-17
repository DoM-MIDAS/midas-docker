# Design: Agent-Safe Analysis Projects via Container Isolation + Synthetic Mirror

## Goal

Coding agents for statistics or bioinformatics projects that are prevented from touching the real data, but have enough context to write/run/debug workflows.  A human operator works on the same project directory with full data access. Both processes edit the same files; changes flow between them through the shared filesystem.

Three mechanisms enable this:

1. **Data indirection.** Real data lives at a path separate from the code, and is declared in a config file. All reads go through a single loader that resolves logical names through this config.
2. **Container isolation.** The agent's process runs in a container or vm whose filesystem does not include the real data path. Even if the agent constructed the path string, the file will not be mounted.
3. **Synthetic mirror data** (committed at `data/example/`, schema-faithful to the real data) makes the agent more productive — it executes and debugs against realistic-shaped data rather than working blind.

The isolation model here guards against inadvertent access but is probably not sufficient to contain an adversary.

## Phasing

**Phase 1 (MVP)** is data indirection + container isolation + layered Docker images for the package environment. This alone meets typical enterprise requirements — the agent simply cannot reach the real data — and ships with no special tooling. The agent works against example files the operator hand-rolls (a CSV with the right header and a handful of fake rows is usually enough to get started). Most projects can ship with just Phase 1.

**Phase 2 (later)** is the `syngen` tool for generating and maintaining schema-faithful synthetic mirrors automatically. This is a productivity layer on top of Phase 1.

The rest of this document describes Phase 1 in detail, then sketches Phase 2 as future work.

---

# Phase 1 (MVP)

## Workflow

End-to-end, from project creation through a delivered report:

1. **Create project skeleton.** Scaffold the directory layout below (R/, analysis/, tests/, data/example/, config/, scripts/, Dockerfile, Dockerfile.agent, .gitignore, README.md). A template repo or cookiecutter is enough; the eventual `syngen init` is a convenience.

2. **Place real data outside the project tree.** Operator moves or symlinks real data to `/rawdata/myproject/`. Nothing in the repo points here.

3. **Write operator's data config.** Operator copies `config/data.toml.example` to `config/data.toml` and edits it to point at `/rawdata/myproject` with the real filename mapping. Whether `config/data.toml` is committed or gitignored is a team choice; see the Config contract section.

4. **Hand-roll the example data.** Operator creates `data/example/` with files matching the real-data schema: same logical filenames (as referenced by `config/data.toml.example`), same columns, dtype-correct values, a handful of rows. Five minutes of work for a small project; large or messy schemas justify the Phase 2 tooling.

5. **Edit Dockerfiles.** `Dockerfile` inherits from an org-standard base image (see Containerization below) and adds project-specific packages. `Dockerfile.agent` inherits from `Dockerfile` and adds the agent runtime.

6. **Build images.** `docker build -t myproject .` and `docker build -f Dockerfile.agent -t myproject-agent .`. Subsequent builds hit the layer cache and are fast.

7. **Agent develops against example data.** Operator launches the agent via `./scripts/agent-shell.sh claude` (or `aider`, etc.). The agent sees `data/example/` as the only data, writes analysis code in `R/`, `analysis/`, and `tests/`, runs it, iterates. All file changes are visible to the operator immediately because the project directory is bind-mounted.

8. **Operator iterates on real data in parallel.** In their host R session, operator runs the same code the agent is writing, against real data (host loader reads `config/data.toml`). When something breaks on the real distribution that didn't break on the example, operator edits the code in place. Agent sees the edit on its next iteration. No commit cycle.

9. **Operator runs report and commits.** When analysis stabilizes, operator knits the report against real data, reviews outputs, commits the code (not the rendered report, which contains real data). Report output should live outside the project tree (e.g., `/reports/myproject`); a symlinked `reports/` inside the project resolves on the host but is a dangling link inside the container, so the agent cannot read or overwrite real reports.

## Project structure

```
myproject/
├── R/                          # library code, sourced by analysis scripts
│   ├── load.R                  # data-reading chokepoint; all reads go through here
│   ├── clean.R
│   ├── model.R
│   └── plot.R
├── analysis/                   # entry-point scripts and reports
│   ├── 01_descriptives.R
│   ├── 02_primary_model.R
│   └── 03_report.Rmd
├── tests/
│   └── testthat/
├── data/
│   └── example/                # COMMITTED. hand-rolled (Phase 1) or syngen-generated (Phase 2).
│       ├── visits.csv
│       ├── labs.csv
│       └── outcomes.xlsx
├── config/
│   ├── data.toml.example       # COMMITTED. points at data/example.
│   ├── data.toml               # GITIGNORED (or committed, see below). operator's real-data config.
│   ├── analysis.toml.example   # COMMITTED. parameters for example data.
│   └── analysis.toml           # GITIGNORED (or committed, see below). parameters for real data.
├── scripts/
│   └── agent-shell.sh          # launcher; runs the agent inside the container
├── reports → /reports/myproject  # GITIGNORED symlink, dangling inside container
├── Dockerfile                  # project runtime, inherits from org base
├── Dockerfile.agent            # agent runtime, inherits from Dockerfile
├── .gitignore
└── README.md
```

### Files that live outside the project tree

```
/rawdata/myproject/             # real data, never in the repo, never in the container
/reports/myproject/             # rendered reports with real data, never committed
```

### Loader contract

`R/load.R` is the only place in the project that calls `read_csv`, `read_excel`, `h5read`, etc. Every other module imports `load_*` functions from it. This is a project-wide invariant; a pre-commit hook should reject reads outside this file.

```r
# R/load.R
.load_config <- function() {
  # Single fixed path. The host sees the operator's real config; the
  # container sees the example, because the launcher mounts the example
  # file over this path.
  RcppTOML::parseTOML("config/data.toml")
}

data_path <- function(name) {
  cfg <- .load_config()
  file.path(cfg$data_dir, cfg$files[[name]])
}

load_visits   <- function() readr::read_csv(data_path("visits"))
load_labs     <- function() readr::read_csv(data_path("labs"))
load_outcomes <- function() readxl::read_excel(data_path("outcomes"))
```

The loader always reads `config/data.toml`. There is no env-var fallback. The trick that makes this work in both environments is that the agent launcher bind-mounts `config/data.toml.example` over `config/data.toml` inside the container — different content visible to each side, same path in the code.

TOML was chosen over YAML and JSON for these configs: it has comments (unlike JSON), unambiguous types (unlike YAML's implicit `NO → false`, `2.10 → 2.1` coercions), and a single canonical way to write a given structure. For flat-ish, human-edited configs of the kind used here, it is the lowest-footgun option.

### Config contract

`config/data.toml.example` (committed, points at example):
```toml
data_dir = "data/example"

[files]
visits = "visits.csv"
labs = "labs.csv"
outcomes = "outcomes.xlsx"
```

`config/data.toml` (operator-authored, points at real):
```toml
data_dir = "/rawdata/myproject"

[files]
visits = "visits_2026q1.csv"
labs = "labs_full.csv"
outcomes = "outcomes_adjudicated.xlsx"
```

Logical-to-physical filename mapping means real filenames (with version suffixes, dates, legacy names) don't pollute analysis code. The example and real configs share *logical* names, so the same code resolves correctly in both environments.

A fresh checkout has only `config/data.toml.example`. The README's first instruction is: `cp config/data.toml.example config/data.toml` and edit. Until that's done, the host R session has no `config/data.toml` to read and fails loudly — which is the right behavior, because there's no real data to point at yet.

`config/analysis.toml.example` / `config/analysis.toml` follow the same pattern for analysis parameters: cohort definitions, thresholds, case-study participant IDs.

**Committed vs. gitignored.** The agent's filesystem view of `config/data.toml` is governed by the launcher's bind mount, not by the gitignore — the container always sees the example regardless of what's in the host file. So whether the operator's real config is committed is a *collaboration* choice, not a security one:

- If your team mounts data at a single shared path (e.g., everyone has `/rawdata/{projectname}/`), commit `config/data.toml`. Onboarding is one less step, and the path string in the repo isn't sensitive — anyone reading the repo already has access to the same mount.
- If operators have heterogeneous paths, gitignore it and commit only `data.toml.example`. Onboarding is `cp` + edit.
- A middle option: commit `data.toml` with a shell-variable placeholder (`data_dir = "${MYPROJECT_DATA_DIR}"`) and have the loader expand env vars. Each operator sets the env var once.

The doc's examples assume the gitignored-per-operator case because it's the safest default, but pick what fits your team.

### .gitignore essentials

```
config/data.toml         # if your team has heterogeneous data paths; omit if committing it
config/analysis.toml     # likewise
reports
.Renviron
*.Rproj.user
```

## Containerization

### Layered images

Three layers, each rebuilt on a different cadence and maintained by a different party:

**Layer 1: language base.** A pinned R version with core system libraries. For bioinformatics, `bioconductor/bioconductor_docker:RELEASE_X_Y` pins R + Bioconductor release together and ships most of the system libraries you need. For non-Bioc projects, `rocker/r-ver:4.4.0` is the equivalent. Maintained by the upstream community; you just pick a tag.

**Layer 2: org-standard analysis base.** Inherits from a Layer 1 image. Adds a *frozen Posit Public Package Manager (PPM) snapshot URL*, written into `Rprofile.site`, plus the packages your group uses on essentially every project.

```dockerfile
# org-base/Dockerfile  →  ghcr.io/yourorg/analysis-base:bioc-3.20-2026-05
FROM bioconductor/bioconductor_docker:RELEASE_3_20

RUN apt-get update && apt-get install -y --no-install-recommends \
      libhdf5-dev pandoc texlive-xetex texlive-fonts-recommended \
 && rm -rf /var/lib/apt/lists/*

# All install.packages() calls from here on hit PPM frozen at this date.
RUN echo 'options(repos = c( \
            PPM  = "https://packagemanager.posit.co/cran/__linux__/jammy/2026-05-01", \
            BioC = BiocManager::repositories() \
          ))' >> "${R_HOME}/etc/Rprofile.site"

# Library path lives outside any future bind mount.
ENV R_LIBS_SITE=/opt/R/library
RUN mkdir -p /opt/R/library

RUN R -e "install.packages(c( \
      'tidyverse','data.table','arrow','duckdb', \
      'glue','fs','here','RcppTOML','jsonlite', \
      'ggplot2','patchwork','scales','gt', \
      'testthat','targets','remotes' \
    ), lib = '/opt/R/library')"

RUN R -e "BiocManager::install(c( \
      'SummarizedExperiment','SingleCellExperiment','DESeq2','edgeR','limma' \
    ), update = FALSE, ask = FALSE, lib = '/opt/R/library')"

# Build-artifact manifest for auditing what actually resolved.
RUN R -e "write.csv(installed.packages()[, c('Package','Version')], \
                    '/opt/R/library/packages.txt', row.names = FALSE)"

# Ephemeral user library for agent experiments during a session.
RUN mkdir -p /home/r/R/library && chmod 777 /home/r/R/library
ENV R_LIBS_USER=/home/r/R/library
```

The PPM date in the URL is the lockfile. Rebuilding this image next year from the same Dockerfile produces the same package versions because PPM keeps historical snapshots indefinitely. Bioconductor versions are pinned by the Bioc release tied to the R version.

**Layer 3: project image.** Inherits from Layer 2. Adds only project-specific packages.

```dockerfile
# myproject/Dockerfile
FROM ghcr.io/yourorg/analysis-base:bioc-3.20-2026-05

# Project-specific CRAN/Bioc packages, picking up the PPM-pinned repos
# inherited via Rprofile.site.
RUN R -e "install.packages(c('lme4','broom.mixed','emmeans'), lib = '/opt/R/library')"
RUN R -e "BiocManager::install('fgsea', update = FALSE, ask = FALSE, lib = '/opt/R/library')"

# GitHub-only packages, pinned by commit SHA. The SHA IS the lockfile entry.
RUN R -e "remotes::install_github( \
      'mygroup/internal-utils@a3f2b1c8d9e0f1234567890abcdef1234567890a', \
      lib = '/opt/R/library')"

WORKDIR /workspace
CMD ["R"]
```

Every input is pinned: base image by tag, CRAN packages by PPM date, Bioc packages by Bioc release, GitHub packages by SHA. The Dockerfile *is* the lockfile. No `renv.lock`, no `renv::restore()`, no autoloader to disable.

### Why this instead of renv

`renv` records a lockfile of every package version. In practice this fights you whenever the dependency graph has anything more exotic than vanilla CRAN: recursive GitHub dependencies fail to resolve, the lockfile records architecture-specific binary hashes that don't transfer between macOS and Linux, and a single unresolvable pin blocks the whole restore.

The PPM-date + Bioc-release + GitHub-SHA scheme replaces lockfile-as-source-of-truth with pin-the-inputs:
- PPM at a given date is internally consistent by construction (a frozen view of CRAN).
- Bioconductor releases are internally consistent by construction (release-testing guarantees it).
- GitHub SHAs are pinpoint.

The composition is reproducible because none of the inputs change. The `packages.txt` baked into the image at build time gives you the resolved-version manifest as a *build artifact*, not a build input — auditability without brittleness.

### Dockerfile.agent

```dockerfile
# Dockerfile.agent
FROM myproject:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /workspace
CMD ["claude"]
```

The agent's R environment is bit-for-bit identical to the project image; only the agent CLI on top differs.

### Package environment summary

Two libraries on R's library path inside the container:

1. **`/opt/R/library`** (`R_LIBS_SITE`): baked into the image at build time. Read-only at runtime. Identical across every container run. Reproducible by rebuilding the image.
2. **`/home/r/R/library`** (`R_LIBS_USER`): user-writable, ephemeral. Where the agent's mid-session `install.packages()` lands. Lost on container restart. Operator promotes survivors into the project Dockerfile if they should persist.

Build-time install is the right default because container restart is frequent (every agent launch) and reinstall-on-restart would be intolerable. Image rebuild is the right boundary for "real" dependency changes: edit the Dockerfile, `docker build`, the affected layer rebuilds (a minute or two thanks to layer caching), earlier layers stay cached.

A persistent named volume for the library would survive restarts without rebuilds, but it's mutable state that drifts from the image, breaks reproducibility, and creates "works on my machine" failures between developers' volumes. Image rebuild is slower in the moment but correct.

### Image maintenance and discovery

Base images are the highest-leverage and highest-risk components: many projects share each base, so a good base saves work everywhere and a broken base breaks everyone. Treat them as platform infrastructure.

**Registry.** Push base images to a single container registry: GitHub Container Registry (`ghcr.io/yourorg/...`), an internal registry, or Docker Hub. Pull credentials, if any, live with the platform team; project users authenticate once and `docker pull` works.

**Naming and tagging.** Tags encode the two things that matter: Bioconductor release and PPM snapshot date. Example: `ghcr.io/yourorg/analysis-base:bioc-3.20-2026-05`. **The `latest` tag is not used** — projects must pin a specific tag in their `FROM` line so an org-base rebuild doesn't silently change a project's package versions. Tags are immutable once published; multiple tags coexist; old images are retained for at least the lifetime of any project using them.

**Discovery.** A single README in the base-image repo lists:
- Available tags and what's in each (R version, Bioc release, PPM date, package list).
- A short table mapping common project types to recommended bases (e.g., "single-cell" → `bioc-3.20-2026-05` with Seurat/SCE; "epi/clinical" → a different base without scRNA stack).
- The policy for cutting new tags (below).

Projects discover bases by reading this README, picking a tag, and putting it in their Dockerfile. If 3-5 distinct bases cover everyone's needs, the README is short and the choice is obvious; resist the temptation to publish a base per project.

**Cadence.** New base tags are cut on three triggers, in order of frequency:
1. *Bioconductor releases* (twice a year, April and October). The platform team builds a new base for the new Bioc release within a few weeks. Projects opt in by bumping their `FROM` line.
2. *PPM date refresh.* Every 6 months, the platform team cuts a new base on the current Bioc release with a more recent PPM snapshot, picking up CRAN updates. Projects opt in only if they want them.
3. *Security fixes.* Urgent system-library updates ship as new patch tags; projects update at their own pace.

**Ownership.** A small platform team or rotating maintainer owns the base-image repo. PRs to add packages go through this team. Most projects do not need to modify the base; the right place to add a needed package is the project's own Dockerfile (Layer 3). A package goes into Layer 2 only if enough projects use it that centralizing is cheaper than per-project duplication.

**Updating a project's base.** Edit the `FROM` line in `myproject/Dockerfile`, `docker build`, run the tests, commit. If the new base brings package version changes that break code, that's regular debugging — not a lockfile-resolution puzzle.

### Python variant

The same three-layer structure applies for Python projects. The mechanics at each layer are different, but the philosophy (pin the inputs, build at image-build time, bake the resolved manifest as a build artifact) is identical.

**Layer 1: language base.** `python:3.12-slim` for most projects. For bioinformatics-flavored Python that needs the heavy native stack (Seurat-equivalent packages, GPU libraries, exotic C/Fortran extensions), inherit from `mambaorg/micromamba` and use conda-forge + bioconda channels instead; this is the closest Python gets to Bioconductor's curated-stack model. Pure-pip is fine for most stats/ML work.

**Layer 2: org analysis base.** Where R uses a frozen PPM URL plus `install.packages()`, Python uses a `requirements.in` (human-edited, loose constraints) compiled to a `requirements.txt` with hashes (machine-generated, exact pins). The lockfile is committed and installed with `pip install --require-hashes`, which refuses any package not pinned by hash — the equivalent guarantee `uv sync --frozen` would give you.

```dockerfile
# org-base/Dockerfile  →  ghcr.io/yourorg/py-analysis-base:py3.12-2026-05
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libhdf5-dev pandoc \
 && rm -rf /var/lib/apt/lists/*

# Install into a system-level prefix outside any future bind mount.
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Pinned lockfile with --require-hashes refuses anything not pinned.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
 && pip freeze > /opt/packages.txt \
 && rm /tmp/requirements.txt
```

The org-base `requirements.in` lists the standard scientific stack:

```
# requirements.in
numpy>=2.0
pandas>=2.2
scipy
scikit-learn
pyarrow
polars
matplotlib
seaborn
jupyter
pytest
tomli; python_version < "3.11"   # stdlib's tomllib is 3.11+
```

Compiled with `pip-compile --generate-hashes` (from `pip-tools`) or `uv pip compile --generate-hashes` — either produces a `requirements.txt` that pins every transitive dependency by version + sha256, with full cross-architecture support (PyPI serves architecture-appropriate wheels based on the request, so the same lockfile installs correctly inside a Linux container regardless of host platform).

**Layer 3: project image.** Same pattern, project-specific lockfile:

```dockerfile
# myproject/Dockerfile
FROM ghcr.io/yourorg/py-analysis-base:py3.12-2026-05

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

WORKDIR /workspace
CMD ["python"]
```

The project's `requirements.in` can list anything the project needs plus GitHub-only deps using PEP 508 syntax: `internal-utils @ git+https://github.com/mygroup/internal-utils@a3f2b1c8`. The compiler resolves and pins these too, with hashes computed from the downloaded archive.

**Workflow when adding a package.** Edit `requirements.in`, run `pip-compile --generate-hashes` (or `uv pip compile --generate-hashes`), commit both files, rebuild the image. The diff in `requirements.txt` shows the full transitive consequence of the change — good for code review.

**Loader.** Python's loader mirrors R's:

```python
# src/myproject/load.py
import tomllib
from pathlib import Path
import pandas as pd

def _load_config():
    with open("config/data.toml", "rb") as f:
        return tomllib.load(f)

def _data_path(name):
    cfg = _load_config()
    return Path(cfg["data_dir"]) / cfg["files"][name]

def load_visits():   return pd.read_csv(_data_path("visits"))
def load_labs():     return pd.read_csv(_data_path("labs"))
def load_outcomes(): return pd.read_excel(_data_path("outcomes"))
```

`tomllib` is in the standard library since Python 3.11. The launcher script, bind mounts, and config-override mechanism don't change — they operate at the Docker level and are language-agnostic.

**Why this over `pyproject.toml` + `uv sync`?** Both work. `requirements.in/.txt` is the more universal, older, lower-ceremony choice: every Python developer recognizes it, every tool reads it, and the Dockerfile is shorter. `pyproject.toml` + `uv sync` is the better choice when the project is itself a package (importable, with its own version, supports editable installs of project code). For analysis projects — flat `analysis/` directory of scripts, no `import myproject` — `requirements.in/.txt` is the right fit.

**Why not conda by default?** Conda gives you a Bioconductor-style curated, version-coordinated ecosystem and handles native dependencies better than pip. The cost is heavier images, slower solves, and a less-standard workflow. Use conda/mamba (with `conda-lock` for pinning) at Layer 1/2 if you genuinely need it; for most projects pip + wheels work fine and are simpler.

**Project structure differences.** A Python project's tree looks like:

```
myproject/
├── src/myproject/
│   ├── __init__.py
│   ├── load.py
│   ├── clean.py
│   └── model.py
├── analysis/
│   ├── 01_descriptives.py
│   ├── 02_primary_model.py
│   └── 03_report.qmd      # Quarto, or .ipynb for Jupyter
├── tests/
├── data/example/
├── config/                # same as R: data.toml.example etc.
├── scripts/agent-shell.sh
├── Dockerfile
├── Dockerfile.agent
├── requirements.in
├── requirements.txt
└── README.md
```

The agent-isolation story is identical; only the package-environment machinery differs.

### scripts/agent-shell.sh

The single entry point for launching the agent. The isolation properties depend on the agent *always* being launched through this script.

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

docker run --rm -it \
  --user "$(id -u):$(id -g)" \
  -v "${PROJECT_DIR}:/workspace" \
  -v "${PROJECT_DIR}/config/data.toml.example:/workspace/config/data.toml:ro" \
  -v "${PROJECT_DIR}/config/analysis.toml.example:/workspace/config/analysis.toml:ro" \
  -v "${PROJECT_DIR}/data/example:/workspace/data/example:ro" \
  -w /workspace \
  myproject-agent:latest \
  "$@"
```

The config-override mounts are what make the single-path loader work: on the host, `config/data.toml` is the operator's real-data config; inside the container, the same path resolves to the committed example. Same code, different content per environment.

### Bind mount contract

- **Mounted read-write:** the project directory. Agent edits code, operator sees edits, vice versa.
- **Mounted read-only:**
  - `data/example/` — prevents the agent from accidentally regenerating or corrupting the synthetic data.
  - `config/data.toml.example` → `config/data.toml` — the override that gives the container its safe config view.
  - `config/analysis.toml.example` → `config/analysis.toml` — same pattern for analysis params.
- **Not mounted:** `/rawdata/`, `/reports/`, the operator's home directory, SSH keys, anything else on the host. The container sees the project plus the standard container OS, nothing else.

### User-id mapping

`--user "$(id -u):$(id -g)"` makes the container write files as the host user. Without this, agent-created files would be owned by `root` and require `sudo` to edit on the host. With it, the agent and operator share the project directory with no permission friction.

### Network policy

The launcher above does *not* set `--network none`. Agent CLIs need to reach their LLM backend to function at all. This means the agent can technically make outbound HTTP calls, so network isolation is not a hard exfiltration boundary — fine for the inadvertent threat model, not fine if you fear data theft. If you need both agent functionality and a real exfiltration boundary, run a host-side proxy that whitelists the agent's API endpoint and nothing else, and configure the container to route through it.

### Discipline requirements

The isolation is convention-enforced for one thing:

1. **The agent must be launched through `scripts/agent-shell.sh`.** Running the agent CLI directly on the host bypasses the container entirely. README must call this out; a wrapper script that errors if it detects it's running on the host (no `/.dockerenv`) catches accidents.

A second item is convention-but-not-security: the committed `*.example` config files should contain only example paths (`data/example`, synthetic IDs). Don't paste real paths or values into them — they're committed, so the cost of a slip is a commit revert. The bind mount protects the agent's runtime view regardless, so this is hygiene, not a boundary.

### What this does and does not prevent

Prevents:
- Agent globbing or `ls`-ing into real data directories (they don't exist in the container).
- Agent autocompleting real filenames from shell history or filesystem traversal.
- Agent committing real data by accident (the real data is not in its filesystem).
- Agent reading the operator's other projects, SSH keys, or home directory.
- Agent seeing the operator's real-data config (the launcher overrides the same path with the example).
- Agent corrupting the example data or its config (read-only mounts).
- Agent writing to or reading from rendered reports (`reports/` is a dangling symlink inside the container).

Does not prevent:
- An agent constructing the real path string by guessing, then exfiltrating via an LLM API call. (Out of threat model; addressable by a whitelisting proxy if needed.)
- Operator pasting real data into the agent's chat context. (Operator discipline.)
- Inadequate example data leading the agent to write code that works on the example but breaks on real data. (This is what Phase 2 partly addresses.)

---

# Phase 2 (future): syngen

Phase 1 leaves the operator hand-rolling example data. That works for small, stable schemas and breaks down for wide tables, multi-file projects, and projects whose schemas drift. Phase 2 adds `syngen`, a utility that introspects real data and emits a schema-faithful synthetic mirror.

## syngen CLI sketch

Five subcommands.

### `syngen init <project_name>`

Scaffolds a new project. Same job as the Phase-1 cookiecutter, just one command.

### `syngen generate-manifest --from <real_data_dir> --out syngen.toml`

Introspects every file in `<real_data_dir>` and writes a TOML manifest:

```toml
version = 1

[files.visits]
path = "visits_2026q1.csv"
format = "csv"
n_rows_real = 48201
n_rows_synthetic = 500

[files.visits.columns.participant_id]
dtype = "string"
role = "identifier"              # auto-detected; operator confirms
cardinality = 1247
null_rate = 0.0
synth = "stable_token"           # emits participant_0001..participant_0500

[files.visits.columns.visit_date]
dtype = "date"
range = ["2019-01-15", "2026-03-22"]
null_rate = 0.003
synth = "range_uniform"

[files.visits.columns.bmi]
dtype = "float"
range = [13.2, 71.8]
null_rate = 0.041
synth = "range_uniform"

[files.visits.columns.site]
dtype = "string"
role = "categorical"
cardinality = 4
levels = ["SITE_A", "SITE_B", "SITE_C", "SITE_D"]
synth = "empirical"              # preserves level frequencies
```

(The deeply-nested manifest is the one place where TOML's dotted-section repetition gets verbose; YAML would be shorter here. The tradeoff is acceptable for consistency with the rest of the project's configs, but if the manifest grows much deeper, revisit.)

Operator reviews and edits. Common edits: promote columns to `identifier`, switch `range_uniform` to `empirical` where shape matters, add `synth = "fixed_vocabulary"` with a vocabulary file for things like gene symbols, mark columns `sensitive = true` to suppress entirely, adjust `n_rows_synthetic`.

### `syngen regen`

Reads `syngen.toml`, reads real files, generates synthetic files into `data/example/`. Idempotent and seeded.

Per-format adapters:
- **csv** — schema + per-column synth strategy.
- **xlsx** — preserves sheet structure, named ranges, column widths. Formulas frozen to values.
- **hdf5** — preserves group hierarchy, dataset shapes, chunking, attributes, compression.
- **parquet** — preserves schema, partition structure, row group layout.

### `syngen check`

Re-introspects real data and compares against the manifest. Exits nonzero on drift. Prints a diff:

```
DRIFT in `visits`:
  + new column `consent_version` (string, cardinality 3)
  ~ column `site` cardinality 4 -> 6 (new levels: SITE_E, SITE_F)
  ~ column `bmi` null_rate 0.041 -> 0.118
```

Run in CI or as a pre-commit hook after pulling new real data.

### `syngen update`

Convenience: `check`, then update manifest in place preserving operator overrides, then `regen`.

### Operational notes

- syngen runs on the host, not inside the agent container. It needs real-data access by definition.
- syngen output (`data/example/`, `syngen.toml`) is committed. The agent reads it; the agent never runs syngen.
- syngen never writes anything to `/rawdata/`. Read-only on the real data.

## Known limitations (relevant to both phases)

- **Interleaved literals.** Analysis code sometimes contains data-specific literals (a specific participant ID for a case study, cohort definitions tied to real values). These belong in `config/analysis.toml`, not in code. Convention: agent always writes `def plot_participant(df, participant_id)`, never `df[df.id == "SUBJ_00417"]`. The example config has synthetic IDs; the operator's config has real ones.
- **Sensitive schemas.** Most schemas are not sensitive. The exceptions (column names encoding unblinded arms, column headers that are themselves PHI, study-name columns) are handled by renaming-at-ingest before any agent-visible code sees them. If even the schema is sensitive, the file-based approach is the wrong tool; use a data-as-a-service interface instead.
