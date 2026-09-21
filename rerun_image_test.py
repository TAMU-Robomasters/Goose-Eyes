"""Rerun view of the Nav2 stack (via the dora ROS 2 bridge) plus the webcam.

Every ROS message arrives as a pyarrow StructArray with ONE row (one message), laid
out exactly like the ROS message definition: a nested message is a nested Struct, a
`T[]` sequence is a length-1 List whose single row holds the whole sequence, so
`.field("ranges").values` is the flat FloatArray. Type mapping:
https://dora-rs.ai/dora/advanced/ros2-bridge.html#mapping-ros2-types-to-arrow-types

Rerun side mirrors ROS TF with named coordinate frames: every TransformStamped becomes a
`Transform3D(parent_frame=, child_frame=)`, and each data entity just declares which
frame it lives in with `CoordinateFrame(header.frame_id)` — no hand-built chain. Costmaps
use the `GridMap` archetype (built for nav_msgs/OccupancyGrid). This follows rerun's own
ROS example: https://github.com/rerun-io/rerun/blob/main/examples/python/ros_node/main.py
"""

import time

import numpy as np
import pyarrow as pa
import rerun as rr
import rerun.blueprint as rrb
from dora import Node

# Frame whose axes mark "the robot". Nav2's robot_base_frame is base_link both in the
# TB3 sim (base_footprint->base_link comes over /tf_static) and on the real robot.
ROBOT_FRAME = "base_link"
WORLD_FRAME = "map"  # Nav2 global_frame; the root every other frame hangs off

# True: log everything as static data — rerun keeps only the latest value per entity, so
# viewer memory stays flat, but there is no timeline to scrub. False: timestamped logging
# (history accumulates until the viewer's memory limit, then the oldest data is dropped).
STREAM_ONLY = True

# Everything visual lives under this entity; the 3D view has it as origin. The ROS `map`
# frame is attached to its implicit frame (`tf#/world`) so the whole TF tree is reachable
# from the view's root.
WORLD = "world"
TF = f"{WORLD}/tf"  # one child entity per TF child frame: world/tf/odom, world/tf/base_link, …


# --- pyarrow helpers ---------------------------------------------------------------
def scalar(msg: pa.StructArray, *path: str):
    """Walk nested struct fields of a one-row message and return the Python value."""
    arr = msg
    for name in path:
        arr = arr.field(name)
    return arr[0].as_py()


def xyz(struct: pa.StructArray, *names: str) -> np.ndarray:
    """Stack the given float fields of a StructArray column-wise -> (N, len(names))."""
    return np.column_stack([struct.field(n).to_numpy() for n in names])


def frame_id(msg: pa.StructArray) -> str:
    # tf2 tolerates a legacy leading "/" on frame ids; rerun would treat it as a new name.
    return scalar(msg, "header", "frame_id").lstrip("/")


# --- handlers -------------------------------------------------------------------------
def on_tf(msg: pa.StructArray, static: bool = STREAM_ONLY) -> None:
    """tf2_msgs/TFMessage -> one Transform3D per edge, keyed by child frame."""
    tfs = msg.field("transforms").values  # StructArray, one row per TransformStamped
    parents = tfs.field("header").field("frame_id").to_pylist()
    children = tfs.field("child_frame_id").to_pylist()
    t = xyz(tfs.field("transform").field("translation"), "x", "y", "z")
    q = xyz(tfs.field("transform").field("rotation"), "x", "y", "z", "w")
    for parent, child, ti, qi in zip(parents, children, t, q):
        child = child.lstrip("/")
        rr.log(
            f"{TF}/{child}",
            rr.Transform3D(
                translation=ti,
                quaternion=rr.Quaternion(xyzw=qi),
                parent_frame=parent.lstrip("/"),
                child_frame=child,
            ),
            static=static,
        )


def on_scan(msg: pa.StructArray) -> None:
    """sensor_msgs/LaserScan -> Points3D (z=0) in the scan's own frame."""
    angle_min = scalar(msg, "angle_min")
    angle_increment = scalar(msg, "angle_increment")
    range_min = scalar(msg, "range_min")
    range_max = scalar(msg, "range_max")
    ranges = msg.field("ranges").values.to_numpy()

    # Angles from len(ranges), not (max-min)/inc, which can round to len±1.
    angles = angle_min + angle_increment * np.arange(len(ranges))
    ok = np.isfinite(ranges) & (ranges >= range_min) & (ranges <= range_max)
    r, a = ranges[ok], angles[ok]
    points = np.column_stack((r * np.cos(a), r * np.sin(a), np.zeros_like(r)))

    rr.log(
        f"{WORLD}/scan",
        rr.CoordinateFrame(frame_id(msg)),
        rr.Points3D(points, radii=0.02, colors=[255, 165, 0]),
        static=STREAM_ONLY,
    )


def on_path(msg: pa.StructArray, entity: str, color: list[int]) -> None:
    """nav_msgs/Path -> one LineStrips3D in the path's frame (map for /plan, odom for /local_plan)."""
    poses = msg.field("poses").values  # StructArray, one row per PoseStamped
    pts = xyz(poses.field("pose").field("position"), "x", "y", "z")
    # Nav2 publishes an empty path once the goal is reached.
    strips = [pts] if len(pts) >= 2 else []
    rr.log(
        entity,
        rr.CoordinateFrame(frame_id(msg)),
        rr.LineStrips3D(strips, radii=0.02, colors=color),
        static=STREAM_ONLY,
    )


def on_costmap(
    msg: pa.StructArray,
    entity: str,
    colormap: rr.components.Colormap,
    draw_order: float,
) -> None:
    """nav_msgs/OccupancyGrid -> GridMap. Cells are int8: -1 unknown, 0 free, 1..100 cost."""
    width = scalar(msg, "info", "width")
    height = scalar(msg, "info", "height")
    grid = msg.field("data").values.to_numpy().reshape(height, width)
    # ROS row 0 is the cell at the origin (bottom-left); rerun image buffers are top-row first.
    # int8 -> uint8 reinterprets -1 as 255, which the Rviz* colormaps treat as "unknown".
    image = np.flipud(grid).astype(np.uint8)

    origin = msg.field("info").field("origin")
    rr.log(
        entity,
        rr.CoordinateFrame(frame_id(msg)),
        rr.GridMap(
            data=image.tobytes(),
            format=rr.components.ImageFormat(
                width=width, height=height, color_model="L", channel_datatype="U8"
            ),
            cell_size=scalar(msg, "info", "resolution"),
            # Pose of the lower-left cell corner in the map's frame — straight from MapMetaData.origin.
            translation=xyz(origin.field("position"), "x", "y", "z")[0],
            quaternion=rr.Quaternion(
                xyzw=xyz(origin.field("orientation"), "x", "y", "z", "w")[0]
            ),
            colormap=colormap,
            draw_order=draw_order,  # higher draws on top where the two costmaps overlap
            opacity=0.75,
        ),
        static=STREAM_ONLY,
    )


def setup_static() -> None:
    """Things logged once: view coordinates, the map<->world link, axes, blueprint."""
    rr.log(WORLD, rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)

    # Attach the ROS root frame to the world entity's implicit frame (identity) and mark
    # the world origin with 1 m axes. The whole TF tree resolves from here.
    rr.log(
        f"{TF}/{WORLD_FRAME}",
        rr.Transform3D(parent_frame=f"tf#/{WORLD}", child_frame=WORLD_FRAME),
        rr.TransformAxes3D(1.0, show_frame=True),
        static=True,
    )
    # Robot axes: TransformAxes3D draws the Transform3D on the same entity, so it sits on
    # the TF edge whose child is the robot frame (the edge itself arrives via /tf).
    rr.log(f"{TF}/{ROBOT_FRAME}", rr.TransformAxes3D(0.3, show_frame=True), static=True)

    rr.send_blueprint(
        rrb.Horizontal(
            rrb.Spatial3DView(
                origin=WORLD,
                name="Nav",
                # Resolve everything relative to the ROS map frame.
                spatial_information=rrb.archetypes.SpatialInformation(
                    target_frame=WORLD_FRAME
                ),
                # Start looking straight down (+y up on screen, like RViz top-down); everything
                # nav-related is at z≈0 so the scene is planar in practice — orbit to tilt.
                eye_controls=rrb.archetypes.EyeControls3D(
                    position=[0.0, 0.0, 15.0],
                    look_target=[0.0, 0.0, 0.0],
                    eye_up=[0.0, 1.0, 0.0],
                ),
            ),
            rrb.Spatial2DView(origin="camera", name="Camera"),
            column_shares=[3, 1],
        )
    )


def main() -> None:
    node = Node()
    rr.init("camera_test")
    # The spawned viewer also runs a gRPC server that buffers every message for late-joining
    # viewers (1 GiB by default) — static logging doesn't shrink that, so cap it.
    rr.spawn(server_memory_limit="256MB")
    setup_static()

    for event in node:
        if event["type"] == "INPUT":
            if event["id"] == "image":
                md = event["metadata"]
                shape = md["shape"]
                pub_time = md["time"]
                image_raveled = event["value"].to_numpy()
                image = image_raveled.reshape(shape)
                if not STREAM_ONLY:
                    rr.set_time("main", duration=pub_time)
                rr.log(
                    "camera/image",
                    rr.Image(image, color_model="BGR"),
                    static=STREAM_ONLY,
                )
                continue

            # ROS data: wall-clock receive time. Header stamps are sim time under use_sim_time
            # and would not line up with the camera on the same timeline.
            if not STREAM_ONLY:
                rr.set_time("main", duration=time.time())
            msg: pa.StructArray = event["value"]
            match event["id"]:
                case "tf":
                    on_tf(msg)
                case "tf_static":
                    on_tf(msg, static=True)
                case "scan":
                    on_scan(msg)
                case "plan":
                    on_path(msg, f"{WORLD}/plan", [0, 255, 0])
                case "local_plan":
                    on_path(msg, f"{WORLD}/local_plan", [255, 0, 255])
                case "global_costmap":
                    on_costmap(
                        msg,
                        f"{WORLD}/costmap/global",
                        rr.components.Colormap.RvizCostmap,
                        draw_order=1.0,
                    )
                case "local_costmap":
                    on_costmap(
                        msg,
                        f"{WORLD}/costmap/local",
                        rr.components.Colormap.Costmap,
                        draw_order=2.0,
                    )
                case _:
                    raise ValueError(f"Unknown input id: {event['id']}")
        elif event["type"] == "STOP":
            break


if __name__ == "__main__":
    main()
