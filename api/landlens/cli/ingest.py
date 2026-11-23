"""`landlens ingest-pdf`: parse, chunk, embed, insert (spec 2.13, FR-13). Idempotent by sha256.

    landlens ingest-pdf --dry-run          # free: parse + chunk, flag pages without text, print tokens and cost
    landlens ingest-pdf                    # embeds with OPENAI_API_KEY (paid), writes the embeddings dump, inserts
    landlens ingest-pdf --offline          # only documents that have a dump (no OpenAI call); used by `seed`

- Input: every *.pdf under seed_inputs/docs/ (or the paths given). Metadata (title, doc_type, issued_by,
  issued_on, source_url) from seed_inputs/docs/manifest.json; without an entry, the PDF title or file name.
- A document whose sha256 is already in `document` is skipped, so re-running is a no-op.
- Pages with under 50 characters of text are flagged and skipped (no OCR; OQ-36).
- Embeddings dump (DEC-006): seed_inputs/docs/embeddings/<sha256>.json holds the chunks and their vectors.
  When it exists it is used instead of calling OpenAI, so a re-seed (which truncates the document tables)
  never pays twice. Re-embedding after a chunker change: delete the dump.
- --fake-embeddings: deterministic local vectors for testing the pipeline without a key. Loud warning, no dump.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from landlens.db import connect
from landlens.rag import chunking
from landlens.rag.llm import EMBED_USD_PER_MTOK, EMBEDDING_MODEL, LLMUnavailable, OpenAISync, fake_embedding

DOC_TYPES = ("master_plan", "government_order", "notification", "regulation")


def seed_root() -> Path:
    return Path(os.environ.get("LANDLENS_SEED_INPUTS", "/app/seed_inputs"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def discover(paths: list[str]) -> list[Path]:
    if paths:
        out: list[Path] = []
        for p in map(Path, paths):
            out += sorted(x for x in p.iterdir() if x.suffix.lower() == ".pdf") if p.is_dir() else [p]
        return out
    d = seed_root() / "docs"
    return sorted(x for x in d.iterdir() if x.suffix.lower() == ".pdf") if d.is_dir() else []


def manifest_for(path: Path) -> dict:
    m = path.parent / "manifest.json"
    if m.exists():
        entry = json.loads(m.read_text()).get(path.name)
        if entry:
            return entry
    return {}


def rel_path(path: Path) -> str:
    """Stored file_path: relative to seed_inputs when inside it, so the API can serve it from its own mount."""
    try:
        return str(path.resolve().relative_to(seed_root().resolve()))
    except ValueError:
        return str(path.resolve())


def _load_dump(dump: Path) -> list[dict] | None:
    if not dump.exists():
        return None
    data = json.loads(dump.read_text())
    if data.get("model") != EMBEDDING_MODEL:
        print(f"    dump {dump.name} was made with {data.get('model')}, not {EMBEDDING_MODEL}: ignored")
        return None
    return data["chunks"]


def run(paths: list[str], dry_run: bool = False, offline: bool = False, fake: bool = False,
        dump_dir: str | None = None, embedder=None) -> int:
    files = discover(paths)
    if not files:
        print("ingest-pdf: no PDFs found (put them in seed_inputs/docs/)", file=sys.stderr)
        return 1
    dumps = Path(dump_dir) if dump_dir else seed_root() / "docs" / "embeddings"
    if fake:
        print("WARNING: --fake-embeddings: vectors are local word hashes, not OpenAI embeddings. "
              "For pipeline tests only; delete these documents before real use.")
    total_tok, todo_tok, rc = 0, 0, 0
    with connect() as conn:
        for f in files:
            sha = sha256(f)
            meta = manifest_for(f)
            row = conn.execute("SELECT document_id FROM document WHERE sha256 = %s", (sha,)).fetchone()
            print(f"- {f.name}  sha256 {sha[:12]}")
            if row:
                print(f"    already ingested as document {row[0]}: skipped")
                continue
            dump = dumps / f"{sha}.json"
            stored = None if fake else _load_dump(dump)
            if stored is None:
                parsed = chunking.parse(f)
                chunks = [{"chunk_no": c.chunk_no, "page_start": c.page_start, "page_end": c.page_end,
                           "content": c.content} for c in chunking.chunk(parsed)]
                page_count = parsed.page_count
                flagged = parsed.flagged
                title = meta.get("title") or parsed.title or f.stem
            else:
                chunks = stored
                d = json.loads(dump.read_text())
                page_count, flagged, title = d["page_count"], d.get("flagged_pages", []), meta.get("title") or d["title"]
            tok = sum(chunking.est_tokens(c["content"]) for c in chunks)
            total_tok += tok
            print(f"    {title}")
            print(f"    {page_count} pages, {len(chunks)} chunks, ~{tok:,} tokens"
                  + (f"; NO TEXT LAYER on pages {flagged} (skipped, not OCR'd)" if flagged else ""))
            if stored is not None:
                print(f"    embeddings from dump {dump.name} (no OpenAI call)")
            elif not fake:
                todo_tok += tok
            if dry_run:
                continue
            if stored is None and offline:
                print("    no embeddings dump: skipped (run `make ingest` to embed)")
                continue
            if stored is None:
                texts = [c["content"] for c in chunks]
                try:
                    vecs = [fake_embedding(t) for t in texts] if fake else (embedder or OpenAISync()).embed(texts)
                except LLMUnavailable as e:
                    print(f"    embedding failed ({e}): document not inserted", file=sys.stderr)
                    rc = 1
                    continue
                for c, v in zip(chunks, vecs, strict=True):
                    c["embedding"] = [round(x, 7) for x in v]
                if not fake:
                    dumps.mkdir(parents=True, exist_ok=True)
                    tmp = dump.with_suffix(".tmp")
                    tmp.write_text(json.dumps({"sha256": sha, "file": f.name, "title": title, "model": EMBEDDING_MODEL,
                                               "page_count": page_count, "flagged_pages": flagged, "chunks": chunks}))
                    tmp.replace(dump)
                    print(f"    wrote embeddings dump {dump}")
            doc_type = meta.get("doc_type", "regulation")
            if doc_type not in DOC_TYPES:
                print(f"    manifest doc_type {doc_type!r} is not one of {DOC_TYPES}", file=sys.stderr)
                return 1
            with conn.transaction():
                doc_id = conn.execute(
                    "INSERT INTO document (title, doc_type, issued_by, issued_on, source_url, file_path, sha256, page_count)"
                    " VALUES (%s, %s::doc_type, %s, %s, %s, %s, %s, %s) RETURNING document_id",
                    (title, doc_type, meta.get("issued_by", "unknown"), meta.get("issued_on"), meta.get("source_url"),
                     rel_path(f), sha, page_count)).fetchone()[0]
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO document_chunk (document_id, chunk_no, page_start, page_end, content, embedding)"
                        " VALUES (%s, %s, %s, %s, %s, %s::vector)",
                        [(doc_id, c["chunk_no"], c["page_start"], c["page_end"], c["content"],
                          "[" + ",".join(map(str, c["embedding"])) + "]") for c in chunks])
            print(f"    inserted as document {doc_id} ({len(chunks)} chunks)")
    usd = todo_tok / 1e6 * EMBED_USD_PER_MTOK
    print(f"corpus ~{total_tok:,} tokens; to embed now ~{todo_tok:,} tokens with {EMBEDDING_MODEL} "
          f"= about ${usd:.4f} at ${EMBED_USD_PER_MTOK}/1M tokens (estimate: ~4 characters per token)")
    return rc
