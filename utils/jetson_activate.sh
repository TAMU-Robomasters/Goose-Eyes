#!/usr/bin/env bash
# Sourced by pixi when the environment is activated on the `jetson` platform (see [target.jetson] in pixi.toml).
# Makes JetPack's OpenCV and TensorRT Python bindings usable from inside the conda env.
# Runs after conda-forge packages' own activation scripts, which may already export PYTHONPATH
# and LD_LIBRARY_PATH — so everything here prepends rather than overwrites.

# 1. JetPack installs its cv2 / tensorrt modules for the system python3.12 here. Put it ahead of
#    the env's site-packages so `import cv2` gets NVIDIA's 4.8.0 build, GStreamer and all, instead
#    of any conda-forge py-opencv a dependency might drag in transitively.
export PYTHONPATH="/usr/lib/python3.12/dist-packages${PYTHONPATH:+:$PYTHONPATH}"

# 2. Library-mixing guard. conda's `python` carries a DT_RPATH ($ORIGIN/../lib) that the dynamic
#    loader consults for *every* transitive library lookup in the process, while NVIDIA's
#    libopencv_*.so.408 use DT_RUNPATH, which checks LD_LIBRARY_PATH first. Left alone, the OpenCV
#    dependency chain loads the system glib for some libraries and conda's for others, and
#    `import cv2` dies with `libgio-2.0.so.0: undefined symbol: g_variant_builder_init_static`.
#    Putting the env's lib/ first makes every soname both sides have resolve to the (newer) conda
#    copy; libraries conda lacks (libopencv_*.408, GTK2, ffmpeg 6, the NVIDIA stack) still come
#    from the system.
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# 3. Consequence of (2): cv2's GStreamer is now conda's libgstreamer core, which by default only
#    scans the env's own plugin dir. Add the system dir so NVIDIA's plugins (nvarguscamerasrc,
#    nvvidconv, nvv4l2decoder, ...) are found, use the env's out-of-process scanner helper, and
#    keep the registry cache next to the env instead of in ~/.cache, where it would keep
#    invalidating the system GStreamer 1.24's cache (and vice versa).
#    Expect one harmless warning on the first scan: the system libgstgtk.so plugin wants a
#    Wayland symbol conda's libgstgl doesn't export, so it's blacklisted and never retried.
export GST_PLUGIN_PATH="/usr/lib/aarch64-linux-gnu/gstreamer-1.0${GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}"
export GST_PLUGIN_SCANNER="$CONDA_PREFIX/libexec/gstreamer-1.0/gst-plugin-scanner"
export GST_REGISTRY="$CONDA_PREFIX/var/cache/gstreamer-1.0/registry.bin"
mkdir -p "$(dirname "$GST_REGISTRY")"
