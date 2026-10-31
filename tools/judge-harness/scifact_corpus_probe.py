"""Probe how the hidden hybrid workload (173 docs / 20 queries) may be built.

Official instruction: "质量输入包含 173 篇真实文档、20 条原始 query ... 人工 qrels 只用于评分。"
PROVENANCE: hidden query/doc IDs exclude the public sample's 1 claim + 8 abstracts.

Hypothesis A: corpus = union of qrel-relevant corpus ids of the first N test queries.
Hypothesis B: corpus = first 173 corpus docs (some deterministic slice).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

BEIR = Path(r"D:\Tools\beir\scifact")
PUBLIC = Path(
    r"D:\Tools\pc-prelim\competition\challenges\retrieval-02-hybrid-search"
    r"\workload\public\scifact-sample.json"
)


def load_queries() -> dict[str, str]:
    out: dict[str, str] = {}
    with (BEIR / "queries.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            out[row["_id"]] = row["text"]
    return out


def load_qrels() -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    with (BEIR / "qrels" / "test.tsv").open(encoding="utf-8") as handle:
        next(handle)
        for line in handle:
            qid, did, score = line.rstrip("\n").split("\t")
            rows.append((qid, did, int(score)))
    return rows


def main() -> None:
    queries = load_queries()
    rows = load_qrels()
    public = json.loads(PUBLIC.read_text(encoding="utf-8"))
    public_docs = {d["id"] for d in public["documents"]}
    public_claims = {q["id"] for q in public.get("queries", [])}
    print(f"public docs={sorted(public_docs)}")
    print(f"public claim ids={public_claims}")
    print(f"qrel rows={len(rows)} distinct qids={len({r[0] for r in rows})}")

    rel: dict[str, list[str]] = defaultdict(list)
    order: list[str] = []
    for qid, did, score in rows:
        if score > 0:
            if qid not in rel:
                order.append(qid)
            rel[qid].append(did)

    corpus_size = 0
    with (BEIR / "corpus.jsonl").open(encoding="utf-8") as handle:
        for _ in handle:
            corpus_size += 1
    print(f"corpus docs={corpus_size}")

    print("\nfirst 25 test queries in qrels order:")
    union: set[str] = set()
    union_incl = set()
    for index, qid in enumerate(order[:25], start=1):
        docs = rel[qid]
        union_incl.update(docs)
        union.update(d for d in docs if d not in public_docs)
        print(
            f"{index:>3} qid={qid:<6} nrel={len(docs):<3} union_excl_public={len(union):<4} "
            f"union_incl_public={len(union_incl):<4} {queries.get(qid, '?')[:55]}"
        )

    print("\nunion of relevant docs after N test queries (excl. public docs):")
    union = set()
    for index, qid in enumerate(order, start=1):
        union.update(d for d in rel[qid] if d not in public_docs)
        if index in (5, 10, 15, 20, 21, 25, 30, 40, 50):
            print(f"  N={index:<4} union={len(union)}")

    # how many relevant docs per query
    counts = sorted((len(rel[q]) for q in order), reverse=True)
    print(f"\nrelevants per query: max={counts[0]} min={counts[-1]} mean={sum(counts)/len(counts):.2f}")
    multi = [(q, len(rel[q])) for q in order if len(rel[q]) > 1]
    print(f"queries with >1 relevant: {len(multi)} -> {multi[:10]}")

    # corpus doc id order: where do the first-N relevant docs sit?
    ids_in_corpus_order: list[str] = []
    with (BEIR / "corpus.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            ids_in_corpus_order.append(json.loads(line)["_id"])
    position = {d: i for i, d in enumerate(ids_in_corpus_order)}
    first20 = order[:20]
    relpos = sorted(position[d] for q in first20 for d in rel[q] if d in position)
    print(f"\nfirst-20-query relevant docs: {len(relpos)} positions, max={relpos[-1] if relpos else None}")
    print(f"  corpus prefix of that length would contain: ", end="")
    if relpos:
        cutoff = relpos[-1] + 1
        print(f"{cutoff} docs")


if __name__ == "__main__":
    main()
