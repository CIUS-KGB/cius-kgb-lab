# GitHub Pages fixtures, sync, and merge conflicts

## Why `docs/index.html` conflicts every time

`docs/index.html` and `docs/lab_visualization.html` are **generated** (thousands of lines). Git cannot merge two different generator outputs line-by-line. After `git merge origin/main` (or merging a PR on GitHub), those files often show as **both modified**.

**Do not resolve by editing conflict markers inside the HTML.** You will corrupt the file.

## Fix: regenerate, do not merge

1. Finish the merge attempt locally (or abort and merge again after reading this).
2. From the repo root, refresh fixtures and rebuild Pages HTML:

```bash
python scripts/sync_github_pages_fixtures.py
```

This copies JSON snapshots into `docs/fixtures/` (when the sources exist), then runs `build_github_pages_docs.py` so `docs/` matches current `report` code + those fixtures.

3. Stage only the regenerated/copied artifacts, for example:

```bash
git add docs/fixtures/*.json docs/index.html docs/lab_visualization.html docs/places_map.html docs/introduction.html docs/CIUS_Logo_RGB_Blue_EngUkr.png 2>/dev/null || true
```

Include whatever paths actually changed (`git status`). The logo appears under `docs/` when the build copies it next to `index.html`.

4. Complete the merge commit:

```bash
git commit --no-edit
# or git commit -m "merge origin/main; regenerate Pages docs"
```

## What gets synced (by default)

| Destination under `docs/fixtures/` | Typical source |
|-----------------------------------|----------------|
| `comparison_results.json` | `data/output/comparison_results.json` |
| `places_geocoded.json` | `data/output/places_geocoded.json` |
| `places_extracted.json` | `data/output/places_extracted.json` |
| `comparison_results_experiment_b.json` | `data/experiments/exp_b_free_segment/pipeline_output/comparison_results.json` |

If a source file is missing, that copy is skipped (the previous fixture stays).

The CIUS keyboard logo asset is **`docs/fixtures/CIUS_Logo_RGB_Blue_EngUkr.png`** (`report.__init__` reads from there); the Pages build copies it beside `docs/index.html`.

## Local lab vs Pages site

- **`data/output/manual_analysis_report.html`** — usual local report; driven by **`data/output/`** and your pipeline config.
- **`docs/index.html`** — site root on GitHub Pages; built with **`output.dir` = `docs`** and **`docs/fixtures/comparison_results.json`** as the comparison input (unless you pass another path to `build_github_pages_docs.py`).

After changing pipeline outputs, run **`sync_github_pages_fixtures.py`** before committing if you want the public site to show the same comparison/places/experiment B data as your latest local run.

## CI on `main`

Workflow **Regenerate Pages HTML** (`.github/workflows/regenerate-pages-docs.yml`) rebuilds from fixtures when certain paths change. Keeping `docs/fixtures/*.json` up to date in the branch you merge avoids surprising drift between “what you tested” and “what Pages shows.”
