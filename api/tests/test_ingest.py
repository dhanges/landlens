"""landlens ingest-pdf (spec 2.13): parse, chunk, embed (stubbed), insert; flagged pages; idempotent by sha256;
the embeddings dump is reused without any embedding call (DEC-006)."""

from __future__ import annotations

import json

from landlens.cli import ingest
from landlens.rag import chunking
from landlens.rag.llm import EMBEDDING_DIMS, fake_embedding

from .conftest import make_pdf

SECTION = ("{n}. Permission for development. (1) No person shall undertake development in a development area "
           "without the written permission of the Authority. (2) The Authority may grant or refuse permission "
           "after considering the master plan and the zoning regulations in force. ") * 3


class StubEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [fake_embedding(t) for t in texts]


class NoEmbedder:
    def embed(self, texts):
        raise AssertionError("must not embed when a dump exists")


def test_parse_flags_pages_without_text(tmp_path):
    pdf = tmp_path / "t.pdf"
    make_pdf(pdf, [SECTION.format(n=1), "", SECTION.format(n=2) + SECTION.format(n=3)])
    parsed = chunking.parse(pdf)
    assert parsed.page_count == 3 and parsed.flagged == [2] and parsed.title == "Generated test document"
    chunks = chunking.chunk(parsed)
    assert chunks and all(c.tokens <= chunking.TARGET_TOKENS + 20 for c in chunks)
    assert {(c.page_start, c.page_end) for c in chunks} <= {(1, 1), (1, 3), (3, 3)}
    assert all(c.page_start != 2 and c.page_end >= c.page_start for c in chunks)
    assert any(c.content.startswith("2. Permission") or "\n\n2. Permission" in c.content for c in chunks)


def test_ingest_dump_and_idempotency(owner, seed_dir, capsys):
    docs = seed_dir / "docs"
    pdf = docs / "act_test.pdf"
    make_pdf(pdf, [SECTION.format(n=1), "", SECTION.format(n=2)])
    (docs / "manifest.json").write_text(json.dumps({"act_test.pdf": {
        "title": "Ingest Test Act", "doc_type": "regulation", "issued_by": "Test", "issued_on": "2025-01-04"}}))
    dumps = seed_dir / "dumps"
    try:
        assert ingest.run([str(pdf)], dry_run=True, dump_dir=str(dumps)) == 0
        assert "NO TEXT LAYER on pages [2]" in capsys.readouterr().out
        assert owner.execute("SELECT count(*) FROM document WHERE title = 'Ingest Test Act'").fetchone()[0] == 0

        emb = StubEmbedder()
        assert ingest.run([str(pdf)], dump_dir=str(dumps), embedder=emb) == 0
        assert emb.calls == 1
        doc_id, fp, pages, issued = owner.execute(
            "SELECT document_id, file_path, page_count, issued_on::text FROM document WHERE title = 'Ingest Test Act'").fetchone()
        assert (fp, pages, issued) == ("docs/act_test.pdf", 3, "2025-01-04")
        n, dims = owner.execute("SELECT count(*), max(vector_dims(embedding)) FROM document_chunk WHERE document_id = %s",
                                (doc_id,)).fetchone()
        assert n >= 1 and dims == EMBEDDING_DIMS
        dump = next(dumps.glob("*.json"))
        assert json.loads(dump.read_text())["flagged_pages"] == [2]

        capsys.readouterr()
        assert ingest.run([str(pdf)], dump_dir=str(dumps), embedder=NoEmbedder()) == 0     # same sha256: no-op
        assert "already ingested" in capsys.readouterr().out

        owner.execute("DELETE FROM document WHERE document_id = %s", (doc_id,))         # e.g. after a re-seed
        assert ingest.run([str(pdf)], offline=True, dump_dir=str(dumps), embedder=NoEmbedder()) == 0
        assert owner.execute("SELECT count(*) FROM document_chunk c JOIN document d USING (document_id)"
                             " WHERE d.title = 'Ingest Test Act'").fetchone()[0] == n
    finally:
        owner.execute("DELETE FROM document WHERE title = 'Ingest Test Act'")
        (docs / "manifest.json").unlink(missing_ok=True)


def test_offline_without_dump_skips(owner, seed_dir, capsys, tmp_path):
    pdf = tmp_path / "nodump.pdf"
    make_pdf(pdf, [SECTION.format(n=4)])
    assert ingest.run([str(pdf)], offline=True, dump_dir=str(tmp_path / "none"), embedder=NoEmbedder()) == 0
    assert "no embeddings dump: skipped" in capsys.readouterr().out
