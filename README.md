# Goose-Eyes
Autonomy code base for 26-27 season

<img width="452" height="498" alt="IMG_9739" src="https://github.com/user-attachments/assets/f3697e42-2863-41f2-9ee2-bec0d298a63d" />

---

## Setup

This repo uses [pixi](https://pixi.sh) to manage the environment. Install pixi if you don't have it. Pixi is very similar to uv it actually uses uv to get packages from the PyPI (Python package repository) but you can also manage non-python packages that are stored on [conda-forge](https://conda-forge.org/)(e.g. ROS2!):

```bash
curl -fsSL https://pixi.sh/install.sh | sh
```

Then, from the repo root, install everything from `pixi.toml` / `pixi.lock`:

```bash
pixi install
```

Run commands inside the environment with `pixi run <cmd>`, or drop into a shell with `pixi shell`.

## Dora demo

A simple [dora-rs](https://dora-rs.ai) dataflow: one node captures webcam frames and fans them out to
five display nodes over shared memory. It's a minimal example of how nodes, inputs and outputs are wired.

```
camera_capture.py ──image──┬──▶ displayer   (second_frame_displayer.py)
                           ├──▶ displayer2
                           ├──▶ displayer3
                           ├──▶ displayer4
                           └──▶ displayer5
```

| File | Role |
|---|---|
| `dataflow.yml` | The graph: node ids, which script each runs, and how outputs feed inputs |
| `camera_capture.py` | Reads frames with OpenCV, flattens them to a `pyarrow` array and sends them on `image` (frame shape goes in metadata) |
| `second_frame_displayer.py` | Receives `image`, reshapes it back with the metadata, shows it in a window |

Run it:

```bash
pixi run dora run dataflow.yml
```

Press `q` in the *camera capture node* window to stop. Logs for each run land in `out/<run-id>/`.

> `camera_capture.py` opens camera index `2` (`cv2.VideoCapture(2)`). If you get `camera didn't open`,
> change the index to match your machine (`0` is usually the built-in webcam).

## Nav2 quickstart (simulation)

The environment also includes ROS 2 Jazzy + Nav2 + Gazebo via [RoboStack](https://robostack.github.io),
set up per the [Nav2 Getting Started](https://docs.nav2.org/getting_started/) guide.

```bash
pixi run nav2-quickstart   # Gazebo GUI + RViz + Nav2 with a TurtleBot3
pixi run nav2-headless     # same, no Gazebo GUI (RViz only)
pixi run nav2-slam         # build the map live instead of loading the saved one
```

In RViz: click **2D Pose Estimate** within ~60 s of launch, then **Nav2 Goal** to drive.

## Test Rerun.io and DORA

Run:

```bash
pixi run dora run rerun-test.yml
```
