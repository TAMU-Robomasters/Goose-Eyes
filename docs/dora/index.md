# dora

How the dora side is laid out and how to run the demo. The generated graph of the dataflow is on
[Architecture](architecture.md); each node's contract is under [Nodes](nodes/camera_pub.md).

Everything lives in `goose-eyes/`: `dataflows/` holds the dataflow graphs (`*.yml`) and `nodes/` the scripts
they run (a node's `path:` is resolved relative to the dataflow file, hence `../nodes/…`). Logs for each
run land in `out/<run-id>/` next to the dataflow.

## Camera pub/sub demo

A minimal [dora-rs](https://dora-rs.ai) dataflow: one node captures webcam frames, one node displays
them, wired together over shared memory. It shows how nodes, inputs and outputs are connected.

```
camera_pub.py ──image──▶ camera_sub.py
```

| File | Role |
|---|---|
| `dataflows/dataflow.yml` | The graph: node ids, which script each runs, and how outputs feed inputs |
| `nodes/camera_pub.py` | Reads frames with OpenCV, flattens them to a `pyarrow` array and sends them on `image` (frame shape goes in metadata) |
| `nodes/camera_sub.py` | Receives `image`, reshapes it back with the metadata, shows it in a window |

Run it from the repo root. `dora` only exists inside the pixi environment, so either open a shell in it
once or prefix the command with `pixi run`:

```bash
pixi shell                                    # drops you into the env; `exit` to leave
dora run goose-eyes/dataflows/dataflow.yml
```

```bash
pixi run dora run goose-eyes/dataflows/dataflow.yml    # same thing, one command
```

Press `q` in the *camera capture node* window to stop.

> `nodes/camera_pub.py` opens camera index `0` (`cv2.VideoCapture(0)`), usually the built-in webcam. If
> you get `error: camera didn't open`, change the index to match your machine.

## rerun

The environment includes the [rerun](https://rerun.io) SDK for visualisation, but no dataflow logs to it
yet. On the Jetson it is installed outside the lock — run `pixi run install-rerun` once (see
[Platforms](../setup/platforms.md)); on a laptop it comes with `pixi install`.
