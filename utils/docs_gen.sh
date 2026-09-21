#!/usr/bin/env bash
# Regenerates the checked-in artifacts under docs/generated/ that the docs embed via pymdownx.snippets.
# Deterministic and AI-free on purpose (CI will run it): one Mermaid file per dora dataflow in
# goose-eyes/dataflows/, straight from `dora graph --mermaid`. Run with `pixi run docs-gen`
# (`docs` / `docs-serve` depend on it, so a plain `pixi run docs` is enough).
set -euo pipefail
cd "${PIXI_PROJECT_ROOT:-$(dirname "${BASH_SOURCE[0]}")/..}"

out=docs/generated
mkdir -p "$out"

# Stale files from a renamed / deleted dataflow would keep building fine but lie, so start clean.
rm -f "$out"/*.mmd

for df in goose-eyes/dataflows/*.yml; do
    name="$(basename "$df" .yml)"
    # dora prints a "Paste the above output on https://mermaid.live/ …" hint after the diagram;
    # keep only the flowchart itself so it drops cleanly into a ```mermaid fence.
    dora graph "$df" --mermaid | sed '/^Paste the above output/,$d' | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' > "$out/$name.mmd"
    echo ">> $df -> $out/$name.mmd"
done
