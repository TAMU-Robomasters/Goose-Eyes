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

## ROS 2 image pub/sub (no dora, no rerun)

The same webcam demo as plain ROS 2 Python nodes, for comparison. One node grabs frames with OpenCV and
publishes them as `sensor_msgs/Image` on `/camera/image_raw`; the other subscribes, rebuilds the frame with
numpy, and shows it. Both nodes open a window. No colcon build, no `cv_bridge` — a `bgr8` `Image` is just
`frame.tobytes()` plus `height`/`width`/`step`.

| File | Role |
|---|---|
| `ros2_pubsub/image_publisher.py` | Timer at `fps` (default 30) → `cap.read()` → resize 640×480 → publish → `cv2.imshow` |
| `ros2_pubsub/image_subscriber.py` | `np.frombuffer(msg.data).reshape(h, w, 3)` → `cv2.imshow`; logs pub→sub latency from `header.stamp` |

Run each in its own terminal (press `q` in a window to quit that node):

```bash
pixi run ros-image-pub --ros-args -p camera_index:=2   # default index is 0
pixi run ros-image-sub
```

> **Use the pixi tasks, not `pixi run python ros2_pubsub/...`.** A 640×480 `bgr8` frame is ~921 KB. Fast DDS's
> shared-memory transport doesn't work in this macOS env, so by default it falls back to UDP loopback, where
> datagrams that large mostly get dropped — the subscriber sees ~0.5 Hz. The tasks set
> `FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA?max_msg_size=4MB&sockets_size=4MB` (user data over TCP), which gets
> the full rate. It's per-task rather than global because the dora ros2 bridge is UDP-only.

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

## ROS 2 ↔ dora bridge (Jazzy build)

`rerun-ros-dora.yml` pulls the ROS 2 `/scan` topic into dora with a `ros2:` node. dora runs
those through a separate binary, `dora-ros2-bridge-node`, which the `dora-rs-cli` wheel does
**not** ship — and the copies dora does publish are built for ROS 2 **Humble** only
([dora-rs/dora#3554](https://github.com/dora-rs/dora/issues/3554)). On this repo's Jazzy env
that shows up as:

```
ERROR ros2_client::distributions: ROS_DISTRO='jazzy' but ros2-client was built for 'humble'.
```

Topics may still flow, but the dora node is invisible to `ros2 node list` and services/actions
break. So we build the bridge ourselves, patched for Jazzy, from inside the pixi env:

```bash
pixi run build-dora-ros2-bridge   # one-time, ~5–10 min; clones dora v1.0.1 into .dora-build/
pixi run rerun-ros                # runs rerun-ros-dora.yml (builds the bridge first if missing)
```

`pixi install` alone can't do this — pixi has no post-install hooks — but the `rerun-ros` task
`depends-on` the build, and the script exits immediately once the binary is installed
(`pixi run build-dora-ros2-bridge --force` rebuilds). Add the same
`depends-on = ["build-dora-ros2-bridge"]` to any new task that uses a `ros2:` node.

What the script does ([`scripts/build_dora_ros2_bridge.sh`](scripts/build_dora_ros2_bridge.sh)):
clone `dora-rs/dora` at the tag matching `dora-rs-cli` in `pixi.toml`, change the one line
`ros2-client = { …, features = ["humble"] }` → `["jazzy"]` in its workspace `Cargo.toml`, then
`cargo build --release -p dora-ros2-bridge-node` and copy the binary into the env's `bin/`.
`cargo`, `git`, `ROS_DISTRO` and `AMENT_PREFIX_PATH` all come from the pixi env, so it works the
same on macOS and the Jetson (linux-aarch64). macOS needs the Xcode Command Line Tools for the
linker (`xcode-select --install`).

Gotchas:
- If you bump `dora-rs-cli` / `dora-rs` in `pixi.toml`, also bump `DORA_TAG` in the script and
  `rm -rf .dora-build` so it re-clones.
- If you also have a `cargo install`ed `dora-ros2-bridge-node` in `~/.cargo/bin`, the pixi one
  wins inside `pixi run`/`pixi shell` (env `bin/` is first on `PATH`), but a bare `dora run`
  outside pixi will pick up the Humble one.
- Once upstream ships a distro feature / Jazzy build (see the issue), this whole section can go.
