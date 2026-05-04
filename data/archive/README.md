# Archive (`data/archive`)

Folders named **`pre_experiment_redo_<UTC-timestamp>`** hold snapshots of **`data/output`** taken when **`scripts/prepare_experiment_redo.py`** runs **without** `--no-archive`.

Each contains:

- **`output/`** — Previous reports, JSON, synonym chunks, etc.
- **`README_RESTORE.txt`** — Short restore instructions.

Do not delete without confirming nobody needs the snapshot.
