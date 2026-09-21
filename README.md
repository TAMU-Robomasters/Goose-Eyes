# Goose-Eyes
Autonomy code base for 26-27 season

<img width="452" height="498" alt="IMG_9739" src="https://github.com/user-attachments/assets/f3697e42-2863-41f2-9ee2-bec0d298a63d" />

---

## Setup

This repo uses [pixi](https://pixi.sh) for the whole environment — Python and non-Python alike: conda-forge
for the toolchain and OpenCV, ROS 2 Jazzy from RoboStack, dora and rerun from PyPI. One `pixi.lock`, solved
for every platform at once.

```bash
curl -fsSL https://pixi.sh/install.sh | sh     # once
pixi install                                   # from the repo root; on a Jetson also: pixi run install-rerun
```

Everything is installed inside the pixi environment, so either enter it with `pixi shell` or prefix commands
with `pixi run`:

```bash
pixi run dora run goose-eyes/dataflows/dataflow.yml    # the camera pub/sub demo
```

New here? [docs/setup/](docs/setup/index.md) explains pixi in a minute.

The **Jetson Orin (JetPack 7) is the main platform**; macOS is partially supported for development. What
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

`pixi run docs-serve` and open http://127.0.0.1:8000 — or read the Markdown directly:

- [docs/setup/](docs/setup/index.md) — install, the `jetson` platform, [adding a dev platform](docs/setup/adding-a-platform.md)
- [docs/dora/](docs/dora/index.md) — running the demo, [architecture](docs/dora/architecture.md) and per-node contracts
- [docs/contributing-docs.md](docs/contributing-docs.md) — how to build/update the docs
