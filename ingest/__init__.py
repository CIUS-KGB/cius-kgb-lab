"""
Ingest module: discover/load documents.
Output: list of { document_id, display_name, path, raw_text?, raw_text_en? }.

When documents.document_map_path and documents.input_dir_ru are set, Russian is primary:
sync copies from dev/russian_originals into data/russian_originals, then documents
are loaded from that directory (raw_text = Russian). English full text is loaded from
``en_filename`` when set, otherwise ``input_dir`` (``<document_id>.txt``, spaced id, ``display_name``).
If those are missing (e.g. CI: ``data/input`` not in repo), derive English filenames from ``rus_filename``
and read from ``source_dir_en`` (``dev/english_translations``), which is committed.
"""
import json
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

# Short document_ids only use exact file/folder matches; longer substring keys avoid false positives.
_MIN_PDF_PATH_SUBSTRING = 6
_MIN_PDF_ALNUM_KEY = 8


def _sanitize_pdf_root_rel(pdf_root: Optional[str]) -> str:
    raw = (pdf_root or "original_pdfs").strip() or "original_pdfs"
    p = Path(raw)
    if p.is_absolute() or ".." in p.parts:
        return "original_pdfs"
    return raw.replace("\\", "/")


def _first_pdf_in_directory(d: Path) -> Optional[Path]:
    for p in sorted(d.glob("*.pdf")) + sorted(d.glob("*.PDF")):
        if p.is_file():
            return p
    return None


def _pdf_path_needles(doc_id: str) -> List[str]:
    d = (doc_id or "").strip()
    if not d:
        return []
    lowered = d.lower()
    candidates = [
        lowered,
        lowered.replace("_", "-"),
        lowered.replace("_", " "),
        lowered.replace("-", "_"),
        lowered.replace("-", " "),
    ]
    seen = set()
    out: List[str] = []
    for c in candidates:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _pdf_alnum_key(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum())


def _find_original_pdf(root: Path, doc_id: str, *, pdf_root: Optional[str] = None) -> Optional[str]:
    """
    Resolve a PDF under the project's originals folder for document_id.

    Tries in order:
    - <pdf_root>/<document_id>.pdf
    - First *.pdf in <pdf_root>/<document_id>/
    - First *.pdf in folders named with common underscore/space/hyphen variants of document_id
    - First *.pdf whose relative path contains a sufficiently long id substring (matches nested layouts)
    - First *.pdf whose relative path contains the alphanumeric key of document_id (matches archive-style folder names)

    pdf_root is relative to project root (config documents.original_pdfs_dir), default original_pdfs.
    Returns a path relative to root using forward slashes, or None.
    """
    root_res = root.resolve()
    rel_base = _sanitize_pdf_root_rel(pdf_root)
    base = (root_res / rel_base).resolve()
    if not base.is_dir():
        return None
    try:
        base.relative_to(root_res)
    except ValueError:
        return None

    def as_proj_rel(p: Path) -> str:
        return p.resolve().relative_to(root_res).as_posix()

    # 1. Flat file: original_pdfs/<doc_id>.pdf
    for ext in (".pdf", ".PDF"):
        p = base / f"{doc_id}{ext}"
        if p.is_file():
            return as_proj_rel(p)

    # 2. Strict child folder
    sub = base / doc_id
    if sub.is_dir():
        found = _first_pdf_in_directory(sub)
        if found:
            return as_proj_rel(found)

    # 3. Folder name variants (spaces vs underscores vs hyphens)
    variants = set()
    v = doc_id.strip()
    if v:
        variants.add(v)
        variants.add(v.replace("_", " "))
        variants.add(v.replace(" ", "_"))
        variants.add(v.replace("-", "_"))
        variants.add(v.replace("_", "-"))
    for folder_name in sorted(variants):
        if not folder_name:
            continue
        subv = base / folder_name
        if subv.is_dir():
            found = _first_pdf_in_directory(subv)
            if found:
                return as_proj_rel(found)

    needles = _pdf_path_needles(doc_id)
    long_needles = [n for n in needles if len(n) >= _MIN_PDF_PATH_SUBSTRING]
    hits: List[Path] = []

    # 4. Path substring (only for needles long enough to reduce false matches)
    if long_needles:
        for p in base.rglob("*"):
            if p.suffix.lower() != ".pdf" or not p.is_file():
                continue
            try:
                rel = p.relative_to(base).as_posix().lower().replace("\\", "/")
            except ValueError:
                continue
            if any(n in rel for n in long_needles):
                hits.append(p)

    # 5. Alphanumeric containment (e.g. FineReader-...-1249-0046-0047.../)
    doc_key = _pdf_alnum_key(doc_id)
    if not hits and len(doc_key) >= _MIN_PDF_ALNUM_KEY:
        for p in base.rglob("*"):
            if p.suffix.lower() != ".pdf" or not p.is_file():
                continue
            try:
                rel_key = _pdf_alnum_key(p.relative_to(base).as_posix())
            except ValueError:
                continue
            if doc_key in rel_key:
                hits.append(p)

    if hits:
        hits.sort(key=lambda x: (len(x.relative_to(base).parts), len(str(x)), x.as_posix().lower()))
        return as_proj_rel(hits[0])

    return None


def sync_russian_originals(config: Dict[str, Any], root: Path) -> None:
    """
    Copy Russian originals from dev folder into data/russian_originals using document map.
    Creates target dir and copies each mapped file as <document_id>.txt.
    """
    doc_config = config.get("documents", {})
    map_path = doc_config.get("document_map_path")
    if not map_path:
        return
    path = root / map_path
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    source_dir = root / data.get("source_dir_ru", "dev/russian_originals")
    target_dir = root / data.get("target_dir_ru", "data/russian_originals")
    if not source_dir.exists():
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in data.get("documents", []):
        doc_id = item.get("document_id", "")
        rus_fn = item.get("rus_filename", "")
        if not doc_id or not rus_fn:
            continue
        src = source_dir / rus_fn
        if not src.exists():
            continue
        dst = target_dir / f"{doc_id}.txt"
        shutil.copy2(src, dst)


def _english_fulltext_candidates(en_dir: Path, doc_id: str, display_name: str) -> List[Path]:
    """Ordered paths to try for English full text under ``input_dir``.

    Russian originals use ``<document_id>.txt`` in ``data/russian_originals``; English files in
    ``data/input`` follow the same ids (e.g. ``1127.txt``) or spaced variants (e.g. ``1262 28-32.txt``
    for ``document_id`` ``1262_28-32``). Legacy code only checked ``display_name``, which does not
    match those filenames, leaving ``raw_text_en`` empty and breaking bilingual view / EN word clouds.
    """
    ordered: List[Path] = []
    seen: Set[str] = set()

    def add(p: Path) -> None:
        key = str(p)
        if key not in seen:
            seen.add(key)
            ordered.append(p)

    add(en_dir / f"{doc_id}.txt")
    spaced = doc_id.replace("_", " ")
    if spaced != doc_id:
        add(en_dir / f"{spaced}.txt")
    dn = (display_name or "").strip()
    if dn:
        add(en_dir / dn)
        if not dn.lower().endswith(".txt"):
            add(en_dir / f"{dn}.txt")
    return ordered


def _read_first_existing_text(paths: List[Path], encoding: str) -> str:
    for p in paths:
        if not p.is_file():
            continue
        try:
            return p.read_text(encoding=encoding)
        except Exception:
            continue
    return ""


def _english_filenames_derived_from_rus(rus_filename: str) -> List[str]:
    """Guess English translation filenames from Russian basename (matches ``dev/english_translations`` layout)."""
    if not rus_filename or not isinstance(rus_filename, str):
        return []
    r = rus_filename.strip()
    out: List[str] = []
    taken: Set[str] = set()

    def add(name: str) -> None:
        if name and name not in taken:
            taken.add(name)
            out.append(name)

    if r.endswith(" RUS.txt"):
        stem = r[: -len(" RUS.txt")]
        add(stem + " ENG.txt")
        collapsed = re.sub(r"-0+(\d)", lambda m: "-" + m.group(1), stem)
        if collapsed != stem:
            add(collapsed + " ENG.txt")
    if r.endswith(" RUS chunk-aligned.txt"):
        stem = r[: -len(" RUS chunk-aligned.txt")]
        add(stem + " ENG.txt")

    if r.endswith("-Original_Rus.docx.txt"):
        add(r[: -len("-Original_Rus.docx.txt")] + "-ENG.txt")
    if r.endswith("-Original-Rus.docx.txt"):
        add(r[: -len("-Original-Rus.docx.txt")] + "-ENG.txt")
    if r.endswith("-Original_Rus.txt"):
        add(r[: -len("-Original_Rus.txt")] + "-Eng.txt")
    if r.endswith("-Rus.txt"):
        add(r[: -len("-Rus.txt")] + "-ENG.txt")

    if r.startswith("RUS - ") and r.endswith("_Rus.txt"):
        middle = r[len("RUS - ") : -len("_Rus.txt")]
        add(f"ENG - {middle}_ENG.txt")

    if r.endswith("-Original-Verified.txt"):
        add(r[: -len("-Original-Verified.txt")] + "-Eng.txt")

    return out


def run(config: Dict[str, Any], root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Discover and load documents. If document_map_path and input_dir_ru are set,
    sync Russian originals from dev into data/russian_originals, then load from there
    (raw_text = Russian). Optionally load raw_text_en from ``input_dir``:
    ``en_filename`` + ``source_dir_en``, else ``input_dir`` candidates, then ``source_dir_en`` paths
    derived from ``rus_filename`` when ``input_dir`` has no file (fresh clone / GitHub Actions).
    Otherwise discover from input_dir (legacy: raw_text = English).
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent
    doc_config = config.get("documents", {})
    encoding = doc_config.get("encoding", "utf-8")
    map_path = doc_config.get("document_map_path")
    input_dir_ru = doc_config.get("input_dir_ru", "data/russian_originals")
    input_dir_en = doc_config.get("input_dir", "data/input")

    if map_path:
        sync_russian_originals(config, root)
        target_ru = root / input_dir_ru
        if target_ru.exists():
            path = root / map_path
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                result = []
                en_dir = root / input_dir_en
                pdf_base = _sanitize_pdf_root_rel(doc_config.get("original_pdfs_dir"))
                for item in data.get("documents", []):
                    doc_id = item.get("document_id", "")
                    display_name = item.get("display_name", f"{doc_id}.txt")
                    if not doc_id:
                        continue
                    ru_path = target_ru / f"{doc_id}.txt"
                    raw_text = ""
                    if ru_path.exists():
                        try:
                            raw_text = ru_path.read_text(encoding=encoding)
                        except Exception:
                            pass
                    entry = {
                        "document_id": doc_id,
                        "display_name": display_name,
                        "path": str(ru_path),
                        "raw_text": raw_text,
                    }
                    stitle = item.get("short_title")
                    if isinstance(stitle, str) and stitle.strip():
                        entry["short_title"] = stitle.strip()
                    bib_title = item.get("bibliographic_title")
                    if isinstance(bib_title, str) and bib_title.strip():
                        entry["bibliographic_title"] = bib_title.strip()
                    en_filename = item.get("en_filename")
                    if en_filename is None and "en_filename" in item:
                        entry["raw_text_en"] = ""
                    elif en_filename and isinstance(en_filename, str):
                        source_en = data.get("source_dir_en", "dev/english_translations")
                        src_en = root / source_en / en_filename
                        if src_en.exists():
                            try:
                                entry["raw_text_en"] = src_en.read_text(encoding=encoding)
                            except Exception:
                                entry["raw_text_en"] = ""
                        else:
                            entry["raw_text_en"] = ""
                    else:
                        entry["raw_text_en"] = _read_first_existing_text(
                            _english_fulltext_candidates(en_dir, doc_id, display_name),
                            encoding,
                        )
                        if not (entry["raw_text_en"] or "").strip():
                            source_en_root = root / data.get(
                                "source_dir_en", "dev/english_translations"
                            )
                            derived_paths = [
                                source_en_root / fn
                                for fn in _english_filenames_derived_from_rus(
                                    item.get("rus_filename") or ""
                                )
                            ]
                            entry["raw_text_en"] = _read_first_existing_text(
                                derived_paths, encoding
                            )
                    prp = item.get("pdf_relative_path")
                    if isinstance(prp, str) and prp.strip():
                        entry["pdf_relative_path"] = prp.strip()
                    else:
                        auto_pdf = _find_original_pdf(root, doc_id, pdf_root=pdf_base)
                        if auto_pdf:
                            entry["pdf_relative_path"] = auto_pdf
                    simgs = item.get("scan_images")
                    if isinstance(simgs, list) and simgs:
                        entry["scan_images"] = [str(x).strip() for x in simgs if str(x).strip()]
                    result.append(entry)
                if result:
                    return result

    # Legacy: discover from input_dir (English as raw_text)
    input_dir = root / input_dir_en
    extensions = tuple(doc_config.get("extensions", [".txt"]))
    if not input_dir.exists():
        return _fixture_documents()
    result = []
    for path in sorted(input_dir.iterdir()):
        if path.suffix.lower() in extensions and path.is_file():
            doc_id = path.stem.replace(" ", "_")[:50]
            display_name = path.name
            entry = {"document_id": doc_id, "display_name": display_name, "path": str(path)}
            try:
                entry["raw_text"] = path.read_text(encoding=encoding)
            except Exception:
                entry["raw_text"] = ""
            result.append(entry)
    return result if result else _fixture_documents()


def _fixture_documents() -> List[Dict[str, Any]]:
    """Minimal fixture so pipeline runs without input dir."""
    return [
        {"document_id": "doc1", "display_name": "doc1.txt", "path": "", "raw_text": "Sample phrase one. Sample phrase two."},
        {"document_id": "doc2", "display_name": "doc2.txt", "path": "", "raw_text": "Another document. Two phrases."},
    ]
