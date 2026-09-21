# Platforms

`pixi.toml` declares two [platforms](https://pixi.sh/latest/workspace/multi_platform_configuration/),
and one `pixi.lock` is solved for both. **`jetson`** is the main target — the robot runs there.
**`osx-arm64`** (dev laptops) is partial support: same dora / ROS 2 / rerun stack, but conda-forge
OpenCV instead of JetPack's and no CUDA / TensorRT, so most things can be developed there but not
everything will run.

| | `jetson` (main) | `osx-arm64` (dev, partial) |
|---|---|---|
| Hardware / OS | AGX Orin / Orin NX on **JetPack 7**: Ubuntu 24.04, CUDA 13.2 | Apple Silicon Mac |
| OpenCV | **JetPack's 4.8** (GStreamer with the NVIDIA plugins) | conda-forge 4.13 |
| TensorRT | JetPack's 10.16 | — |
| numpy | 1.26 (`<2`, forced by JetPack's cv2) | 2.x |
| rerun-sdk | `pixi run install-rerun`, outside the lock | in the lock |

The commands are the same on both: `pixi install`, `pixi shell` / `pixi run …`.

## How it's wired

**The `jetson` platform.** It's a *named* platform entry in `pixi.toml`
(`{ name = "jetson", platform = "linux-aarch64", glibc = "2.39" }`): it solves for `linux-aarch64` but
pins the glibc a JetPack 7 board has, so `pixi install` on an older JetPack (Ubuntu 22.04) refuses
instead of producing a half-working env. Jetson-only dependencies and activation live under
`[target.jetson.*]`, laptop substitutes under `[target.osx-arm64.*]`
([targets](https://pixi.sh/latest/reference/pixi_manifest/#the-target-table),
[virtual packages](https://pixi.sh/latest/workspace/system_requirements/)).

**JetPack's OpenCV / TensorRT.** The Jetson target declares no conda OpenCV. Instead an
[activation script](https://pixi.sh/latest/reference/pixi_manifest/#the-activation-table),
[`utils/jetson_activate.sh`](https://github.com/TAMU-Robomasters/Goose-Eyes/blob/main/utils/jetson_activate.sh),
runs whenever the env is entered and puts JetPack's `cv2` / `tensorrt` on `PYTHONPATH`, the env's `lib/`
first on `LD_LIBRARY_PATH` (avoids a glib clash between conda and NVIDIA libraries), and the NVIDIA
GStreamer plugins on `GST_PLUGIN_PATH`. The script's comments explain each line. Check it on a board:

```bash
pixi run python -c "import cv2, tensorrt; print(cv2.__version__, cv2.__file__, tensorrt.__version__)"
# 4.8.0 /usr/lib/python3.12/dist-packages/cv2/__init__.py 10.16.2.10
```

**rerun on the Jetson is installed outside the lock.** JetPack's `cv2` needs numpy 1.x, every recent
`rerun-sdk` *declares* numpy ≥ 2, and pixi can't override that metadata — so the two can't be in one
solve. rerun 0.38.1 actually runs fine on numpy 1.26, so
[`utils/install_jetson_rerun.sh`](https://github.com/TAMU-Robomasters/Goose-Eyes/blob/main/utils/install_jetson_rerun.sh)
installs the wheel with `--no-deps` (`pixi run install-rerun`; no-op once installed, `--force` to
reinstall). Its real runtime deps are in the Jetson solve. Keep the version in that script equal to the
`rerun-sdk` pin in `pixi.toml` so both platforms speak the same rerun wire format.

**No CUDA declared.** Adding `cuda = "13.2"` to the `jetson` entry would make conda-forge prefer
CUDA builds of packages, which drag in conda's own CUDA runtime instead of JetPack's. GPU Python packages
on the Jetson should come from NVIDIA's JetPack wheels.

## Gotchas

- On the Jetson, `pixi run` / `pixi shell` put conda's `lib/` first on `LD_LIBRARY_PATH`, so system
  tools run from inside the env (`nvcc`, `tegrastats`, …) see conda's libraries too. Harmless so far; run
  a system tool outside pixi if it misbehaves.
