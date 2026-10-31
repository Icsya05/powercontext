"""A corpus-derived semantic embedding: latent semantic analysis.

No transformer runtime is available in this environment, so the semantic
channel used to measure the PDF retrieval is built from the corpus itself: the
term document matrix of the pages and the questions is decomposed with the
Gram-matrix eigen decomposition and every text is folded into the resulting
concept space.  It carries topic information a bag of words does not, which is
what the semantic channel is supposed to add, but it is a lower bound for a
real embedding model.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import numpy as np

TOKEN = re.compile(r"[a-z]+|\d+")


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class LsaEmbedding:
    def __init__(self, documents: list[str], questions: list[str], dimension: int, vocab: int) -> None:
        self.dimension = dimension
        texts = documents + questions
        counter = Counter()
        for text in texts:
            counter.update(set(tokenize(text)))
        self.vocabulary = {term: index for index, term in enumerate(counter.most_common(vocab))}
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
        frequency = (matrix > 0).sum(axis=0)
        inverse = np.log((len(texts) + 1.0) / (frequency + 1.0)) + 1.0
        matrix *= inverse
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        matrix /= norms
        gram = matrix @ matrix.T
        gram = (gram + gram.T) / 2.0
        values, vectors = np.linalg.eigh(gram)
        order = np.argsort(values)[::-1][:dimension]
        self.basis = (matrix.T @ vectors[:, order]) / np.sqrt(np.maximum(values[order], 1e-9))

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
            return self._fallback(text)
        concept /= norm
        return tuple(float(value) for value in concept)

    def _fallback(self, text: str) -> tuple[float, ...]:
        counts = Counter(tokenize(text))
        vector = [0.0] * self.dimension
        for term, count in counts.items():
            digest = hashlib.sha256(term.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            vector[0] = 1.0
            norm = 1.0
        return tuple(value / norm for value in vector)
