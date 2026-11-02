# Goose-Eyes
Autonomy code base for 26-27 season

<img width="452" height="498" alt="IMG_9739" src="https://github.com/user-attachments/assets/f3697e42-2863-41f2-9ee2-bec0d298a63d" />

---

## Setup

This repo uses [pixi](https://pixi.sh) for python and non-python package management. Pixi pulls packages from [conda forge and PyPI](https://pixi.prefix.dev/latest/concepts/conda_pypi/)

```bash
curl -fsSL https://pixi.sh/install.sh | sh     # once
# from the repo root, pick your machine:
pixi install && pixi run install-rerun         # Jetson
pixi install -e dev                            # Mac / x86_64 Linux laptop (the `dev` env adds OpenCV + rerun)
```

Everything is installed inside the pixi environment, so either enter it with `pixi shell` or prefix commands
with `pixi run`. On a laptop or non-jetson device add `-e dev` to both:

```bash
pixi run dora run goose-eyes/dataflows/dataflow.yml          # Jetson
pixi run -e dev dora run goose-eyes/dataflows/dataflow.yml   # laptop
```

New here? [docs/setup/](docs/setup/index.md) explains how to use pixi.

The **Jetson Orin (JetPack 7) is the main platform**; macOS and x86_64 Linux are partially supported for
development through the `dev` environment. What
differs and why is in [docs/setup/platforms.md](docs/setup/platforms.md).

## Layout

```
pixi.toml, pixi.lock     the environment (all platforms) and the tasks
goose-eyes/              the code → docs/dora/index.md
  nodes/                 dora node scripts (one process each: camera_pub, camera_sub)
  dataflows/             dora dataflow graphs (*.yml) wiring nodes together
utils/                   scripts pixi calls: activation on the Jetson, the rerun install, docs generators
docs/, mkdocs.yml        the MkDocs site (pixi run docs-serve)
```

## Docs
If you are building an advance feature like EKF auto-aim I would encourage you to write explanations with link to learning resources in the docs
- [docs/setup/](docs/setup/index.md) — install, the `jetson` platform, [adding a dev platform](docs/setup/adding-a-platform.md)
- [docs/contributing-docs.md](docs/contributing-docs.md) — how to build/update the docs
