"""mkdocs-gen-files script: one API page per Python module in goose-eyes/nodes/.

Runs inside `mkdocs build` (see `plugins: gen-files` in mkdocs.yml); nothing is written to
docs/ on disk. Each page is a single mkdocstrings directive, and the nav for the section comes
from the generated SUMMARY.md via mkdocs-literate-nav. Docstrings are parsed statically (griffe),
so the node scripts are never imported — safe even though they open cameras at module level.
"""

from pathlib import Path

import mkdocs_gen_files

NODES = Path("goose-eyes/nodes")
API = Path("api/python")

nav = mkdocs_gen_files.Nav()

for src in sorted(NODES.glob("*.py")):
    if src.name.startswith("_"):
        continue
    module = src.stem
    page = API / f"{module}.md"
    nav[(module,)] = f"{module}.md"

    with mkdocs_gen_files.open(page, "w") as fd:
        fd.write(f"# `{module}`\n\n::: {module}\n")
    # "Edit this page" / source links point at the script itself, not the virtual .md.
    mkdocs_gen_files.set_edit_path(page, Path("..") / src)

with mkdocs_gen_files.open(API / "SUMMARY.md", "w") as fd:
    fd.writelines(nav.build_literate_nav())
