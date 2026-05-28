"""Sync places_extracted.json and places_geocoded.json from full-document corpus scan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPORT_ROOT = Path(__file__).resolve().parent.parent


def _import_geocode_places_module() -> Any:
    path = _REPORT_ROOT / "scripts" / "geocode_places.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location("vozmezdie_geocode_places", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load geocode_places from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _places_output_dir(config: Dict[str, Any], root: Path) -> Path:
    out = config.get("output", {}).get("dir", "data/output")
    path = Path(out)
    if not path.is_absolute():
        path = root / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def sync_places_artifacts(
    documents: List[Dict[str, Any]],
    config: Dict[str, Any],
    root: Optional[Path] = None,
    *,
    comparison_by_doc: Optional[Dict[str, Dict[str, Any]]] = None,
    geocode_online: bool = False,
) -> Dict[str, Path]:
    """
    Regenerate places JSON from independent corpus gazetteer scan.

    Does not use taxonomy Places labels. comparison_by_doc is optional and only
    used to attach related_row_index hints for navigation convenience.
    """
    if root is None:
        root = _REPORT_ROOT
    out_dir = _places_output_dir(config, root)
    extracted_path = out_dir / "places_extracted.json"
    geocoded_path = out_dir / "places_geocoded.json"

    from places.corpus_extract import extract_from_documents

    alignments_by_doc: Dict[str, Dict[str, Any]] = {}
    align_path = out_dir / "bilingual_alignments.json"
    if align_path.exists():
        try:
            with open(align_path, encoding="utf-8") as f:
                alignments_by_doc = json.load(f).get("by_doc") or {}
        except Exception:
            pass

    extracted = extract_from_documents(
        documents,
        comparison_by_doc=comparison_by_doc,
        alignments_by_doc=alignments_by_doc,
    )
    extracted_path.write_text(
        json.dumps(extracted, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    geo_mod = _import_geocode_places_module()
    geocoded = geo_mod.build_geocoded_from_extracted(
        extracted,
        use_nominatim=geocode_online,
        cache_path=geocoded_path if geocoded_path.exists() else None,
    )
    geocoded_path.write_text(
        json.dumps(geocoded, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {"extracted": extracted_path, "geocoded": geocoded_path}
