# Adding a development platform

The Jetson is the main target; `osx-arm64` and `linux-64` are the dev platforms so far. Adding another
(say `osx-64` for an Intel Mac) is a `pixi.toml` change; pixi's
[multi-platform docs](https://pixi.sh/latest/workspace/multi_platform_configuration/) cover the
mechanics.

1. **Declare it** — add the platform string to `platforms = [...]` in `pixi.toml`
   (`"linux-64"`, `"win-64"`, `"osx-64"`). Plain strings are fine for laptops; only the Jetson needs
   the named-platform form, because it pins a glibc.
2. **Add it to the `dev` feature** so it gets the laptop substitutes for what the Jetson gets from
   JetPack (conda-forge OpenCV, rerun):

    ```toml
    [feature.dev]
    platforms = ["osx-arm64", "linux-64", "osx-64"]
    ```

    If a substitute needs a per-platform tweak, put it in `[feature.dev.target.<platform>.*]`.
3. **Re-solve and install** — [`pixi lock`](https://pixi.sh/latest/reference/cli/pixi/lock/) solves
   the lock for every platform (this is where you find out if a dependency doesn't exist for the new
   one; ROS 2 from RoboStack is the likely culprit), then `pixi install -e dev`. Commit the whole `pixi.lock`.
4. **Smoke test:**

    ```bash
    pixi run -e dev python -c "import cv2, dora, rerun, rclpy; print(cv2.__version__, rerun.__version__)"
    pixi run -e dev dora run goose-eyes/dataflows/dataflow.yml    # needs a webcam
    ```

Things to know:

- `[dependencies]` is for packages that exist on *every* declared platform; anything else goes in a
  `[target.<platform>.*]` table (or the `dev` feature, for laptop-only packages), or the whole solve fails.
- A `[target.<platform>.activation]` `scripts` list *replaces* the workspace-level one rather than
  adding to it. Only the Jetson has activation scripts today.
- Don't declare `cuda` on any platform (see [Platforms](platforms.md)).
- Laptops are partial support by design: anything hardware-bound (NVIDIA GStreamer, TensorRT) won't run
  there. Note the gap in [Platforms](platforms.md) rather than working around it.
- Windows is untested; the activation scripts are bash and cameras are `/dev/video*`. WSL2 is the
  lower-effort route.
