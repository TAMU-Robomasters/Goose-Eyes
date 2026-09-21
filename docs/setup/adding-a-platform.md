# Adding a development platform

The Jetson is the main target and `osx-arm64` is the only dev platform so far. Adding another (say
`linux-64` for an x86 laptop) is a `pixi.toml` change; pixi's
[multi-platform docs](https://pixi.sh/latest/workspace/multi_platform_configuration/) cover the
mechanics.

1. **Declare it** — add the platform string to `platforms = [...]` in `pixi.toml`
   (`"linux-64"`, `"win-64"`, `"osx-64"`). Plain strings are fine for laptops; only the Jetson needs
   the named-platform form, because it pins a glibc.
2. **Add substitutes** for what the Jetson gets from JetPack. Copy the `osx-arm64` target tables:

    ```toml
    [target.linux-64.dependencies]
    opencv = ">=4.13.0,<5"

    [target.linux-64.pypi-dependencies]
    rerun-sdk = ">=0.38.1, <0.39"
    ```

    Keep the `rerun-sdk` pin equal to `RERUN_VERSION` in `utils/install_jetson_rerun.sh`.
3. **Re-solve and install** — [`pixi lock`](https://pixi.sh/latest/reference/cli/pixi/lock/) solves
   the lock for every platform (this is where you find out if a dependency doesn't exist for the new
   one; ROS 2 from RoboStack is the likely culprit), then `pixi install`. Commit the whole `pixi.lock`.
4. **Smoke test:**

    ```bash
    pixi run python -c "import cv2, dora, rerun, rclpy; print(cv2.__version__, rerun.__version__)"
    pixi run dora run goose-eyes/dataflows/dataflow.yml    # needs a webcam
    ```

Things to know:

- `[dependencies]` is for packages that exist on *every* declared platform; anything else goes in a
  `[target.<platform>.*]` table, or the whole solve fails.
- A `[target.<platform>.activation]` `scripts` list *replaces* the workspace-level one rather than
  adding to it. Only the Jetson has activation scripts today.
- Don't declare `cuda` on any platform (see [Platforms](platforms.md)).
- Laptops are partial support by design: anything hardware-bound (NVIDIA GStreamer, TensorRT) won't run
  there. Note the gap in [Platforms](platforms.md) rather than working around it.
- Windows is untested; the activation scripts are bash and cameras are `/dev/video*`. WSL2 is the
  lower-effort route.
