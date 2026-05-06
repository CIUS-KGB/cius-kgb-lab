# Agent Guides — Vozmezdie Framework

Essential documentation for AI agents and contributors. Start here.

---

## Quick Start

1. **Read first:** [AGENT_HANDOFF.md](AGENT_HANDOFF.md) — user feedback, implementation plan, aesthetic direction, outside-the-box ideas.
2. **UX backlog (canonical):** [UI_SCOPE_AND_ROADMAP.md](UI_SCOPE_AND_ROADMAP.md) — full meeting-derived scope, decisions, epics, statuses.
3. **UI ↔ data labels:** [UI_LABEL_MAP.md](UI_LABEL_MAP.md) — Specific Details / Ideological Layers vs canonical taxonomy strings (UI-only policy).
4. **Project context:** [AGENTS.md](../AGENTS.md) (root) — summary, key paths, where to edit.
5. **Pipeline contracts:** [FRAMEWORK.md](FRAMEWORK.md) — data shapes, module boundaries.

---

## Index by Purpose

| When you need… | Read |
|----------------|------|
| **Experiment redo: paths, archive, commands** | [NEXT_AGENT_EXPERIMENT_SETUP.md](NEXT_AGENT_EXPERIMENT_SETUP.md) |
| **Experiment redo: taxonomy & agent prompts (A vs B)** | [EXPERIMENT_AGENT_PROMPTS.md](EXPERIMENT_AGENT_PROMPTS.md) |
| **Handoff for next session** | [AGENT_HANDOFF.md](AGENT_HANDOFF.md) |
| **UX/UI roadmap & meeting scope** | [UI_SCOPE_AND_ROADMAP.md](UI_SCOPE_AND_ROADMAP.md) |
| **UI display names vs stored taxonomy** | [UI_LABEL_MAP.md](UI_LABEL_MAP.md) |
| **Handoff for fork** | [HANDOFF_FOR_FORK.md](HANDOFF_FOR_FORK.md) |
| **Project summary, paths, workflows** | [AGENTS.md](../AGENTS.md) |
| **Pipeline structure, data shapes, contracts** | [FRAMEWORK.md](FRAMEWORK.md) |
| **Recent completions, data locations, task instructions** | [NEXT_STEPS.md](NEXT_STEPS.md) |
| **Design ideas, known issues, incremental fixes** | [DESIGN_EXPLORATION.md](DESIGN_EXPLORATION.md) |
| **Grand design: layout, features, roadmap, visual direction** | [GRAND_DESIGN_PLAN.md](GRAND_DESIGN_PLAN.md) |
| **How to perform manual assessment (taxonomy, blind mode)** | [INSTRUCTIONS_AGENT_ASSESSMENT.md](INSTRUCTIONS_AGENT_ASSESSMENT.md) |
| **Experiment: assess framing without Generic / Neutral** | [INSTRUCTIONS_EXPERIMENT_NO_GENERIC_FRAMING.md](INSTRUCTIONS_EXPERIMENT_NO_GENERIC_FRAMING.md) |
| **Ground truth from HTML (loading, contract, checklist)** | [INSTRUCTIONS_GROUND_TRUTH_HTML.md](INSTRUCTIONS_GROUND_TRUTH_HTML.md) |
| **Document text view behaviour, dropdown/span fixes** | [TEXT_VIEW_ASSESSMENT.md](TEXT_VIEW_ASSESSMENT.md) |
| **Places map (extraction, geocoding, report integration)** | [PLACES_MAP_REFERENCE.md](PLACES_MAP_REFERENCE.md) |
| **GitHub Pages: sync fixtures, regenerate docs, fix HTML merge conflicts** | [PAGES_SYNC_AND_MERGE_CONFLICTS.md](PAGES_SYNC_AND_MERGE_CONFLICTS.md) |
| **Taxonomy churn, report regen, viz/Cyrillic/word-cloud notes (Apr 2026)** | [REPORT_AND_TAXONOMY_UPDATES.md](REPORT_AND_TAXONOMY_UPDATES.md) |
| **Baseline before per-document viz + dynamic taxonomy** | [PER_DOC_VIZ_BASELINE.md](PER_DOC_VIZ_BASELINE.md) |

---

## File Summary

| File | Contents |
|------|----------|
| **AGENT_HANDOFF.md** | Primary handoff. User feedback, approved features, tabled items, archival+KGB aesthetic, visualization ideas, phased implementation plan. |
| **UI_SCOPE_AND_ROADMAP.md** | Canonical UX backlog from stakeholder meetings; decisions D1–D5; epics E0–E7; deferred taxonomy-data work called out explicitly. |
| **UI_LABEL_MAP.md** | Umbrella UI terms (Specific Details, Ideological Layers) mapped to JSON fields and taxonomy ids; UI-only vs data migration policy. |
| **HANDOFF_FOR_FORK.md** | Fork handoff. Snapshot summary, five new viz, fixes (Mismatch Flow, Term x Framing Heatmap), key paths, verification notes. |
| **AGENTS.md** | Root-level entry. Project summary, key paths, recent work, next priority. |
| **FRAMEWORK.md** | Pipeline overview, data shapes, module contracts. Required for understanding ingest/llm/ground_truth/compare/report. |
| **NEXT_STEPS.md** | Recent completions, data locations, config notes, simple instructions for next agent. |
| **DESIGN_EXPLORATION.md** | Known issues (segment search, dropdown, substring overlap), design ideas by area, recommended priority order. |
| **GRAND_DESIGN_PLAN.md** | Layout options, user personas, feature inventory, visual directions, phased roadmap, insights and visualizations. |
| **INSTRUCTIONS_AGENT_ASSESSMENT.md** | Taxonomy labels, assessment modes (standard vs fresh blind), workflow, document status. |
| **INSTRUCTIONS_EXPERIMENT_NO_GENERIC_FRAMING.md** | Experiment: Cursor agent assesses framing without Generic / Neutral; new data files, no overwrite. |
| **INSTRUCTIONS_GROUND_TRUTH_HTML.md** | How to load ground truth from HTML; contract and checklist. |
| **TEXT_VIEW_ASSESSMENT.md** | Document text view: server-filled vs table-built, dropdown population, known fixes. |
| **PLACES_MAP_REFERENCE.md** | Places pipeline, report integration, troubleshooting. |
| **PAGES_SYNC_AND_MERGE_CONFLICTS.md** | Sync local JSON into `docs/fixtures/`, regenerate Pages HTML; fix merge conflicts without hand-editing generated HTML. |
| **REPORT_AND_TAXONOMY_UPDATES.md** | Taxonomy churn notes, report regeneration, viz/Cyrillic/word cloud. |
| **PER_DOC_VIZ_BASELINE.md** | Baseline before per-document viz + dynamic taxonomy. |
