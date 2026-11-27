# sentry-nav (ROS 2 navigation)

The sentry's Nav2 stack lives in its own repo,
[TAMU-Robomasters/sentry-nav](https://github.com/TAMU-Robomasters/sentry-nav), pulled into Goose Eyes
as a git submodule at `goose-eyes/ros2/sentry-nav` on the `goose-eyes` branch.v1 battlefield.

| Package | What it is |
|---|---|
| `sentry_description` | Sentry URDF, meshes, Gazebo sensors/plugins |
| `sentry_bringup` | Launch files, Nav2/AMCL/SLAM params, maps, the 1v1 world and `sim_chassis` |
| `uart_odom` | Real-robot odometry + `/cmd_vel` bridge over UART. Kept, but not used in sim. It will be replaced by a dora comms node. |
| `mcu_msgs` | Messages for the old AutoX MCU bridge |
| `dual-ldlidar`, `multi-laserscan-toolbox-ros2` | LD19 driver and scan merger (submodules of sentry-nav) |

## Get it

```bash
git submodule update --init goose-eyes/ros2/sentry-nav
git -C goose-eyes/ros2/sentry-nav submodule update --init src/multi-laserscan-toolbox-ros2
```

## Build

The ROS 2 build tools (compilers, colcon, Gazebo, extra ROS packages) are in the `ros-build` pixi
feature, which is part of the `default` (Jetson) and `dev` (laptop) environments.

```bash
pixi shell -e dev            # on the Jetson: `pixi shell`
cd goose-eyes/ros2/sentry-nav
colcon build                 
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
`headless_rendering` (Linux only; defaults on when `DISPLAY` is unset).
