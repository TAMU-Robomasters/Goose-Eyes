# Setup

The whole environment — Python, OpenCV, ROS 2 Jazzy, dora, rerun — comes from one
[pixi](https://pixi.sh) manifest, `pixi.toml`.

```bash
curl -fsSL https://pixi.sh/install.sh | sh     # once
pixi install                                   # from the repo root
pixi run install-rerun                         # Jetson only — rerun lives outside the lock there
```

## pixi in one minute

pixi is a package manager that installs everything (conda-forge packages *and* PyPI packages) into
a project-local environment under `.pixi/`. Nothing goes on your system. What you need to know:

- **`pixi.toml`** lists the dependencies; **`pixi.lock`** records the exact versions that were solved
  and is checked in, so everyone gets the same environment. `pixi install` reads the lock.
  ([manifest](https://pixi.sh/latest/reference/pixi_manifest/) ·
  [lock file](https://pixi.sh/latest/workspace/lockfile/))
- **Running things.** The environment isn't on your `PATH` by default. Either enter it with
  [`pixi shell`](https://pixi.sh/latest/reference/cli/pixi/shell/) and work normally (`exit` to leave),
  or prefix a single command with [`pixi run`](https://pixi.sh/latest/reference/cli/pixi/run/):

    ```bash
    pixi shell
    dora run goose-eyes/dataflows/dataflow.yml
    ```
    ```bash
    pixi run dora run goose-eyes/dataflows/dataflow.yml
    ```

- **Tasks** are named shortcuts defined in `pixi.toml` (`pixi task list`). This repo keeps them for
  tooling only — `install-rerun`, the `docs*` tasks — not for running dataflows.
  ([tasks](https://pixi.sh/latest/workspace/advanced_tasks/))
- **Adding a dependency:** [`pixi add <pkg>`](https://pixi.sh/latest/reference/cli/pixi/add/)
  (`pixi add --pypi <pkg>` for PyPI). It re-solves the lock for every platform and fails right there if
  the package doesn't exist for one of them.
- **Platforms and targets.** The manifest is solved for the Jetson and for macOS laptops at once;
  platform-specific dependencies live in `[target.<platform>.*]` tables. See
  [Platforms](platforms.md) and [Adding a platform](adding-a-platform.md).
- **ROS 2 Jazzy** comes from the [RoboStack](https://robostack.github.io) conda channel as ordinary
  dependencies — no `source /opt/ros/...`, it's just there inside the environment. Nothing in
  `goose-eyes/` uses it yet.
- The docs toolchain is a separate pixi *environment* (`docs`) so the runtime env stays small; the
  `pixi run docs*` tasks pick it automatically. ([environments](https://pixi.sh/latest/workspace/multi_environment/),
  [Updating the docs](../contributing-docs.md))
