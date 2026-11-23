"""OpenAI behind one small interface (ADR-011): embeddings and chat completions over the REST API with httpx.

- EMBEDDING_MODEL = text-embedding-3-small (1536 dims, spec 2.13); the generation model comes from LLM_MODEL.
- 10 s timeout per call (spec 2.14); any failure raises LLMUnavailable so callers degrade instead of erroring.
- No key -> LLMUnavailable("no_key") before any network call. Tests and `--fake-embeddings` use FakeLLM, which
  never touches the network (DEC-003 OQ-31: agents stub the client; the owner runs paid steps).
"""

from __future__ import annotations

import hashlib
import math
import os
import re

import httpx

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
DEFAULT_LLM_MODEL = "gpt-4o-mini"
API = "https://api.openai.com/v1"
TIMEOUT_S = 10.0
BATCH = 100                          # spec 2.13: embeddings in batches of 100
EMBED_USD_PER_MTOK = 0.02            # text-embedding-3-small list price per 1M tokens (owner to confirm)


class LLMUnavailable(Exception):
    """No key, timeout, HTTP error or malformed answer: the caller falls back (degraded mode)."""


def est_tokens(text: str) -> int:
    """~4 characters per token for English (OpenAI rule of thumb); used for chunk sizes and cost estimates."""
    return max(1, math.ceil(len(text) / 4))


def llm_model() -> str:
    return os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL


def _key() -> str:
    k = os.environ.get("OPENAI_API_KEY", "").strip()
    if not k:
        raise LLMUnavailable("no_key")
    return k


def _check_vectors(data: dict, n: int) -> list[list[float]]:
    try:
        vecs = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    except (KeyError, TypeError) as e:
        raise LLMUnavailable(f"bad_response: {e}") from None
    if len(vecs) != n or any(len(v) != EMBEDDING_DIMS for v in vecs):
        raise LLMUnavailable("bad_response: wrong count or dimension")
    return vecs


def _chat_body(messages: list[dict]) -> dict:
    return {"model": llm_model(), "messages": messages, "temperature": 0, "max_tokens": 600}


def _chat_text(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise LLMUnavailable(f"bad_response: {e}") from None


class OpenAISync:
    """For the CLI (ingest-pdf, eval)."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        key = _key()
        out: list[list[float]] = []
        with httpx.Client(timeout=60.0) as c:
            for i in range(0, len(texts), BATCH):
                batch = texts[i:i + BATCH]
                try:
                    r = c.post(f"{API}/embeddings", headers={"Authorization": f"Bearer {key}"},
                               json={"model": EMBEDDING_MODEL, "input": batch})
                    r.raise_for_status()
                except httpx.HTTPError as e:
                    raise LLMUnavailable(f"embeddings: {e}") from None
                out += _check_vectors(r.json(), len(batch))
        return out

    def chat(self, messages: list[dict]) -> str:
        key = _key()
        try:
            r = httpx.post(f"{API}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                           json=_chat_body(messages), timeout=60.0)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMUnavailable(f"chat: {e}") from None
        return _chat_text(r.json())


class OpenAIAsync:
    """For the API (/chat): one shared AsyncClient, 10 s timeout (spec 2.14)."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=TIMEOUT_S)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        key = _key()
        try:
            r = await self._client.post(f"{API}/embeddings", headers={"Authorization": f"Bearer {key}"},
                                        json={"model": EMBEDDING_MODEL, "input": texts})
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMUnavailable(f"embeddings: {e}") from None
        return _check_vectors(r.json(), len(texts))

    async def chat(self, messages: list[dict]) -> str:
        key = _key()
        try:
            r = await self._client.post(f"{API}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                                        json=_chat_body(messages))
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMUnavailable(f"chat: {e}") from None
        return _chat_text(r.json())


_WORD = re.compile(r"[a-z0-9]+")


def fake_embedding(text: str) -> list[float]:
    """Deterministic bag-of-words hashing vector (unit length): texts sharing words get a small cosine distance,
    so retrieval behaves plausibly in tests. Never used for real data except by an explicit --fake-embeddings."""
    v = [0.0] * EMBEDDING_DIMS
    for w in _WORD.findall(text.lower()):
        h = int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "little")
        v[h % EMBEDDING_DIMS] += 1.0 if (h >> 32) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class FakeLLM:
    """Test double for both interfaces. `answer` builds the chat reply from the prompt; `fail` simulates outages."""

    def __init__(self, answer=None, fail: str | None = None) -> None:
        self.answer = answer
        self.fail = fail                 # None | "embed" | "chat" | "all"
        self.calls: list[str] = []

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        return [fake_embedding(t) for t in texts]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append("embed")
        if self.fail in ("embed", "all"):
            raise LLMUnavailable("fake outage")
        return [fake_embedding(t) for t in texts]

    async def chat(self, messages: list[dict]) -> str:
        self.calls.append("chat")
        if self.fail in ("chat", "all"):
            raise LLMUnavailable("fake outage")
        return self.answer(messages) if callable(self.answer) else (self.answer or "")

    async def aclose(self) -> None:
        return None
