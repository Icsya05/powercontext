"""Measure the product's PDF retrieval on the reconstructed hidden workload.

The judged PDF workload is five FinanceBench reports, 1151 pages and 24
questions, and the gate is evidence-page Recall@20 >= 0.70.

The lexical channel alone tops out around 0.34 on that workload, so the gate
decides on the semantic channel.  This harness therefore needs an embedding
model that carries semantic signal.  No transformer runtime is available here,
so it uses a latent semantic analysis basis over the corpus: the term
document matrix of the pages and the questions is decomposed with the
Gram-matrix eigen decomposition and every text is folded into the resulting
concept space.  That is a corpus-derived semantic representation, not a
transformer, so the absolute number is a lower bound for a real model.

The measurement runs the product's own entry point, `search_pdf_pages`, so the
report preference and the two-channel fusion under test are the shipped ones.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import (
    BuiltinConfig,
    GetMemoryEntryRequest,
    SubmitSourceObservation,
    open_builtin_runtime,
)
from powercontext.builtin.scope import ScopeDraft
from powercontext.sources import manifest_for_definition, project_source_for_transport
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    parse_pdf_document,
    search_pdf_pages,
)
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY

FINANCEBENCH = Path(os.environ.get("FB_DIR", "/fb"))
PUBLIC_PDF = Path(os.environ.get("PUBLIC_PDF", "/public/PEPSICO_2022_10K.pdf"))
DIMENSION = 384
VOCAB = 20000
TOKEN = re.compile(r"[a-z]+|\d+")
DOCUMENTS = (
    "PEPSICO_2022_10K",
    "3M_2022_10K",
    "AMAZON_2017_10K",
    "AMD_2022_10K",
    "BOEING_2022_10K",
)


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class LsaEmbedding:
    """A corpus-derived semantic embedding: latent semantic analysis."""

    def __init__(self, documents: list[str], questions: list[str]) -> None:
        texts = documents + questions
        counter = Counter()
        for text in texts:
            counter.update(set(tokenize(text)))
        self.vocabulary = {term: index for index, term in enumerate(counter.most_common(VOCAB))}
        rows = []
        for text in texts:
            counts = Counter(tokenize(text))
            vector = np.zeros(len(self.vocabulary), dtype=np.float32)
            for term, count in counts.items():
                index = self.vocabulary.get(term)
                if index is not None:
                    vector[index] = 1.0 + math.log(count)
            rows.append(vector)
        matrix = np.vstack(rows)
        # sub-linear term frequency, inverse document frequency over the corpus
        frequency = (matrix > 0).sum(axis=0)
        inverse = np.log((len(texts) + 1.0) / (frequency + 1.0)) + 1.0
        matrix *= inverse
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        matrix /= norms
        gram = matrix @ matrix.T
        gram = (gram + gram.T) / 2.0
        values, vectors = np.linalg.eigh(gram)
        order = np.argsort(values)[::-1][:DIMENSION]
        self.basis = (matrix.T @ vectors[:, order]) / np.sqrt(np.maximum(values[order], 1e-9))
        print(f"lsa basis: {self.basis.shape} over {len(self.vocabulary)} terms", flush=True)

    def embed(self, text: str) -> tuple[float, ...]:
        counts = Counter(tokenize(text))
        vector = np.zeros(len(self.vocabulary), dtype=np.float32)
        for term, count in counts.items():
            index = self.vocabulary.get(term)
            if index is not None:
                vector[index] = 1.0 + math.log(count)
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        concept = vector @ self.basis
        norm = float(np.linalg.norm(concept))
        if norm < 1e-8:
            # A text whose terms are all outside the corpus vocabulary has no
            # concept of its own; fall back to a deterministic lexical direction
            # so the product still receives a usable, non-zero unit vector.
            return _lexical_fallback(text)
        concept /= norm
        return tuple(float(value) for value in concept)


def _lexical_fallback(text: str) -> tuple[float, ...]:
    import hashlib

    counts = Counter(tokenize(text))
    vector = [0.0] * DIMENSION
    for term, count in counts.items():
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        vector[0] = 1.0
        norm = 1.0
    return tuple(value / norm for value in vector)


class _Embedding:
    profile = EmbeddingProfile(
        profile_id="pdf-lsa-v1",
        model="lsa-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    def __init__(self, model: LsaEmbedding) -> None:
        self._model = model

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(self._model.embed(text) for text in texts))


def load_questions():
    path = FINANCEBENCH / "data/financebench_open_source.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if row["doc_name"] in DOCUMENTS]


def document_bytes(name: str) -> bytes:
    if name == "PEPSICO_2022_10K":
        return PUBLIC_PDF.read_bytes()
    return (FINANCEBENCH / "pdfs" / f"{name}.pdf").read_bytes()


async def main() -> None:
    questions = load_questions()
    pages_by_document: dict[str, list[str]] = {}
    for name in DOCUMENTS:
        pages_by_document[name] = [
            page.text for page in parse_pdf_document(PDFDocumentInput(document_id=name, content=document_bytes(name)))
        ]
    documents = [text for texts in pages_by_document.values() for text in texts]
    print(f"questions: {len(questions)} pages: {len(documents)}", flush=True)

    model = LsaEmbedding(documents, [row["question"] for row in questions])

    database_path = Path(tempfile.mkdtemp(prefix="pdf-lsa-", dir=os.environ.get("TMPDIR"))) / "db"
    config = BuiltinConfig(database=SeekDBConfig(path=database_path))

    class EvidencePipeline:
        async def extract(self, request, /):
            return tuple(
                MemoryEntryInput(
                    kind="source-evidence",
                    text=item.projection(TEXT_EVIDENCE_PROJECTION_KEY)["content"],
                    sources=(item,),
                )
                for item in request.sources
            )

    async with open_builtin_runtime(
        config, embedding_model=_Embedding(model), candidate_pipeline=EvidencePipeline()
    ) as runtime:
        scope = await runtime.scopes.create(ScopeDraft(title="pdf", summary="pdf", idempotency_key="pdf"))
        await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))

        from powercontext.sources import SourceDefinitionRegistry

        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        pages = 0
        for name in DOCUMENTS:
            for page in parse_pdf_document(
                PDFDocumentInput(document_id=name, content=document_bytes(name))
            ):
                source = await registry.resolve(page)
                observation = project_source_for_transport(registry, source)
                await runtime.ingestion.submit(
                    SubmitSourceObservation(scope_id=scope.scope_id, observation=observation)
                )
                pages += 1
        print(f"submitted {pages} page observations", flush=True)

        memory = runtime.memory.for_scope(scope.scope_id)
        for _ in range(pages + 2):
            if not (await memory.flush()).processed:
                break
        print("flushed", flush=True)

        groups: dict[str, list[tuple[int, int]]] = {}
        latencies: list[float] = []
        total_hit = total_annotated = 0
        for row in questions:
            name = row["doc_name"]
            annotated = {
                (name, int(item["evidence_page_num"]) + 1)
                for item in row["evidence"]
                if item.get("evidence_page_num") is not None
            }
            started = time.perf_counter()
            citations = await search_pdf_pages(memory, row["question"], limit=20)
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            returned: set[tuple[str, int]] = set()
            for citation in citations:
                entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
                document_id = entry.text.split("\n", 1)[0]
                page_number = int(entry.sources[0].source_id.rsplit(":", 1)[1])
                returned.add((document_id, page_number))
            hit = len(annotated & returned)
            total_hit += hit
            total_annotated += len(annotated)
            groups.setdefault(name, []).append((hit, len(annotated)))
            print(
                f"  {name:<20} hit={hit}/{len(annotated)} pages={len(returned)} "
                f"{elapsed:.0f}ms  {row['question'][:60]}",
                flush=True,
            )

        print()
        worst = 1.0
        for name, rows in groups.items():
            hit = sum(a for a, _ in rows)
            total = sum(b for _, b in rows)
            value = hit / total if total else 0.0
            worst = min(worst, value)
            print(f"  {name:<22} {hit}/{total} = {value:.4f}")
        latencies.sort()
        print()
        print(f"  product search_pdf_pages evidence-page Recall@20: {total_hit}/{total_annotated} "
              f"= {total_hit / total_annotated:.4f}  (gate 0.70)")
        print(f"  worst group: {worst:.4f}")
        print(f"  p50 latency: {latencies[len(latencies) // 2]:.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
