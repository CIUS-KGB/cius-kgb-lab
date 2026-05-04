Committed snapshots for reproducible GitHub Pages builds.

- comparison_results.json — comparison_by_doc payload passed to the HTML generator.
- places_geocoded.json / places_extracted.json — Places map markup.

Refresh after a new corpus run: copy from data/output/ into this folder, rebuild docs with
python scripts/build_github_pages_docs.py, then commit.
