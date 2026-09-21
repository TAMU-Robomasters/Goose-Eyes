# Updating the docs

The site is [MkDocs](https://www.mkdocs.org) + Material, configured in `mkdocs.yml`, with the pages in
`docs/`. The toolchain is its own pixi environment (`docs`), so it never touches the runtime env; the
tasks below find that environment on their own.

## The three commands

```bash
pixi run docs-serve    # live preview at http://127.0.0.1:8000 — edit a page, the browser reloads
pixi run docs          # full build into site/ with --strict: broken links and nav mistakes fail it
pixi run docs-gen      # only regenerate docs/generated/ (dora graph → Mermaid); the other two run it first
```

`site/` is build output and gitignored. `docs/generated/` **is** checked in — commit it when a dataflow
changes, so a `--strict` build is reproducible without dora installed.

## When you change…

| you changed | update |
|---|---|
| a dataflow YAML | nothing by hand — `pixi run docs-gen` regenerates the diagram. If a node was added/removed, add/remove its page under `docs/dora/nodes/` and its line in the `nav:` of `mkdocs.yml`. |
| a node's inputs, outputs, metadata or rate | its page in `docs/dora/nodes/` — the tables are the contract; keep them true. |
| a docstring | nothing — the API pages are rendered from the source at build time. |
| `pixi.toml` platforms or targets | `docs/setup/platforms.md` / `docs/setup/adding-a-platform.md`. |
| a page's location or name | the `nav:` in `mkdocs.yml`, and any links to it (`--strict` will tell you). |

Conventions: mark anything you don't know as `TODO` rather than guessing, and never write a "Why"
for a decision you didn't make — a `TODO: rationale` is more useful than an invented one. Docstrings
are Google style. Repo files that aren't pages get linked with a full GitHub URL, since MkDocs only
resolves links inside `docs/`.

