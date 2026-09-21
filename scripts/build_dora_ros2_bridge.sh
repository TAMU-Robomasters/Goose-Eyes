#!/usr/bin/env bash
# Build dora's ROS 2 bridge node (`dora-ros2-bridge-node`) for the ROS distro in this
# pixi env instead of the Humble-only build dora publishes.
#
# Why: dora hard-pins `ros2-client` to `features = ["humble"]` in its workspace
# Cargo.toml (see https://github.com/dora-rs/dora/issues/3554). The only thing that
# feature changes is the rmw Gid size (24 bytes on Humble, 16 on Iron+), so a Jazzy
# build is a one-line patch — but there's no cargo feature to flip, hence this script.
# The `dora-rs-cli` wheel doesn't ship the bridge binary at all, so it needs building
# either way.
#
# Meant to be run through pixi (`pixi run build-dora-ros2-bridge`) so that cargo, git,
# ROS_DISTRO and AMENT_PREFIX_PATH all come from the env. Installs into $CONDA_PREFIX/bin,
# which is first on PATH inside `pixi run` / `pixi shell`.
#
# Skips if the binary is already installed for this tag+distro, so tasks can `depends-on` it
# cheaply. (pixi's own `outputs` cache can't be used: its globs don't see inside .pixi/.)
# Pass --force (or delete the binary) to rebuild.
set -euo pipefail

DORA_TAG="${DORA_TAG:-v1.0.1}"                     # must match dora-rs-cli / dora-rs in pixi.toml
ROS_DISTRO="${ROS_DISTRO:?run this via pixi so ROS_DISTRO is set}"
PREFIX="${CONDA_PREFIX:?run this via pixi so CONDA_PREFIX is set}"
ROOT="${PIXI_PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SRC="$ROOT/.dora-build/dora"                       # gitignored; keeps the cargo cache between runs
BIN="$PREFIX/bin/dora-ros2-bridge-node"
STAMP="$BIN.built-for"                              # "<tag> <distro> patches=<n>" of the installed binary
PATCH_LEVEL=2                                       # bump when the source patches below change, so stale binaries rebuild
WANT="$DORA_TAG $ROS_DISTRO patches=$PATCH_LEVEL"

if [ "${1:-}" != "--force" ] && [ -x "$BIN" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$WANT" ]; then
    echo ">> dora-ros2-bridge-node already built for dora $DORA_TAG / $ROS_DISTRO patches=$PATCH_LEVEL ($BIN); --force to rebuild"
    exit 0
fi

if [ ! -d "$SRC/.git" ]; then
    echo ">> cloning dora $DORA_TAG into $SRC"
    git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$DORA_TAG" https://github.com/dora-rs/dora "$SRC"
fi

cd "$SRC"
# The one-line patch: pick the ros2-client distro feature. Idempotent — `sed -i.bak`
# works on both BSD (macOS) and GNU sed.
sed -i.bak -E "s/^(ros2-client = \{.*features = \[\")[a-z]+(\"\].*)$/\1${ROS_DISTRO}\2/" Cargo.toml
grep -q "features = \[\"${ROS_DISTRO}\"\]" Cargo.toml \
    || { echo "!! failed to patch ros2-client feature in $SRC/Cargo.toml"; exit 1; }
echo ">> ros2-client pinned to: $(grep -E '^ros2-client = ' Cargo.toml)"

# Patch 2: let `topic:` accept namespaced names like Nav2's `/global_costmap/costmap`.
# The bridge builds every topic as `Name::new("/", "<topic sans leading slash>")`, and
# ros2-client's `Name::new` rejects a `/` inside the base name (BadChar). `Name::parse`
# from the same crate splits `/ns/base` into namespace + base and produces the same DDS
# name (`rt/ns/base`) ROS 2 uses, so flat topics like `/scan` are unaffected. Not fixed
# upstream as of dora main (checked 2026-09). Idempotent like the sed above.
MAIN_RS=binaries/ros2-bridge-node/src/main.rs
sed -i.bak "s|ros2_client::Name::new(\"/\", topic_config.topic.trim_start_matches('/'))|ros2_client::Name::parse(\&format!(\"/{}\", topic_config.topic.trim_start_matches('/')))|" "$MAIN_RS"
grep -q 'Name::parse(&format!("/{}", topic_config.topic.trim_start_matches' "$MAIN_RS" \
    || { echo "!! failed to patch namespaced-topic support in $SRC/$MAIN_RS"; exit 1; }
echo ">> namespaced topic names patched in $MAIN_RS"

echo ">> building dora-ros2-bridge-node (release) — first build takes several minutes"
cargo build --release --locked -p dora-ros2-bridge-node

install -m 755 target/release/dora-ros2-bridge-node "$BIN"
echo "$WANT" > "$STAMP"
echo ">> installed $BIN (ROS_DISTRO=$ROS_DISTRO, dora $DORA_TAG)"
