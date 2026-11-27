# sentry-nav (ROS 2 navigation)

The sentry's Nav2 stack lives in its own repo,
[TAMU-Robomasters/sentry-nav](https://github.com/TAMU-Robomasters/sentry-nav), pulled into Goose Eyes
as a git submodule at `src/ros2/sentry-nav` on the `goose-eyes` branch. That branch is the
Goose Eyes port: ROS 2 **Jazzy** (from RoboStack, through pixi), packages renamed from the Nav2
tutorial's `sam_bot_*` to `sentry_*`, and a Gazebo (Harmonic) sim of the ARCC 1v1 battlefield.

| Package | What it is |
|---|---|
| `sentry_description` | Sentry URDF from the Onshape export, meshes, Gazebo sensors/plugins |
| `sentry_bringup` | Launch files, Nav2/AMCL/SLAM params, maps, the 1v1 world and `sim_chassis` |
| `uart_odom` | Real-robot odometry + `/cmd_vel` bridge over UART. Kept, but not used in sim. It will be replaced by a dora comms node. |
| `mcu_msgs` | Messages for the old AutoX MCU bridge |
| `dual-ldlidar`, `multi-laserscan-toolbox-ros2` | LD19 driver and scan merger (submodules of sentry-nav) |

## Get it

```bash
git clone --recurse-submodules git@github.com:TAMU-Robomasters/Goose-Eyes.git
# or, in an existing clone:
git submodule update --init --recursive
```

`dual-ldlidar` is a private repo cloned over SSH. Without access, init everything else and skip
it when building: the sim doesn't need it.

```bash
git submodule update --init src/ros2/sentry-nav
git -C src/ros2/sentry-nav submodule update --init src/multi-laserscan-toolbox-ros2
```

## Build

The ROS 2 build tools (compilers, colcon, Gazebo, extra ROS packages) are in the `ros-build` pixi
feature, which is part of the `default` (Jetson) and `dev` (laptop) environments.

```bash
pixi shell -e dev            # on the Jetson: pixi shell
cd src/ros2/sentry-nav
colcon build                 # Linux without dual-ldlidar access: add --packages-skip ldlidar ldlidar_component ldlidar_node
source install/setup.bash
```

## Run the 1v1 sim

```bash
ros2 launch sentry_bringup sim_1v1.launch.py            # RViz only
ros2 launch sentry_bringup sim_1v1.launch.py gui:=true  # plus the Gazebo GUI
```

The sentry starts in the red start zone. Send it goals with RViz's **Nav2 Goal** tool.
Launch arguments: `spin_rate` (chassis spin in rad/s, default 4.0, 0 turns it off),
`turret_heading` (world heading in rad the turret holds), `spawn_x` / `spawn_y`, `map`,
`headless_rendering` (EGL sensors with no display, Linux only; defaults on when `DISPLAY` is unset).

### How the sim stands in for the robot

```
Nav2 (base_footprint) ──/cmd_vel (global vx, vy)──► sim_chassis ──x, y, yaw joint velocities──► Gazebo
                                                       │  └─turret joint velocity (hold heading)─► Gazebo
          /odom, TF odom→base_footprint→base_link ◄────┘◄──joint positions (x, y, yaw, turret)────┘
Gazebo LD19 x2 (on the turret) ──/lidar_{left,right}/ldlidar_node/scan──► merger ──/scan (base_footprint)──► AMCL, costmaps
```

- **Spin and global velocity, as on the robot.** The firmware takes a world-frame velocity and
  rotates it into the spinning chassis frame (`rotateVector(-orientation)` in aimbots-dev's
  `chassis_auto_nav_tokyo_command.cpp`) for its wheel kinematics. The sim has no wheels: the
  chassis rides planar joints (world-aligned x and y, plus yaw), so `sim_chassis` sends the global
  velocity straight to the x/y joints and spins the yaw joint.
- **It stays on the floor.** The planar joints are driven by force-limited velocity controllers, so
  walls and bunkers stop the robot, and it can't tip or lift off. The chassis collision shape follows
  the meshes (0.514 m square, corners cut to 0.341 m). A chassis spinning against a wall still rolls
  along it a little, as a real one would; chassis friction is set to 0.3.
- **Nav runs on `base_footprint`.** It follows the robot's position but never rotates relative to
  `odom`, so Nav2's `/cmd_vel` is already the global vector. `base_link` is the spinning chassis.
  The sim rewrites `robot_base_frame`/`base_frame_id` in `nav2_params_real_lidar.yaml` at launch;
  the real launches still use `base_link`.
- **The lidars are on the turret.** In the CAD both LD19s hang upside down from the gimbal yaw stage
  (`part_1`, after joint `revolute_6`), so the sim drives that joint to hold the turret's world
  heading while the chassis spins. The URDF's `lidar_*_link` frames are upright, matching the real
  driver, which undoes the inverted mount with `rot_verse: 'CW'`.
- **The field** (`worlds/1v1_field.sdf`, `maps/1v1_field.{pgm,yaml}`) is generated from the Events
  Manual's 1v1 dimensions (Fig. 4-3, 4-4) by `scripts/gen_1v1_field.py`. Edit the script, not the
  outputs.

## The sentry model

`sentry_description/urdf/sentry_onshape.xacro` is the Onshape URDF export with three edits: mesh
paths point into `sentry_description/meshes/`, the non-ASCII link `17mm_Ü__` is renamed
`barrel_17mm`, and the wheel and pitch joint types are macro parameters (fixed by default). Onshape's
joint names are kept (`revolute_6` = gimbal yaw, `revolute_7` = pitch). A new export means redoing
those edits by hand.

The meshes put the chassis's outer radius at 0.341 m (the swerve module corners), inside the
costmaps' `robot_radius` of 0.35 m.
