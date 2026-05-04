# Vozmezdie framework

Modular pipeline for expert-grounded LLM evaluation on Cold War archival documents. This repo defines the **structure** and **contracts**; implementation can live here or plug in from the main Vozmezdie codebase.

**See [docs/agents/FRAMEWORK.md](docs/agents/FRAMEWORK.md)** for the pipeline overview, data shapes, and module contracts. **See [AGENTS.md](AGENTS.md)** for guidance for AI agents and contributors (workflows, recent work, next priority). All agent guides: [docs/agents/](docs/agents/).

**Source repository:** [github.com/Pivoslav/vozmezdie](https://github.com/Pivoslav/vozmezdie).

## Pipeline at a glance

1. **Ingest** — Discover/load documents (by path or adapter).
2. **LLM extraction** — Get phrases + category + framing per document (swap backend without changing the rest).
3. **Ground truth load** — Load human-coded rows in the same shape.
4. **Compare** — Align LLM vs human, compute category/framing/both accuracy.
5. **Report** — Produce HTML (tabs, comparison table, document text view, glossary).

## Run

```bash
# Full pipeline (fixture data + stub LLM; no Ollama required)
python run.py

# Regenerate report only from last run’s saved results (no LLM)
python run_report_only.py
# Or: python run_report_only.py path/to/comparison_results.json
```

Output: `data/output/manual_analysis_report.html` and `data/output/comparison_results.json`.

### PDF scans in the report (local vs hosted HTTPS)

- Keep `original_pdfs/` as described in **`original_pdfs/PLACE_PDFS_HERE.txt`**.
- For **embedded PDF iframes** (Research Lab + GitHub Pages), **`raw.githubusercontent.com` is a poor choice**: it sends `X-Frame-Options: deny` and often `Content-Type: application/octet-stream`, so iframes stay blank and clicks may force download.
- Prefer **jsDelivr** (same repo paths, branch pinned), base URL with **no trailing slash**:

  `https://cdn.jsdelivr.net/gh/Pivoslav/vozmezdie@main`

  Set **`documents.pdf_public_base_url`** to that value (see `config/pipeline_config.example.json`). URLs become `…/original_pdfs/<document_id>/<file>.pdf` under that base.

- For **GitHub Pages** (`scripts/build_github_pages_docs.py`): the builder copies **`original_pdfs/` → `docs/original_pdfs/`** and emits **same-origin** PDF paths (no third-party iframe). **Commit `docs/original_pdfs/` with `docs/index.html`** when you deploy, or the embedded scans will 404.

**CLI:** `python run.py --agent-assessments` (use `agent_assessments.json` instead of LLM); `python run.py --use-ollama` (use Ollama); `python run.py --report-only` (regenerate HTML from saved JSON). **Tests:** `pytest tests/ -v`

## Layout

```
vozmezdie_framework/
├── docs/agents/       # Agent guides (see docs/agents/README.md)
├── README.md          # This file
├── run.py             # Full pipeline orchestrator
├── run_report_only.py # Regenerate report from saved JSON
├── config/            # pipeline_config.example.json, taxonomy.json
├── ingest/            # Document discovery and load
├── llm/               # LLM extraction (stub or Ollama)
├── ground_truth/      # Load human-coded CSVs (or stub)
├── compare/           # Align rows + accuracy metrics
├── report/            # Build HTML (tabs, table, document text view, glossary)
├── original_pdfs/     # PDF scans per document_id (optional public_base URL for hosting)
└── data/
    ├── input/         # Optional: put .txt documents here
    ├── ground_truth/  # Optional: put CSVs here (doc_id in filename)
    └── output/        # Report HTML + comparison_results.json
```

## Status

- **Done**: Full pipeline with stubs and optional Ollama adapter; config (`use_fixture`); document text view and glossary (definitions from `Categories Explained.html`); agent assessments mode (`--agent-assessments`); `export_segments_only.py` for blind assessment; intermediate JSON; `run_report_only.py`; tests (compare, ingest, pipeline smoke).
- **Next**: See [docs/agents/NEXT_STEPS.md](docs/agents/NEXT_STEPS.md) and [docs/agents/AGENT_HANDOFF.md](docs/agents/AGENT_HANDOFF.md); or point config at real `data/input`; set `use_fixture: false` to run with Ollama.
