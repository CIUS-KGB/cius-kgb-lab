"""
Test ingest module: fixture when no input dir, and document shape.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import _english_filenames_derived_from_rus
from ingest import run as ingest_run


def test_ingest_returns_fixture_when_no_dir():
    config = {"documents": {"input_dir": "data/input", "extensions": [".txt"], "encoding": "utf-8"}}
    # data/input may not exist from repo root
    result = ingest_run(config)
    assert isinstance(result, list)
    assert len(result) >= 1
    for doc in result:
        assert "document_id" in doc
        assert "display_name" in doc
        assert "raw_text" in doc
        assert isinstance(doc["raw_text"], str)


def test_ingest_fixture_has_usable_text():
    config = {}
    result = ingest_run(config)
    texts = [d.get("raw_text", "") for d in result]
    assert any(len(t.strip()) > 0 for t in texts)


@pytest.mark.skipif(
    not (Path(__file__).resolve().parent.parent / "data" / "input" / "1127.txt").is_file(),
    reason="repo sample data/input/1127.txt not present",
)
def test_document_map_loads_english_from_doc_id_txt():
    """Russian-first map mode must find data/input/<document_id>.txt, not display_name-only paths."""
    root = Path(__file__).resolve().parent.parent
    cfg_path = root / "config" / "pipeline_config.example.json"
    if not cfg_path.is_file():
        pytest.skip("pipeline_config.example.json missing")
    config = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not config.get("documents", {}).get("document_map_path"):
        pytest.skip("document_map_path not configured")
    docs = ingest_run(config, root)
    by_id = {d["document_id"]: d for d in docs}
    assert "1127" in by_id
    assert len((by_id["1127"].get("raw_text_en") or "").strip()) > 100
    assert len((by_id["1127"].get("raw_text") or "").strip()) > 100
    # Underscore doc id maps to spaced filename on disk
    if "1262_28-32" in by_id and (root / "data" / "input" / "1262 28-32.txt").is_file():
        assert len((by_id["1262_28-32"].get("raw_text_en") or "").strip()) > 100


def test_english_filenames_derived_from_rus_covers_map_patterns():
    assert "F.16-Op.01-Spr.1127-59-64 ENG.txt" in _english_filenames_derived_from_rus(
        "F.16-Op.01-Spr.1127-59-64 RUS.txt"
    )
    assert "F.16-Op.01-Spr.1249-0046-0047 ENG.txt" in _english_filenames_derived_from_rus(
        "F.16-Op.01-Spr.1249-0046-0047 RUS chunk-aligned.txt"
    )
    assert "FineReader-016-0001-1230-ENG.txt" in _english_filenames_derived_from_rus(
        "FineReader-016-0001-1230-Original_Rus.docx.txt"
    )
    names_1213 = _english_filenames_derived_from_rus(
        "F.16-Op.01-Spr.1213-0154-56 RUS.txt"
    )
    assert "F.16-Op.01-Spr.1213-154-56 ENG.txt" in names_1213
    assert "ENG - 016-0001-1262-0028-32_ENG.txt" in _english_filenames_derived_from_rus(
        "RUS - 016-0001-1262-0028-32_Rus.txt"
    )


def test_map_mode_loads_english_from_dev_when_input_dir_empty(tmp_path):
    """Mirrors CI: ``data/input`` absent — fall back to committed ``dev/english_translations``."""
    dev_ru = tmp_path / "dev" / "russian_originals"
    dev_en = tmp_path / "dev" / "english_translations"
    dev_ru.mkdir(parents=True)
    dev_en.mkdir(parents=True)
    rus_fn = "F.16-Op.01-Spr.1127-59-64 RUS.txt"
    dev_ru.joinpath(rus_fn).write_text("Russian body", encoding="utf-8")
    dev_en.joinpath("F.16-Op.01-Spr.1127-59-64 ENG.txt").write_text(
        "Full English translation body for CI.", encoding="utf-8"
    )
    empty_input = tmp_path / "empty_input"
    empty_input.mkdir()
    map_path = tmp_path / "document_map.json"
    map_path.write_text(
        json.dumps(
            {
                "source_dir_ru": "dev/russian_originals",
                "target_dir_ru": "data/russian_originals",
                "source_dir_en": "dev/english_translations",
                "documents": [
                    {
                        "document_id": "1127",
                        "rus_filename": rus_fn,
                        "display_name": "Test bulletin",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    config = {
        "documents": {
            "document_map_path": "document_map.json",
            "input_dir": "empty_input",
            "input_dir_ru": "data/russian_originals",
            "encoding": "utf-8",
        }
    }
    docs = ingest_run(config, tmp_path)
    assert len(docs) == 1
    assert docs[0].get("raw_text_en") == "Full English translation body for CI."
