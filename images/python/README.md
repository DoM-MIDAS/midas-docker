# Using the Python base images: notebooks & kernels

Applies to the Python Layer 2 bases — [`py-analysis-base`](../py-analysis-base/)
and [`py-singlecell`](../py-singlecell/).

These images ship a **Jupyter kernel, not a Jupyter server.** The pinned
environment lives in a venv at **`/opt/venv`** and is registered as a kernel
via `ipykernel`; there is no JupyterLab/Notebook web server in the base. You
bring the frontend (VS Code, or a Jupyter on your host) and point it at the
kernel running inside the container.

If you specifically want
a browser IDE running *inside* the container (e.g. on a remote/HPC node with
nothing installed locally), add `jupyterlab` in your project's Layer 3 image,
or run a `*-lab` variant `FROM` the base.

The interpreter to select in any frontend is always:

```
/opt/venv/bin/python
```

---

## Option A — VS Code

VS Code's Python/Jupyter extensions only need `ipykernel` in the environment
(which the base has); VS Code provides the notebook UI and manages the kernel.

1. Start the container with your project bind-mounted and keep it alive, e.g.:
   ```bash
   container run -d --name myproj -v "$PWD":/workspace -w /workspace \
     ghcr.io/dom-midas/py-analysis-base:py3.13-2026-05-r1 sleep infinity
   ```
   (or launch it however your project's `.sandbox/` tooling does).
2. In VS Code: **Command Palette → "Dev Containers: Attach to Running
   Container"** → pick `myproj`. VS Code installs its server *inside* the
   container.
3. Open the `/workspace` folder, install the **Python** + **Jupyter**
   extensions when prompted (they install into the container), then open a
   `.py` or `.ipynb`.
4. Choose interpreter / kernel **`/opt/venv/bin/python`** and run cells. They
   execute in the container against the pinned env.

> The Dev Containers "attach" feature talks to a Docker-compatible runtime. If
> your runtime isn't supported by that extension (e.g. Apple `container`), use
> Option B, which is runtime-agnostic.

---

## Option B — Jupyter on your host, kernel in the container

Run the kernel inside the container and connect a host frontend to it via a
shared connection file. Works with any runtime and any frontend that supports
`--existing` (`jupyter console`, `jupyter qtconsole`).

1. **Create a connection file with fixed ports** in your project dir (host):
   ```bash
   python3 - <<'PY'
   import json, uuid
   json.dump({
       "transport": "tcp", "ip": "0.0.0.0",
       "shell_port": 9001, "iopub_port": 9002, "stdin_port": 9003,
       "control_port": 9004, "hb_port": 9005,
       "signature_scheme": "hmac-sha256", "key": str(uuid.uuid4()),
       "kernel_name": "python3",
   }, open("kernel.json", "w"), indent=2)
   PY
   ```
2. **Launch the kernel in the container**, bind-mounting the project so it can
   read `kernel.json`, and make the 5 ports reachable from the host:
   ```bash
   # Docker-compatible runtime (publish ports):
   docker run --rm -it -v "$PWD":/workspace -w /workspace -p 9001-9005:9001-9005 \
     ghcr.io/dom-midas/py-analysis-base:py3.13-2026-05-r1 \
     python -m ipykernel_launcher -f /workspace/kernel.json

   # Apple `container` (no -p; the container gets its own IP):
   container run --rm -it -v "$PWD":/workspace -w /workspace \
     ghcr.io/dom-midas/py-analysis-base:py3.13-2026-05-r1 \
     python -m ipykernel_launcher -f /workspace/kernel.json
   #   then: container ls   # note the container's IP
   ```
3. **Connect from the host.** Copy the file and set `ip` to where the kernel is
   reachable — `127.0.0.1` for published ports, or the container's IP for Apple
   `container`:
   ```bash
   sed 's/"0.0.0.0"/"127.0.0.1"/' kernel.json > kernel.client.json   # or the container IP
   jupyter console --existing "$PWD/kernel.client.json"
   ```

> Connecting a full **host JupyterLab GUI** to an external kernel this way is
> not well-supported (Lab expects to own its kernels). If that's a frequent
> workflow, add `jupyter-kernel-gateway` to a Layer 3 image and connect Lab
> with `jupyter lab --gateway-url=...` — or just run `jupyterlab` inside the
> container (Layer 3) per the note at the top.

---

## Notebooks as `.py` with jupytext

The base ships [`jupytext`](https://jupytext.readthedocs.io/). Prefer committing
notebooks as paired `.py` (percent format): clean git diffs, and agents edit
`.py` far more reliably than `.ipynb` JSON.

```bash
jupytext --set-formats ipynb,py:percent analysis/explore.ipynb  # pair them
jupytext --sync analysis/explore.py                              # regen the .ipynb
```

In VS Code / Jupyter, opening the `.py` and "Run Cell" works directly thanks to
the `# %%` cell markers — no `.ipynb` required.
