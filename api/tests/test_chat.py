"""POST /chat and GET /documents/{id}/file (spec 2.13, 2.14) with OpenAI stubbed (FakeLLM): hybrid retrieval,
the not-found rule, the citation check, degraded mode, parcel context, the 20/min rate limit."""

from __future__ import annotations

import re

import pytest

from landlens.rag.llm import fake_embedding

from .conftest import make_pdf

CORPUS = [  # (title, doc_type, file, [(page, content)])
    ("Test Development Act", "regulation", "docs/act.pdf", [
        (1, "13. The Government may declare any area as a development area by notification in the Gazette."),
        (2, "19. No person shall undertake development without permission of the Authority; fees are payable."),
    ]),
    ("LRS FAQ", "notification", "docs/lrs.pdf", [
        (1, "Q3. Layout regularization requires payment of regularization charges by all plot owners."),
    ]),
]


@pytest.fixture(scope="module")
def corpus(owner, seed_dir):
    make_pdf(seed_dir / "docs" / "act.pdf", ["Section 13 text", "Section 19 text"])
    ids = []
    for title, dt, path, chunks in CORPUS:
        doc = owner.execute(
            "INSERT INTO document (title, doc_type, issued_by, file_path, sha256, page_count)"
            " VALUES (%s, %s, 'test', %s, md5(%s) || md5(%s), 2) RETURNING document_id",
            (title, dt, path, title, title)).fetchone()[0]
        for n, (page, text) in enumerate(chunks, 1):
            emb = "[" + ",".join(map(str, fake_embedding(text))) + "]"
            owner.execute("INSERT INTO document_chunk VALUES (%s, %s, %s, %s, %s, DEFAULT, %s::vector)",
                          (doc, n, page, page, text, emb))
        ids.append(doc)
    yield ids
    owner.execute("DELETE FROM document WHERE document_id = ANY(%s)", (ids,))


def excerpt_with(messages, needle: str) -> int:
    user = messages[-1]["content"]
    for m in re.finditer(r"\[(\d+)\] ([^\n]+):\n([^\n]+)", user):
        if needle in m.group(3):
            return int(m.group(1))
    raise AssertionError(f"{needle!r} not in the excerpts")


def ask(client, h, q, **kw):
    return client.post("/api/chat", headers=h, json={"question": q, **kw})


def test_chat_requires_session_and_valid_body(client, make_user, corpus):
    assert client.post("/api/chat", json={"question": "permission needed?"}).status_code == 401
    h, _ = make_user()
    assert ask(client, h, "hi").status_code == 422
    assert client.post("/api/chat", headers=h, json={"question": "x" * 501}).status_code == 422
    assert client.post("/api/chat", headers=h, json={"question": "permission?", "extra": 1}).status_code == 422


def test_answer_with_checked_citations(client, make_user, corpus):
    h, _ = make_user()
    llm = client.app.state.llm
    llm.answer = lambda m: f"Development needs the Authority's permission [{excerpt_with(m, 'permission')}]. See also [9]."
    r = ask(client, h, "Development without permission of the Authority?")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["found"] is True and d["degraded"] is False
    assert "[9]" not in d["answer"] and d["answer"].endswith("See also.")            # unknown [9] dropped
    assert len(d["citations"]) == 1
    c = d["citations"][0]
    assert (c["title"], c["page_start"], c["page_end"]) == ("Test Development Act", 2, 2)
    assert f"[{c['n']}]" in d["answer"] and "permission" in c["snippet"]
    assert llm.calls == ["embed", "chat"]


def test_not_found_rule_skips_the_llm(client, make_user, corpus):
    h, _ = make_user()
    llm = client.app.state.llm
    d = ask(client, h, "What is the capital of France?").json()     # no keyword hit, distance ~1 > 0.6
    assert d == {"found": False, "degraded": False, "answer": "not found in the documents", "citations": [], "note": None}
    assert llm.calls == ["embed"]


def test_llm_says_not_found_and_uncited_answers(client, make_user, corpus):
    h, _ = make_user()
    llm = client.app.state.llm
    llm.answer = "Not found in the documents."
    d = ask(client, h, "Development without permission of the Authority?").json()
    assert d["found"] is False and d["answer"] == "not found in the documents" and d["citations"] == []
    llm.answer = "You need permission."                               # no [n] at all
    d = ask(client, h, "Development without permission of the Authority?").json()
    assert d["found"] is True and d["answer"] is None and len(d["citations"]) == 3 and "note" in d


def test_degraded_without_embeddings_is_keyword_only(client, make_user, corpus):
    h, _ = make_user()
    llm = client.app.state.llm
    llm.fail = "embed"
    d = ask(client, h, "What are regularization charges?").json()
    assert d["degraded"] is True and d["found"] is True and d["answer"] is None
    assert d["citations"][0]["title"] == "LRS FAQ" and "note" in d
    assert llm.calls == ["embed"]                                      # no chat call in degraded mode
    d = ask(client, h, "Zebra giraffe elephant?").json()
    assert d["degraded"] is True and d["found"] is False and d["citations"] == []


def test_llm_outage_returns_passages(client, make_user, corpus):
    h, _ = make_user()
    client.app.state.llm.fail = "chat"
    d = ask(client, h, "Development without permission of the Authority?").json()
    assert d["degraded"] is True and d["found"] is True and d["answer"] is None and d["citations"]


def test_parcel_context_and_unknown_parcel(client, make_user, corpus):
    h, _ = make_user()
    seen = {}

    def answer(m):
        seen["user"] = m[-1]["content"]
        return f"Permission is needed [{excerpt_with(m, 'permission')}]."
    client.app.state.llm.answer = answer
    assert ask(client, h, "Development without permission of the Authority?", parcel_id=3).json()["found"] is True
    assert "peri urban parcel in Commercial zone" in seen["user"].replace("[fallback] ", "")
    r = ask(client, h, "Do I need permission?", parcel_id=999)
    assert r.status_code == 404 and r.json()["error"]["code"] == "parcel_not_found"


def test_chat_rate_limit_20_per_minute(client, make_user, corpus):
    h, _ = make_user()
    client.app.state.llm.fail = "all"
    codes = [ask(client, h, "regularization charges?").status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_document_file(client, corpus):
    r = client.get(f"/api/documents/{corpus[0]}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and "inline" in r.headers["content-disposition"]
    assert client.get(f"/api/documents/{corpus[1]}/file").json()["error"]["code"] == "document_file_missing"
    assert client.get("/api/documents/999999/file").status_code == 404


def test_document_file_refuses_paths_outside_seed_inputs(client, owner):
    doc = owner.execute("INSERT INTO document (title, doc_type, issued_by, file_path, sha256, page_count)"
                        " VALUES ('evil', 'regulation', 'x', '../../../etc/passwd', repeat('e', 64), 1)"
                        " RETURNING document_id").fetchone()[0]
    try:
        r = client.get(f"/api/documents/{doc}/file")
        assert r.status_code == 404 and r.json()["error"]["code"] == "document_file_missing"
    finally:
        owner.execute("DELETE FROM document WHERE document_id = %s", (doc,))
